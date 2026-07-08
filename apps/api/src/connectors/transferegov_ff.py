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

# ── Campos a calibrar contra a API viva ─────────────────────────────────────
IBGE_FIELD = "codigo_ibge"  # coluna de IBGE em programa_beneficiario
PROGRAMA_ID = "id_programa"
PLANO_ID = "id_plano_acao"
PAGE_LIMIT = 500
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


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

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        # base URL pode vir do painel admin (config runtime); fallback = .env
        self.base_url = (
            await config_service.resolver("transferegov_ff_base_url") or self.base_url
        )
        # 1) beneficiários (municípios) → programas que atendem este IBGE
        beneficiarios = await self._get(
            "programa_beneficiario",
            {IBGE_FIELD: f"eq.{municipio_ibge}", "limit": str(PAGE_LIMIT)},
        )
        prog_ids = {
            str(b[PROGRAMA_ID]) for b in beneficiarios if b.get(PROGRAMA_ID) is not None
        }
        if not prog_ids:
            return []

        in_list = f"in.({','.join(sorted(prog_ids))})"

        # 2) planos de ação desses programas
        planos = await self._get(
            "plano_acao", {PROGRAMA_ID: in_list, "limit": str(PAGE_LIMIT)}
        )
        # 3) enriquecer com o programa
        programas = await self._get(
            "programa", {PROGRAMA_ID: in_list, "limit": str(PAGE_LIMIT)}
        )
        prog_by_id = {str(p.get(PROGRAMA_ID)): p for p in programas}
        benef_by_prog = {str(b.get(PROGRAMA_ID)): b for b in beneficiarios}

        records: list[RawRecord] = []
        for pa in planos:
            pid = str(pa.get(PROGRAMA_ID))
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
        return records

    async def health_check(self) -> bool:
        try:
            await self._get("programa", {"limit": "1"})
            return True
        except Exception:
            return False


register(TransferegovFFConnector())
