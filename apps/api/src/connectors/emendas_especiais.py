"""Emenda parlamentar e seu AUTOR — enriquecimento da proposta no TransfereGov.

Na transferência especial o dinheiro tem dono declarado: a proposta/plano de
ação nasce de uma emenda parlamentar, e o gestor precisa saber QUAL emenda e de
QUEM — é com o gabinete do autor que ele fala. Esse dado não vem na mesma rota
do plano de ação: mora em rota irmã do módulo, consultada pela chave que o
gestor tem em mãos (id do plano de ação, nº da proposta, id do plano de
trabalho). Mesmo eixo do `pareceres.py`: coleta POR PROPOSTA, não por município,
então não implementa o Protocol de `base.py`.

Duas maneiras de responder, nesta ordem:

1. **rota do módulo** (`_especiais.descobrir`) — a emenda completa: número,
   ano, tipo, autor com partido/UF e os valores empenhado/pago;
2. **registro-fonte que já temos** (`emendas_do_registro_fonte`) — o plano de
   ação do módulo especiais carrega `nome_parlamentar_emenda_plano_acao` e o
   valor do repasse. É menos, mas é offline e instantâneo: sem rota calibrada o
   painel ainda mostra de quem é a emenda, em vez de uma seção vazia.

A rota NÃO é constante (§27): nome de rota chutado foi o que quebrou em
produção. Overrides manuais no painel admin (`emendas_esp_endpoint` /
`emendas_esp_chave`) para quando a descoberta não bastar.
"""

from __future__ import annotations

from typing import Any

from ..services import config as config_service
from ._especiais import Rota, descobrir
from ._http import ConnectorClientError, get_json

SOURCE_ID = "transferegov_emenda"

BASE_PADRAO = "https://api-publica.transferegov.gestao.gov.br/especiais/"

# assunto da rota — o nome tem que falar de emenda
PALAVRAS_ROTA = ("emenda",)

# Chaves de consulta em ORDEM DE ESPECIFICIDADE: o id do plano de ação é o elo
# forte (é a entidade que a emenda financia); o nº da proposta é o que o gestor
# tem em mãos e serve de retaguarda.
CHAVES = (
    "id_plano_acao",
    "numero_plano_acao",
    "id_plano_trabalho",
    "numero_plano_trabalho",
    "numero_proposta",
    "id_proposta",
)

TAMANHO_PAGINA = 50
MAX_PAGINAS = 10  # trava: uma proposta não tem 500 emendas


def _limpo(valor: Any) -> str:
    return str(valor or "").strip()


def emendas_do_registro_fonte(dados_fonte: dict | None) -> list[dict]:
    """Emenda embutida no registro-fonte do plano de ação (sem ir à rede).

    O plano de ação do módulo especiais já traz o parlamentar e o valor do
    repasse (`*_emenda_plano_acao`). Sem a rota calibrada isso é tudo que temos
    — e é bem melhor que nada: responde "de quem é a emenda" na hora.
    """
    if not isinstance(dados_fonte, dict):
        return []

    # o registro pode vir aninhado (`{"plano_acao": {...}}`) como o normalizer trata
    plano = dados_fonte.get("plano_acao")
    linha = plano if isinstance(plano, dict) else dados_fonte

    campos = {
        k: v
        for k, v in linha.items()
        if isinstance(k, str)
        and v not in (None, "", [], {})
        and ("emenda" in k.lower() or "parlamentar" in k.lower())
    }
    if not campos:
        return []
    # só vale como emenda se identificar autor ou número — um campo solto de
    # valor não descreve emenda nenhuma
    tem_identidade = any(
        ("parlamentar" in k.lower() or "autor" in k.lower() or "numero" in k.lower())
        for k in campos
    )
    if not tem_identidade:
        return []
    return [{**campos, "_origem": "registro_fonte"}]


class EmendaEspecialConnector:
    source_id = SOURCE_ID

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url

    async def base(self) -> str:
        return (
            self._base_url
            or await config_service.resolver("especiais_base_url")
            or BASE_PADRAO
        )

    async def rota(self) -> Rota | None:
        """Override do painel primeiro; senão descobre no spec do módulo."""
        endpoint = await config_service.resolver("emendas_esp_endpoint")
        if endpoint:
            chave = await config_service.resolver("emendas_esp_chave") or CHAVES[0]
            return Rota(endpoint=endpoint.strip("/"), chave=chave)
        return await descobrir(await self.base(), PALAVRAS_ROTA, CHAVES)

    async def collect_por_proposta(self, chaves: dict[str, Any]) -> list[dict]:
        """Emendas da proposta. `chaves` = o que sabemos dela (id_plano_acao,
        numero_proposta…); a rota escolhe qual dessas ela aceita filtrar."""
        disponiveis = {k: _limpo(v) for k, v in (chaves or {}).items() if _limpo(v)}
        if not disponiveis:
            return []

        rota = await self.rota()
        if rota is None:
            raise ConnectorClientError(
                "não achei no módulo especiais uma rota de emenda que filtre por "
                f"{', '.join(disponiveis)} — calibre `emendas_esp_endpoint` e "
                "`emendas_esp_chave` no painel admin (Fontes)"
            )

        valor = disponiveis.get(rota.chave)
        if not valor:
            raise ConnectorClientError(
                f"a rota de emenda filtra por `{rota.chave}` e esta proposta não "
                f"tem esse dado (tenho: {', '.join(disponiveis)})"
            )

        base = await self.base()
        coletados: list[dict] = []
        for pagina in range(1, MAX_PAGINAS + 1):
            params = {
                **rota.filtro(valor),
                **rota.paginacao(pagina, TAMANHO_PAGINA),
            }
            dados = await get_json(base, rota.endpoint, params)
            if isinstance(dados, dict):
                dados = dados.get("itens") or dados.get("items") or dados.get("data") or []
            linhas = [d for d in dados if isinstance(d, dict)]
            coletados.extend(linhas)
            # sem paginação declarada a rota devolve tudo de uma vez
            if len(linhas) < TAMANHO_PAGINA or not rota.paginacao(pagina, TAMANHO_PAGINA):
                break
        return coletados

    async def health_check(self) -> bool:
        """Saudável = consigo descobrir (ou já tenho calibrada) a rota da emenda."""
        try:
            return (await self.rota()) is not None
        except Exception:  # noqa: BLE001
            return False


def get_connector() -> EmendaEspecialConnector:
    return EmendaEspecialConnector()
