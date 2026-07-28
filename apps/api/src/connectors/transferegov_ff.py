"""Connector TransfereGov — Fundo a Fundo (API REST PostgREST).

Base: https://api.transferegov.gestao.gov.br/fundoafundo/
Sintaxe PostgREST: ?campo=eq.valor · ?campo=in.(a,b,c)

Fluxo de coleta (semântico do modelo Fundo a Fundo):
  1. `programa_beneficiario` filtrado pelo IBGE do município → programas que o atendem
  2. `plano_acao` desses programas → os "planos" que viram Proposta
  3. `programa` → enriquece título/órgão

Resiliência (a API oficial retornou 502 em produção):
  - retry 3x com backoff exponencial em 5xx/timeout/erro de transporte (tenacity)
  - 4xx (ex.: filtro/coluna não suportada) NÃO é retry: vira ConnectorClientError,
    o serviço registra incidente em sync_runs e nunca engole o erro.

NOTA: os nomes de campo abaixo (IBGE, ids) são o ponto a calibrar contra a API
viva — estão isolados em constantes de propósito.
"""

from __future__ import annotations

from datetime import date

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..core.config import settings
from ..services import config as config_service
from .base import RawRecord, register

# ── Autocalibração contra a API viva ────────────────────────────────────────
# A API oficial recusou `codigo_ibge` em produção (42703: coluna não existe).
# Em vez de chutar um nome fixo, o connector DESCOBRE a coluna de IBGE:
#   1. override manual do painel admin (`transferegov_ff_ibge_field`), se houver;
#   2. OpenAPI do próprio PostgREST (GET / com Accept: application/openapi+json);
#   3. tentativa dos candidatos abaixo (400/42703 → próximo).
# O nome descoberto fica cacheado em memória por base_url.
IBGE_CANDIDATES = (
    "codigo_ibge",
    "cd_ibge",
    "cd_municipio_ibge",
    "codigo_municipio_ibge",
    "id_municipio_ibge",
    "co_municipio_ibge",
    "cd_municipio",
    "codigo_municipio",
    "municipio_codigo_ibge",
    "nr_ibge",
)
PROGRAMA_ID = "id_programa"
PLANO_ID = "id_plano_acao"
PAGE_LIMIT = 500
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# cache do campo IBGE descoberto, por base_url
_ibge_field_cache: dict[str, str] = {}


def _escolher_coluna_ibge(colunas: list[str]) -> str | None:
    """Heurística sobre o schema real: 'ibge' no nome > código de município."""
    for c in colunas:
        if "ibge" in c.lower():
            return c
    for c in colunas:
        lc = c.lower()
        if "municipio" in lc and any(k in lc for k in ("cd", "cod", "id")):
            return c
    return None


class ConnectorClientError(Exception):
    """Erro 4xx da fonte (filtro inválido, etc.) — não deve ser retry."""


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


