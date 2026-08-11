"""Connector TransfereGov — Transferências Especiais (API pública PostgREST).

Base: https://api.transferegov.gestao.gov.br/transferenciasespeciais/
Tabela: plano_acao_especial (PostgREST — ?campo=eq.valor / ?campo=ilike.*x*).

A tabela NÃO tem código IBGE — o beneficiário vem por UF + CNPJ + NOME
(ex.: "MUNICIPIO DE FORTALEZA", uf=CE). Então filtramos por
`uf_beneficiario` = UF do município + `nome_beneficiario ilike *<nome>*`,
resolvendo IBGE→(nome, uf) via services.municipios. Como o mesmo nome pode
existir em variações ("FORTALEZA" × "FORTALEZA DO TABOCAO"), refinamos em
Python: só mantém linhas cujo beneficiário casa o município.

Sem stub de scraping: se a API falhar, o erro sobe e vira incidente em
sync_runs — nunca gravamos uma "proposta" vazia (o antigo scrape-<ibge>).
"""

from __future__ import annotations

import unicodedata
from datetime import date

from ..services import config as config_service
from ..services import municipios as municipios_service
from ._http import get_json
from .base import RawRecord, register

TABLE = "plano_acao_especial"
UF_FIELD = "uf_beneficiario_plano_acao"
NOME_FIELD = "nome_beneficiario_plano_acao"
ID_FIELD = "id_plano_acao"
DEFAULT_BASE = "https://api.transferegov.gestao.gov.br/transferenciasespeciais/"


def _norm(t: str) -> str:
    sem = unicodedata.normalize("NFD", t or "")
    return "".join(c for c in sem if unicodedata.category(c) != "Mn").lower().strip()


class TransferegovEspConnector:
    source_id = "transferegov_esp"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = DEFAULT_BASE

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("transferegov_esp_base_url") or self.base_url
        # a base antiga (api-publica/especiais) não tem plano_acao_especial;
        # se a config ainda apontar pra lá, usa o host que tem a tabela.
        if "api-publica" in base or "/especiais" in base:
            base = DEFAULT_BASE

        nome_uf = await municipios_service.nome_uf_por_ibge(municipio_ibge)
        if not nome_uf:
            return []  # sem como casar o município → nada a coletar
        nome, uf = nome_uf
        nome_norm = _norm(nome)

        data = await get_json(
            base,
            TABLE,
            {UF_FIELD: f"eq.{uf}", NOME_FIELD: f"ilike.*{nome}*", "limit": "500"},
        )
        linhas = data if isinstance(data, list) else data.get("items", [])

        registros: list[RawRecord] = []
        for row in linhas:
            benef = _norm(str(row.get(NOME_FIELD) or ""))
            # refino: beneficiário tem que SER o município deste nome (evita
            # "FORTALEZA" casar "FORTALEZA DO TABOCAO").
            if not (benef.endswith(nome_norm) or f" {nome_norm} " in f" {benef} "):
                continue
            registros.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=str(row.get(ID_FIELD) or row.get("id")),
                    municipio_ibge=municipio_ibge,
                    endpoint=TABLE,
                    raw={"plano_acao": row, "modalidade": "Especial"},
                )
            )
        return registros

    async def health_check(self) -> bool:
        try:
            await get_json(self.base_url, TABLE, {"limit": "1"})
            return True
        except Exception:
            return False


register(TransferegovEspConnector())
