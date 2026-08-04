"""Connector TransfereGov — Fundo a Fundo (API REST PostgREST).

Base: https://api.transferegov.gestao.gov.br/fundoafundo/
Sintaxe PostgREST: ?campo=eq.valor · ?campo=in.(a,b,c)

Modelo (corrigido): a oportunidade de um município é o `plano_acao` em que ele
é o ENTE RECEBEDOR. Consultamos `plano_acao` DIRETO pela coluna de IBGE do
recebedor — a tabela já traz órgão repassador, valores, vigência e situação.
Enriquecemos com `programa` (título/eixo) via `id_programa`.

Histórico: a versão anterior partia de `programa_beneficiario` filtrando por
IBGE, mas essa tabela NÃO tem coluna de município (só cnpj/nome/uf) — dava
"não achei a coluna de IBGE" e falhava toda coleta. `plano_acao` é a tabela
certa e tem `codigo_ibge_municipio_ente_recebedor_plano_acao`.

Resiliência (a API oficial já retornou 502 em produção):
  - retry 3x com backoff exponencial em 5xx/timeout/erro de transporte;
  - 4xx (filtro/coluna inválida) NÃO é retry: vira ConnectorClientError, que o
    serviço registra em sync_runs — nunca engolimos o erro.
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

# ── Autocalibração da coluna de IBGE do RECEBEDOR em plano_acao ──────────────
# Descobrimos o nome real (schemas mudam) por: override do painel admin >
# OpenAPI do PostgREST > tentativa dos candidatos abaixo.
TABLE = "plano_acao"
IBGE_CANDIDATES = (
    "codigo_ibge_municipio_ente_recebedor_plano_acao",  # nome atual confirmado
    "codigo_ibge_municipio_ente_repassador_plano_acao",  # fallback (repassador)
    "codigo_ibge_recebedor",
    "codigo_ibge_municipio",
    "codigo_ibge",
)
PROGRAMA_ID = "id_programa"
PLANO_ID = "id_plano_acao"
PAGE_LIMIT = 1000
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# cache do campo IBGE descoberto, por base_url
_ibge_field_cache: dict[str, str] = {}


def _escolher_coluna_ibge(colunas: list[str]) -> str | None:
    """Heurística sobre o schema real: recebedor com 'ibge' > qualquer 'ibge'."""
    lower = {c.lower(): c for c in colunas}
    for c in IBGE_CANDIDATES:
        if c in colunas:
            return c
    for lc, c in lower.items():
        if "ibge" in lc and "receb" in lc:
            return c
    for lc, c in lower.items():
        if "ibge" in lc:
            return c
    return None


class ConnectorClientError(Exception):
    """Erro 4xx da fonte (filtro inválido, etc.) — não deve ser retry."""


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
            resp = await client.get(
                endpoint, params=params, headers={"Accept": "application/json"}
            )
            if 400 <= resp.status_code < 500:
                raise ConnectorClientError(f"{endpoint} {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()  # 5xx → HTTPStatusError → retry
            return resp.json()

    async def _descobrir_ibge_field(self) -> str | None:
        """Lê o OpenAPI do PostgREST e acha a coluna de IBGE de plano_acao."""
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=TIMEOUT) as client:
                resp = await client.get("", headers={"Accept": "application/openapi+json"})
                resp.raise_for_status()
                spec = resp.json()
            defs = spec.get("definitions") or spec.get("components", {}).get("schemas", {})
            props = defs.get(TABLE, {}).get("properties", {})
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
                await self._get(TABLE, {candidato: f"eq.{municipio_ibge}", "limit": "1"})
                _ibge_field_cache[self.base_url] = candidato
                return candidato
            except ConnectorClientError as exc:  # 42703 → coluna não existe
                ultima_falha = exc
                continue
        raise ConnectorClientError(
            f"não achei a coluna de IBGE em {TABLE} — defina transferegov_ff_ibge_field "
            f"no painel admin. Última falha: {ultima_falha}"
        )

    async def _planos_por_ibge(self, campo_ibge: str, municipio_ibge: str) -> list[dict]:
        planos = await self._get(
            TABLE, {campo_ibge: f"eq.{municipio_ibge}", "limit": str(PAGE_LIMIT)}
        )
        # algumas bases usam IBGE de 6 dígitos (sem dígito verificador)
        if not planos and len(municipio_ibge) == 7:
            planos = await self._get(
                TABLE, {campo_ibge: f"eq.{municipio_ibge[:6]}", "limit": str(PAGE_LIMIT)}
            )
        return planos

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        # base URL e coluna podem vir do painel admin (config runtime); fallback = .env
        self.base_url = (
            await config_service.resolver("transferegov_ff_base_url") or self.base_url
        )
        campo_ibge = await self._campo_ibge(municipio_ibge)

        planos = await self._planos_por_ibge(campo_ibge, municipio_ibge)
        if not planos:
            return []

        # enriquecimento best-effort com `programa` (título/eixo) via id_programa
        prog_ids = {str(p[PROGRAMA_ID]) for p in planos if p.get(PROGRAMA_ID) is not None}
        prog_by_id: dict[str, dict] = {}
        if prog_ids:
            in_list = f"in.({','.join(sorted(prog_ids))})"
            try:
                programas = await self._get(
                    "programa", {PROGRAMA_ID: in_list, "limit": str(PAGE_LIMIT)}
                )
                prog_by_id = {str(p.get(PROGRAMA_ID)): p for p in programas}
            except ConnectorClientError:
                prog_by_id = {}  # degrada sem derrubar a coleta

        records: list[RawRecord] = []
        for pa in planos:
            pid = str(pa.get(PROGRAMA_ID))
            id_ext = str(pa.get(PLANO_ID) or pa.get("id") or f"{pid}-{municipio_ibge}")
            records.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=id_ext,
                    municipio_ibge=municipio_ibge,
                    endpoint=TABLE,
                    raw={"plano_acao": pa, "programa": prog_by_id.get(pid, {})},
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