class TransferegovFFConnector:
    source_id = "transferegov_ff"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.transferegov_ff_base_url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def _get(self, endpoint: str, params: dict[str, str]) -> list[dict]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=TIMEOUT) as client:
            resp = await client.get(endpoint, params=params, headers={"Accept": "application/json"})
            if 400 <= resp.status_code < 500:
                # 4xx não é retry — propaga como erro de cliente
                raise ConnectorClientError(f"{endpoint} {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()  # 5xx aqui vira HTTPStatusError => retry
            return resp.json()

    async def _descobrir_ibge_field(self) -> str | None:
        """Lê o OpenAPI do PostgREST e acha a coluna de IBGE de programa_beneficiario."""
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=TIMEOUT) as client:
                resp = await client.get("", headers={"Accept": "application/openapi+json"})
                resp.raise_for_status()
                spec = resp.json()
            defs = spec.get("definitions") or spec.get("components", {}).get("schemas", {})
            props = defs.get("programa_beneficiario", {}).get("properties", {})
            return _escolher_coluna_ibge(list(props))
        except Exception:
            return None

    async def _campo_ibge(self, municipio_ibge: str) -> str:
        """Override do painel > cache > OpenAPI > tentativa dos candidatos."""
        override = await config_service.resolver("transferegov_ff_ibge_field")
        if override:
            return override
        if self.base_url in _ibge_field_cache:
            return _ibge_field_cache[self.base_url]
        campo = await self._descobrir_ibge_field()
        if campo:
            _ibge_field_cache[self.base_url] = campo
            return campo
        ultima_falha: Exception | None = None
        for candidato in IBGE_CANDIDATES:
            try:
                await self._get(
                    "programa_beneficiario",
                    {candidato: f"eq.{municipio_ibge}", "limit": "1"},
                )
                _ibge_field_cache[self.base_url] = candidato
                return candidato
            except ConnectorClientError as exc:  # 42703 → coluna não existe
                ultima_falha = exc
                continue
        raise ConnectorClientError(
            "não achei a coluna de IBGE em programa_beneficiario — defina "
            f"transferegov_ff_ibge_field no painel admin. Última falha: {ultima_falha}"
        )

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        # base URL pode vir do painel admin (config runtime); fallback = .env
        self.base_url = await config_service.resolver("transferegov_ff_base_url") or self.base_url
        campo_ibge = await self._campo_ibge(municipio_ibge)
        # 1) beneficiários (municípios) → programas que atendem este IBGE
        beneficiarios = await self._get(
            "programa_beneficiario",
            {campo_ibge: f"eq.{municipio_ibge}", "limit": str(PAGE_LIMIT)},
        )
        # algumas bases usam IBGE de 6 dígitos (sem dígito verificador)
        if not beneficiarios and len(municipio_ibge) == 7:
            beneficiarios = await self._get(
                "programa_beneficiario",
                {campo_ibge: f"eq.{municipio_ibge[:6]}", "limit": str(PAGE_LIMIT)},
            )
        if not beneficiarios:
            return []

        # chave de ligação com programa: usa a que EXISTE nas linhas reais
        chave_prog = PROGRAMA_ID
        if PROGRAMA_ID not in beneficiarios[0]:
            for k in beneficiarios[0]:
                lk = k.lower()
                if "programa" in lk and lk.startswith(("id", "cd", "codigo")):
                    chave_prog = k
                    break

        prog_ids = {str(b[chave_prog]) for b in beneficiarios if b.get(chave_prog) is not None}
        benef_by_prog = {str(b.get(chave_prog)): b for b in beneficiarios}

        # 2) planos de ação + 3) programa — enriquecimento best-effort: se o
        # nome da chave divergir nessas tabelas (42703), degrada para o
        # beneficiário puro em vez de perder a coleta inteira
        planos: list[dict] = []
        programas: list[dict] = []
        if prog_ids:
            in_list = f"in.({','.join(sorted(prog_ids))})"
            try:
                planos = await self._get(
                    "plano_acao", {chave_prog: in_list, "limit": str(PAGE_LIMIT)}
                )
            except ConnectorClientError:
                planos = []
            try:
                programas = await self._get(
                    "programa", {chave_prog: in_list, "limit": str(PAGE_LIMIT)}
                )
            except ConnectorClientError:
                programas = []
        prog_by_id = {str(p.get(chave_prog)): p for p in programas}

        records: list[RawRecord] = []
        if planos:
            for pa in planos:
                pid = str(pa.get(chave_prog))
                id_ext = str(pa.get(PLANO_ID) or pa.get("id") or f"{pid}-{municipio_ibge}")
                records.append(
                    RawRecord(
                        source_id=self.source_id,
                        id_externo=id_ext,
                        municipio_ibge=municipio_ibge,
                        endpoint="plano_acao",
                        raw={
                            "plano_acao": pa,
                            "programa": prog_by_id.get(pid, {}),
                            "beneficiario": benef_by_prog.get(pid, {}),
                        },
                    )
                )
        else:
            # sem plano de ação acessível → o programa disponível ao município
            # ainda é uma oportunidade de captação
            for pid, b in benef_by_prog.items():
                records.append(
                    RawRecord(
                        source_id=self.source_id,
                        id_externo=f"programa-{pid}-{municipio_ibge}",
                        municipio_ibge=municipio_ibge,
                        endpoint="programa_beneficiario",
                        raw={
                            "plano_acao": {},
                            "programa": prog_by_id.get(pid, {}),
                            "beneficiario": b,
                        },
                    )
                )
        return records

    async def health_check(self) -> bool:
        try:
            await self._get("programa", {"limit": "1"})
            return True
        except Exception:
            return False


register(TransferegovFFConnector())
