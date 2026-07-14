"""Connector SISMOB — obras de saúde (Ministério da Saúde).

Acompanha propostas/obras do Sistema de Monitoramento de Obras (SISMOB): UBS,
UPA, academias da saúde etc. Fecha o eixo de execução na área da saúde.

NOTA: nomes de campo/rota isolados em constantes — ponto de calibração contra a
API viva do MS. Egress bloqueado neste ambiente; validado por teste mockado.
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ..services import config as config_service
from ._http import get_json
from .base import RawRecord, register

ENDPOINT = "obras"  # calibrar
COL_ID = "id_proposta"
COL_NOME = "tipo_obra"
COL_SITUACAO = "estagio_obra"
COL_PERC = "percentual_execucao"
COL_INVEST = "valor_investimento"
COL_REPASSADO = "valor_repassado"
COL_INICIO = "data_inicio"
COL_FIM = "data_previsao"
COL_LAT = "latitude"
COL_LON = "longitude"


class SismobConnector:
    source_id = "sismob"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.sismob_base_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("sismob_base_url") or self.base_url
        data = await get_json(base, ENDPOINT, {"codigo_ibge": municipio_ibge})
        linhas = data.get("items", data) if isinstance(data, dict) else data
        records: list[RawRecord] = []
        for row in linhas:
            ext = str(row.get(COL_ID) or f"{municipio_ibge}-{len(records)}")
            records.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=ext,
                    municipio_ibge=municipio_ibge,
                    endpoint=ENDPOINT,
                    raw={
                        "nome": row.get(COL_NOME),
                        "objeto": row.get("descricao"),
                        "programa": row.get("programa") or "SISMOB",
                        "eixo": "saude",
                        "situacao": row.get(COL_SITUACAO),
                        "percentual_execucao": row.get(COL_PERC),
                        "valor_investimento": row.get(COL_INVEST),
                        "valor_repassado": row.get(COL_REPASSADO),
                        "data_inicio": row.get(COL_INICIO),
                        "data_fim_prevista": row.get(COL_FIM),
                        "latitude": row.get(COL_LAT),
                        "longitude": row.get(COL_LON),
                        "orgao": "Ministério da Saúde",
                        "detalhe": row,
                    },
                )
            )
        return records

    async def health_check(self) -> bool:
        try:
            await get_json(self.base_url, ENDPOINT, {"limit": "1"})
            return True
        except Exception:
            return False


register(SismobConnector())
