"""Emenda parlamentar e seu AUTOR — enriquecimento da proposta no TransfereGov.

Na transferência especial o dinheiro tem dono declarado: a proposta/plano de
ação nasce de uma emenda parlamentar, e o gestor precisa saber QUAL emenda e de
QUEM — é com o gabinete do autor que ele fala. Esse dado não vem na mesma rota
do plano de ação: mora em rota irmã do módulo, consultada pela chave que o
gestor tem em mãos (id do plano de ação, nº da proposta, id do plano de
trabalho). Mesmo eixo do `pareceres.py`: coleta POR PROPOSTA, não por município,
então não implementa o Protocol de `base.py`.

Três maneiras de responder, nesta ordem:

1. **rota do módulo** (`_especiais.descobrir`) — a emenda completa: número,
   ano, tipo, autor com partido/UF e os valores empenhado/pago;
2. **o próprio plano de ação na fonte** (`_emenda_do_plano_acao`) — o módulo
   `transferenciasespeciais` NÃO publica tabela de emenda: das suas 14 tabelas,
   nenhuma tem o assunto. E não precisa — na transferência especial a emenda é
   atributo do plano de ação, que traz autor, ano, código formatado, número e
   sequencial (`*_emenda_parlamentar_plano_acao`). Buscar a linha por
   `id_plano_acao` devolve a emenda OFICIAL, não um resumo;
3. **registro-fonte que já temos** (`emendas_do_registro_fonte`) — os mesmos
   campos, quando o plano de ação já está salvo com a proposta. É offline e
   instantâneo: serve quando a fonte está fora do ar.

Só levanta erro se as três falharem — seção vazia com dado disponível é pior
que lenta.

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

BASE_PADRAO = "https://api.transferegov.gestao.gov.br/transferenciasespeciais/"

# assunto da rota — o nome tem que falar de emenda
PALAVRAS_ROTA = ("emenda",)

# Chaves de consulta em ORDEM DE ESPECIFICIDADE: o id do plano de ação é o elo
# forte (é a entidade que a emenda financia); o nº da proposta é o que o gestor
# tem em mãos e serve de retaguarda.
#: tabela do plano de ação — onde a emenda realmente mora neste módulo
ENDPOINT_PLANO_ACAO = "plano_acao_especial"

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

    # A LINHA BRUTA do CSV entra por baixo (§46): o de-para do connector só
    # mapeia as colunas que ele conhece, e as da emenda (NR_EMENDA,
    # NOME_PARLAMENTAR, VL_EMENDA) ficavam invisíveis aqui mesmo estando no
    # registro-fonte — a proposta do SIconv caía direto no texto de erro.
    bruto = linha.get("csv")
    if isinstance(bruto, dict):
        combinada = {k: v for k, v in bruto.items() if isinstance(k, str)}
        combinada.update({k: v for k, v in linha.items() if v not in (None, "", [], {})})
        linha = combinada

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
            # Sem rota dedicada: a emenda é atributo do plano de ação. Só é erro
            # se nem o plano de ação responder.
            do_plano = await self._emenda_do_plano_acao(disponiveis)
            if do_plano:
                return do_plano
            raise ConnectorClientError(
                "não achei no módulo especiais rota de emenda nem plano de ação que "
                f"filtre por {', '.join(disponiveis)} — calibre `emendas_esp_endpoint` "
                "e `emendas_esp_chave` no painel admin (Fontes)"
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

    async def _emenda_do_plano_acao(self, disponiveis: dict[str, str]) -> list[dict]:
        """A emenda lida da linha do plano de ação na fonte (`id_plano_acao`).

        Devolve só os campos de emenda/parlamentar — o resto da linha é o plano
        de ação, que o painel já mostra em outra seção; repetir tudo aqui faria
        a tela dizer duas vezes a mesma coisa.
        """
        valor = disponiveis.get("id_plano_acao")
        if not valor:
            return []
        try:
            dados = await get_json(
                await self.base(),
                ENDPOINT_PLANO_ACAO,
                {"id_plano_acao": f"eq.{valor}", "limit": "1"},
            )
        except Exception:  # noqa: BLE001 — fonte fora: cai no registro-fonte
            return []
        linhas = [d for d in dados if isinstance(d, dict)] if isinstance(dados, list) else []
        if not linhas:
            return []
        emenda = emendas_do_registro_fonte(linhas[0])
        for e in emenda:
            e["_origem"] = "plano_acao_especial"
        return emenda

    async def health_check(self) -> bool:
        """Saudável = a rota da emenda existe OU o plano de ação responde.

        Este módulo não publica tabela de emenda; exigir rota aqui pintaria de
        vermelho uma fonte que entrega a emenda todo dia pelo plano de ação.
        """
        try:
            if (await self.rota()) is not None:
                return True
            dados = await get_json(await self.base(), ENDPOINT_PLANO_ACAO, {"limit": "1"})
            return bool(dados)
        except Exception:  # noqa: BLE001
            return False


def get_connector() -> EmendaEspecialConnector:
    return EmendaEspecialConnector()
