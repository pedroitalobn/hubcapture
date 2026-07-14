"""Connector CAIXA/SIORB — obras de infraestrutura (OGU + APF).

Obras acompanhadas pela CAIXA como mandatária da União (SIORB): pavimentação,
saneamento, equipamentos urbanos. Cobre o eixo de infraestrutura.

NOTA: nomes de campo/rota isolados em constantes — ponto de calibração contra a
API viva da CAIXA. Egress bloqueado neste ambiente; validado por teste mockado.
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ..services import config as config_service
from ._http import get_json
from .base import RawRecord, register

ENDPOINT = "obras"  # calibrar
COL_ID = "num_contrato"
COL_NOME = "objeto"
COL_SITUACAO = "situacao_obra"
COL_PERC = "perc_execucao_fisica"
COL_INVEST = "valor_investimento"
COL_REPASSADO = "valor_liberado"
COL_INICIO = "data_inicio"
COL_FIM = "data_conclusao_prevista"
COL_LAT = "latitude"
COL_LON = "longitude"


class CaixaObrasConnector:
    source_id = "caixa"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.caixa_obras_base_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("caixa_obras_base_url") or self.base_url
        data = await get_json(base, ENDPOINT, {"municipio": municipio_ibge})
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
                        "objeto": row.get("descricao") or row.get(COL_NOME),
                        "programa": row.get("programa") or "OGU/APF",
                        "eixo": "infraestrutura",
                        "situacao": row.get(COL_SITUACAO),
                        "percentual_execucao": row.get(COL_PERC),
                        "valor_investimento": row.get(COL_INVEST),
                        "valor_repassado": row.get(COL_REPASSADO),
                        "data_inicio": row.get(COL_INICIO),
                        "data_fim_prevista": row.get(COL_FIM),
                        "latitude": row.get(COL_LAT),
                        "longitude": row.get(COL_LON),
                        "orgao": "CAIXA",
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


register(CaixaObrasConnector())
