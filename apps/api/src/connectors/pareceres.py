"""Pareceres do plano de trabalho (TransfereGov/SICONV).

O parecer é emitido sobre o PLANO DE TRABALHO, não sobre a proposta — daí este
connector ser o único que coleta por `numero_plano_trabalho` em vez de por
município (não implementa o Protocol de `base.py`, que é município+since; é
consultado sob demanda a partir da proposta).

CALIBRAÇÃO PENDENTE — rota e nomes de campo são o ponto de ajuste, como em
toda fonte nova do repo (§15/§27). O que está aqui é a estrutura da tela de
tramitação (data · esfera · responsável · papel · cargo · link do parecer);
os identificadores exatos precisam ser conferidos contra a fonte viva com
`python -m src.tools.probe_fontes`. Enquanto não forem, o connector falha com
mensagem clara em `sync_runs` em vez de inventar dado.

Dois caminhos, na ordem da §5 (coleta combinada):
1. API — se a fonte publicar a tramitação numa rota REST (override
   `pareceres_endpoint` no painel admin);
2. Scraping — a tela do plano de trabalho pelo facade (`scraping/scraper.py`),
   que é como o gestor a vê hoje. `PARECER_EXTRACT_SCHEMA` casa com a tabela
   renderizada; `scraping/tabelas.py` já lê `<table>` e grid ARIA.

Se a página exigir login, o scraping devolve vazio/erro e isso vira incidente
registrado — não silêncio.
"""

from __future__ import annotations

from typing import Any

from ..services import config as config_service
from ._http import ConnectorClientError, get_json

SOURCE_ID = "transferegov_parecer"

# Ponto de calibração 1 — rota da API (quando houver). `{plano}` é substituído
# pelo número do plano de trabalho.
ENDPOINT_PADRAO = "plano_trabalho_parecer"
PARAM_PLANO = "numero_plano_trabalho"

# Ponto de calibração 2 — URL da tela de tramitação para o scraping.
URL_TRAMITACAO_PADRAO = (
    "https://discricionarias.transferegov.sistema.gov.br/voluntarias/"
    "PlanoTrabalhoParecer/ConsultarParecer.do?numeroPlanoTrabalho={plano}"
)

# Ponto de calibração 3 — o que queremos que o scraper estruture. Os rótulos das
# colunas da tela ("Data", "Esfera", "Responsável"…) casam por `description` em
# `scraping/tabelas.py`.
PARECER_EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pareceres": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "Data"},
                    "esfera": {"type": "string", "description": "Esfera"},
                    "responsavel": {"type": "string", "description": "Responsável"},
                    "papel": {"type": "string", "description": "Perfil"},
                    "cargo": {"type": "string", "description": "Cargo"},
                    "situacao": {"type": "string", "description": "Situação"},
                    "url_parecer": {"type": "string", "description": "Visualizar Parecer"},
                },
            },
        }
    },
}


class ParecerConnector:
    """Coleta por NÚMERO DE PLANO DE TRABALHO (não por município)."""

    source_id = SOURCE_ID

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url

    async def _base(self) -> str | None:
        return self._base_url or await config_service.resolver("pareceres_base_url")

    async def _via_api(self, numero_plano: str) -> list[dict]:
        base = await self._base()
        if not base:
            return []
        endpoint = await config_service.resolver("pareceres_endpoint") or ENDPOINT_PADRAO
        dados = await get_json(base, endpoint, {PARAM_PLANO: f"eq.{numero_plano}"})
        if isinstance(dados, dict):
            dados = dados.get("pareceres") or dados.get("itens") or []
        return [d for d in dados if isinstance(d, dict)]

    async def _via_scraping(self, numero_plano: str) -> list[dict]:
        from ..scraping.scraper import get_scraper

        url_base = (
            await config_service.resolver("pareceres_url_tramitacao") or URL_TRAMITACAO_PADRAO
        )
        url = url_base.replace("{plano}", numero_plano)
        scraper = await get_scraper()  # levanta ScraperNotConfigured se não houver
        extraido = await scraper.extract(url, PARECER_EXTRACT_SCHEMA)
        linhas = (extraido or {}).get("pareceres") or []
        for linha in linhas:
            if isinstance(linha, dict):
                linha.setdefault("_origem_url", url)
                linha["_scraper"] = extraido.get("_scraper")
        return [x for x in linhas if isinstance(x, dict)]

    async def collect_por_plano(self, numero_plano_trabalho: str) -> list[dict]:
        """Pareceres do plano de trabalho. API primeiro; scraping assume/complementa.

        Best-effort nos DOIS lados: a falha de um não derruba o outro. Se ambos
        falharem, levanta — quem chama registra em `sync_runs`.
        """
        numero_plano = str(numero_plano_trabalho).strip()
        if not numero_plano:
            return []

        registros: list[dict] = []
        falhas: list[str] = []

        try:
            registros = await self._via_api(numero_plano)
        except Exception as exc:  # rota não calibrada / fora do ar
            falhas.append(f"api: {type(exc).__name__}: {exc}")

        if not registros:
            try:
                registros = await self._via_scraping(numero_plano)
            except Exception as exc:  # sem scraper configurado / página com login
                falhas.append(f"scraping: {type(exc).__name__}: {exc}")

        if not registros and falhas:
            raise ConnectorClientError(
                "não consegui coletar pareceres do plano de trabalho "
                f"{numero_plano} — calibre a fonte no painel admin "
                f"(pareceres_base_url/pareceres_endpoint/pareceres_url_tramitacao). "
                f"Tentativas: {' | '.join(falhas)}"
            )
        return registros

    async def health_check(self) -> bool:
        base = await self._base()
        if not base:
            return False
        try:
            await get_json(base, await config_service.resolver("pareceres_endpoint")
                           or ENDPOINT_PADRAO, {"limit": "1"})
            return True
        except Exception:
            return False


def get_connector() -> ParecerConnector:
    return ParecerConnector()
