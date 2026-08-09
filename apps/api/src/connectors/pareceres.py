"""Análises/pareceres do plano de trabalho — API pública do TransfereGov.

CALIBRADO contra o spec real de `/planos_trabalho_analises_especiais`. É o único
connector que coleta por PLANO DE TRABALHO em vez de município (não implementa o
Protocol de `base.py`): o parecer é emitido sobre o plano, e a mesma proposta
acumula vários ao longo da análise.

Diferente das demais rotas do TransfereGov, esta **não é PostgREST**: filtra por
query param direto (`id_plano_trabalho=123`, sem `eq.`) e pagina com
`pagina`/`tamanho_da_pagina`. Por isso não usa `_postgrest.py`.

A chave de filtro é o **id inteiro** do plano de trabalho — não o número
formatado da proposta ("14275/2026"). Quem chama passa o que tem; aqui só vai
para a rede o que for numérico, senão a API responderia 422 e o gestor veria
"fonte indisponível" onde a verdade é "não tenho o id do plano".

Scraping da tela de tramitação segue como segunda fonte (§5): a API dá o
veredito e o texto, a tela dá QUEM assinou (responsável, papel, cargo) — os dois
lados se completam.
"""

from __future__ import annotations

from typing import Any

from ..services import config as config_service
from ._http import ConnectorClientError, get_json

SOURCE_ID = "transferegov_parecer"

# Rota real da API pública (módulo "especiais"). Overrides no painel admin.
BASE_PADRAO = "https://api-publica.transferegov.gestao.gov.br/especiais/"
ENDPOINT_PADRAO = "planos_trabalho_analises_especiais"

PARAM_PLANO = "id_plano_trabalho"
PARAM_PAGINA = "pagina"
PARAM_TAMANHO = "tamanho_da_pagina"
TAMANHO_PAGINA = 50
MAX_PAGINAS = 20  # trava de segurança: um plano não tem 1000 análises

# Situação do parecer — o veredito da análise (valores fechados do spec).
SITUACOES_PARECER = (
    "Aprovar Plano de Trabalho",
    "Não se aplica",
    "Reprovar Plano de Trabalho",
    "Solicitar Complementação",
)

# Ponto de calibração do scraping — a tela de tramitação (quem assinou).
URL_TRAMITACAO_PADRAO = ""

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


def id_do_plano(valor: Any) -> str | None:
    """Só o id INTEIRO serve de filtro nesta rota.

    O plano chega ora como id ("988776"), ora como número formatado
    ("14275/2026" — que é da proposta, não do plano). Mandar o segundo daria 422.
    """
    bruto = str(valor or "").strip()
    return bruto if bruto.isdigit() else None


class ParecerConnector:
    source_id = SOURCE_ID

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url

    async def _base(self) -> str:
        return (
            self._base_url
            or await config_service.resolver("pareceres_base_url")
            or BASE_PADRAO
        )

    async def _endpoint(self) -> str:
        return await config_service.resolver("pareceres_endpoint") or ENDPOINT_PADRAO

    async def _via_api(self, id_plano: str) -> list[dict]:
        """Pagina a rota até acabar (ou até MAX_PAGINAS)."""
        base, endpoint = await self._base(), await self._endpoint()
        coletados: list[dict] = []
        for pagina in range(1, MAX_PAGINAS + 1):
            dados = await get_json(
                base,
                endpoint,
                {
                    PARAM_PLANO: id_plano,
                    PARAM_PAGINA: str(pagina),
                    PARAM_TAMANHO: str(TAMANHO_PAGINA),
                },
            )
            # a rota pode devolver lista pura ou envelope paginado
            if isinstance(dados, dict):
                dados = dados.get("itens") or dados.get("items") or dados.get("data") or []
            linhas = [d for d in dados if isinstance(d, dict)]
            coletados.extend(linhas)
            if len(linhas) < TAMANHO_PAGINA:
                break
        return coletados

    async def _via_scraping(self, numero_plano: str) -> list[dict]:
        from ..scraping.scraper import get_scraper

        url_base = (
            await config_service.resolver("pareceres_url_tramitacao") or URL_TRAMITACAO_PADRAO
        )
        if not url_base:
            return []  # sem URL calibrada não há o que raspar — não é erro
        url = url_base.replace("{plano}", numero_plano)
        scraper = await get_scraper()
        extraido = await scraper.extract(url, PARECER_EXTRACT_SCHEMA)
        linhas = (extraido or {}).get("pareceres") or []
        for linha in linhas:
            if isinstance(linha, dict):
                linha.setdefault("_origem_url", url)
                linha["_scraper"] = (extraido or {}).get("_scraper")
        return [x for x in linhas if isinstance(x, dict)]

    async def collect_por_plano(self, numero_plano_trabalho: str) -> list[dict]:
        """Análises do plano. API é a fonte primária; scraping complementa/assume."""
        numero_plano = str(numero_plano_trabalho or "").strip()
        if not numero_plano:
            return []

        registros: list[dict] = []
        falhas: list[str] = []

        id_plano = id_do_plano(numero_plano)
        if id_plano:
            try:
                registros = await self._via_api(id_plano)
            except Exception as exc:
                falhas.append(f"api: {type(exc).__name__}: {exc}")
        else:
            falhas.append(
                f"api: '{numero_plano}' não é o id numérico do plano de trabalho "
                "(a rota filtra por id_plano_trabalho inteiro)"
            )

        if not registros:
            try:
                registros = await self._via_scraping(numero_plano)
            except Exception as exc:
                falhas.append(f"scraping: {type(exc).__name__}: {exc}")

        if not registros and falhas:
            raise ConnectorClientError(
                f"não consegui coletar pareceres do plano {numero_plano}. "
                f"Tentativas: {' | '.join(falhas)}"
            )
        return registros

    async def health_check(self) -> bool:
        try:
            await get_json(
                await self._base(), await self._endpoint(), {PARAM_TAMANHO: "1"}
            )
            return True
        except Exception:
            return False


def get_connector() -> ParecerConnector:
    return ParecerConnector()
