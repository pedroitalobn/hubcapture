"""Connector FPM — Fundo de Participação dos Municípios (recebidos).

Repasses decendiais do Tesouro (~a cada 10 dias). Decompõe cada repasse em
linhas de **crédito** (Parcela de IPI, Parcela de IR) e **dedução** (Retenção
PASEP, Dedução FUNDEB) — cada uma vira um RawRecord com `natureza`, para o
dashboard calcular o líquido = Σ créditos − Σ deduções.

NOTA: nomes de campo/rota isolados em constantes — ponto de calibração contra a
API viva do Tesouro. Egress bloqueado neste ambiente; validado por teste mockado.
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ._http import get_json
from .base import RawRecord, register

ENDPOINT = "fpm/municipio"  # calibrar
CREDITOS = ("valor_ipi", "valor_ir")
DEDUCOES = ("valor_pasep", "valor_fundeb")


class FpmConnector:
    source_id = "fpm"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.fpm_base_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        data = await get_json(
            self.base_url,
            ENDPOINT,
            {"cod_ibge": municipio_ibge, "data_inicio": since.isoformat()},
        )
        linhas = data.get("items", data) if isinstance(data, dict) else data
        records: list[RawRecord] = []
        for row in linhas:
            base_id = str(row.get("id") or f"{municipio_ibge}-{row.get('data')}")
            data_repasse = row.get("data") or row.get("data_repasse")
            for campo in CREDITOS + DEDUCOES:
                valor = row.get(campo)
                if valor in (None, "", 0, "0"):
                    continue
                natureza = "credito" if campo in CREDITOS else "deducao"
                records.append(
                    RawRecord(
                        source_id=self.source_id,
                        id_externo=f"{base_id}:{campo}",
                        municipio_ibge=municipio_ibge,
                        endpoint=ENDPOINT,
                        raw={
                            "data_repasse": data_repasse,
                            "descricao": campo.replace("valor_", "").upper(),
                            "categoria": "FPM",
                            "orgao_superior": "Tesouro Nacional",
                            "natureza": natureza,
                            "valor": valor,
                            "detalhe": {"rubrica": campo},
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


register(FpmConnector())
