"""Connector do PAINEL TRANSFEREGOV (Visão Geral) — scraping + API de enrichment.

O `source_id` diz "serpro" por causa da hospedagem, mas o dado é TransfereGov: o
painel público da Visão Geral em
https://dd-publico.serpro.gov.br/extensions/painel/TransferegovbrVisaoGeral.html
— o SERPRO só serve a página. Por isso este connector faz parte do grupo
TransfereGov em `services/fontes.py`.

É um painel Qlik (JS pesado): só existe depois de renderizado, então a extração
vai pela facade de scraping, que hoje resolve isso com browser local
(Crawl4AI/Playwright) sem depender de serviço externo.

Coleta COMBINADA (seção 5): a API gateway do SERPRO (token) e o painel rodam
JUNTOS e o resultado é aglutinado — o painel é uma segunda fonte de verdade, não
um plano B, e é dele que vem a execução financeira (empenhado/pago/saldo).
Campos/rotas isolados p/ calibração.
"""

from __future__ import annotations

from datetime import date

from ..core.config import settings
from ..scraping.scraper import get_scraper
from ..services import config as config_service
from . import _combinada, _identidade
from ._http import get_json
from .base import RawRecord, register

ENDPOINT = "transferencias/municipio"  # calibrar (API gateway, requer token)

# schema de extração do painel dd-publico (TransferegovbrVisaoGeral) —
# calibrado contra o RELATÓRIO real exportado do painel (22 colunas), com os
# valores de execução financeira que o gestor quer ver (empenhado etc.)
PAINEL_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "transferencias": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "numero": {"type": "string", "description": "Nº Transferência"},
                    "link": {"type": "string"},
                    "ano": {"type": "string"},
                    "situacao": {"type": "string"},
                    "tipo_transferencia": {"type": "string"},
                    "modalidade": {"type": "string"},
                    "orgao": {"type": "string", "description": "Órgão Repassador"},
                    "ente_recebedor": {"type": "string"},
                    "natureza_juridica": {"type": "string"},
                    "uf": {"type": "string"},
                    "municipio": {"type": "string"},
                    "data_assinatura": {"type": "string"},
                    "data_inicio_vigencia": {"type": "string"},
                    "data_fim_vigencia": {"type": "string"},
                    "objeto": {"type": "string"},
                    "valor_global": {"type": "string"},
                    "valor_empenhado": {"type": "string"},
                    "valor_liberado": {"type": "string"},
                    "valor_pago": {"type": "string"},
                    "saldo_conta": {"type": "string", "description": "Saldo em Conta"},
                },
            },
        }
    },
}


class SerproConnector:
    source_id = "serpro"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.serpro_base_url

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        """Coleta COMBINADA: API gateway e painel público rodam juntos.

        O painel não é plano B — é a fonte que traz a execução financeira
        (empenhado/pago/saldo) que o gateway não devolve. Os dois lados são
        aglutinados por número da transferência; o que só existe num dos lados
        entra assim mesmo.
        """
        linhas_api, linhas_painel, erro_api = await _combinada.coletar(
            lambda: self._linhas_api(municipio_ibge),
            lambda: self._linhas_painel(municipio_ibge),
            fonte=self.source_id,
        )
        if not linhas_api and not linhas_painel:
            # nada de nenhum lado: releva o erro da API para virar sync_run
            if erro_api:
                raise erro_api
            return []

        registros: list[RawRecord] = []
        for api, painel in _combinada.aglutinar(linhas_api, linhas_painel):
            numero = (painel or {}).get("numero") or api.get("id")
            raw: dict = {"enrichment": api} if api else {}
            if painel:
                raw[_combinada.CHAVE_SCRAPE] = {"plano_acao": painel}
            registros.append(
                RawRecord(
                    source_id=self.source_id,
                    # sem número na página, a identidade sai do CONTEÚDO da linha
                    # (_identidade): a posição na lista mudava a cada coleta e fazia a
                    # mesma transferência ora duplicar, ora sobrescrever a vizinha
                    id_externo=(
                        str(numero)
                        if numero
                        else _identidade.hash_conteudo(
                            painel or api, municipio_ibge, prefixo="painel:"
                        )
                    ),
                    municipio_ibge=municipio_ibge,
                    endpoint=ENDPOINT if api else "scrape",
                    raw=raw,
                )
            )
        return registros

    async def _linhas_api(self, municipio_ibge: str) -> list[dict]:
        base = await config_service.resolver("serpro_base_url") or self.base_url
        data = await get_json(base, ENDPOINT, {"ibge": municipio_ibge})
        return data if isinstance(data, list) else data.get("items", [])

    async def _linhas_painel(self, municipio_ibge: str) -> list[dict]:
        painel = await config_service.resolver("serpro_painel_url") or settings.serpro_painel_url
        dados = await get_scraper().extract(
            painel,
            PAINEL_EXTRACT_SCHEMA,
            prompt=f"Extraia as transferências do município IBGE {municipio_ibge}.",
        )
        return dados.get("transferencias", []) if isinstance(dados, dict) else []

    async def health_check(self) -> bool:
        try:
            await get_json(self.base_url, ENDPOINT, {"limit": "1"})
            return True
        except Exception:
            return await get_scraper().is_enabled()


register(SerproConnector())
