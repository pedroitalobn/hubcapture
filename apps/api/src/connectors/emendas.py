"""Connector Emendas parlamentares (recebidos).

Emendas pagas ao município (por autor/comissão). Cada pagamento vira um RawRecord
de repasse com `emenda=True` e a área/categoria quando disponível.

IMPORTANTE: a API do Portal da Transparência EXIGE a chave `chave-api-dados`
(cadastro gratuito em portaldatransparencia.gov.br/api-de-dados). Sem a chave
(painel `emendas_api_key`), o connector falha com mensagem clara — registrada em
`sync_runs` — em vez de um 401 opaco.

NOTA: rota/campos a calibrar (Portal da Transparência / SIOP). Egress bloqueado
neste ambiente; validado por teste mockado.
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ..services import config as config_service
from ._http import get_json
from .base import RawRecord, register

ENDPOINT = "emendas"  # calibrar


class ChaveApiAusente(Exception):
    """Portal da Transparência exige `chave-api-dados` — configure no painel."""


class EmendasConnector:
    source_id = "emendas"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.emendas_base_url

    async def _headers(self) -> dict[str, str]:
        chave = await config_service.resolver("emendas_api_key")
        if not chave:
            raise ChaveApiAusente(
                "Configure emendas_api_key no painel admin (chave-api-dados do "
                "Portal da Transparência — cadastro gratuito)"
            )
        return {"chave-api-dados": chave}

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("emendas_base_url") or self.base_url
        data = await get_json(
            base,
            ENDPOINT,
            {"codigoIbge": municipio_ibge, "ano": str(since.year)},
            headers=await self._headers(),
        )
        linhas = data.get("items", data) if isinstance(data, dict) else data
        records: list[RawRecord] = []
        for row in linhas:
            id_ext = str(row.get("codigoEmenda") or row.get("id"))
            records.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=id_ext,
                    municipio_ibge=municipio_ibge,
                    endpoint=ENDPOINT,
                    raw={
                        "data_repasse": row.get("dataPagamento"),
                        "descricao": row.get("objeto") or row.get("funcao"),
                        "categoria": row.get("funcao"),
                        "orgao_superior": row.get("orgao"),
                        "natureza": "repasse",
                        "valor": row.get("valorPago"),
                        "documento": row.get("numeroEmenda"),
                        "emenda": True,
                        "detalhe": {"autor": row.get("nomeAutor")},
                    },
                )
            )
        return records

    async def health_check(self) -> bool:
        try:
            await get_json(
                self.base_url, ENDPOINT, {"pagina": "1"}, headers=await self._headers()
            )
            return True
        except Exception:
            return False


register(EmendasConnector())
