"""Plano de trabalho da proposta — o elo que faltava para os PARECERES.

O parecer não é emitido sobre a proposta: é emitido sobre o **plano de trabalho**
dela (§36), e a rota `/planos_trabalho_analises_especiais` filtra pelo **id
INTEIRO** do plano. Só que a proposta que chega pelo CSV do SIconv não traz esse
id — traz o número da proposta ("30011/2026") e o `ID_PROPOSTA` interno. Sem o
elo, `services/pareceres` mandava o número formatado, o connector recusava (com
razão: a API responderia 422) e o gestor lia "não consegui consultar os pareceres"
numa proposta que TEM parecer publicado na fonte.

Este módulo resolve o elo: dado o que sabemos da proposta, descobre o id do plano
de trabalho. Duas portas, nesta ordem:

  1. **o registro-fonte** — se o id já veio na coleta, não há motivo para ir à
     rede (`id_no_registro_fonte`);
  2. **a rota de planos de trabalho** do módulo `especiais`, descoberta no spec
     (`_especiais.descobrir`) como nas demais rotas irmãs.

**Refiltro no cliente, sempre** — mesma disciplina de `empenhos_especiais`:
FastAPI ignora query param desconhecido em vez de recusar, então uma rota que
não aceite a chave devolveria a tabela nacional paginada e nós adotaríamos o
plano de trabalho de OUTRA proposta. Linha que não casa a identidade da proposta
é descartada.
"""

from __future__ import annotations

from typing import Any

from ..ingestion._campos import palavras, so_digitos
from ..services import config as config_service
from ._especiais import Rota, descobrir
from ._http import get_json

SOURCE_ID = "transferegov_plano_trabalho"

BASE_PADRAO = "https://api-publica.transferegov.gestao.gov.br/especiais/"
ENDPOINT_PADRAO = "planos_trabalho_especiais"

PALAVRAS_ROTA = ("plano", "trabalho")

# Ordem de especificidade: o que identifica UMA proposta vem primeiro.
CHAVES = (
    "id_proposta",
    "numero_proposta",
    "id_plano_acao",
    "numero_plano_acao",
)

# Colunas que identificam a proposta na linha devolvida (para o refiltro).
_TERMOS_IDENTIDADE = (("proposta",), ("plano", "acao"))

# Colunas que carregam o id do PLANO DE TRABALHO na linha devolvida.
_TERMOS_ID_PLANO = (
    ("id", "plano", "trabalho"),
    ("codigo", "plano", "trabalho"),
    ("id", "plano", "trabalho", "analise"),
)

TAMANHO_PAGINA = 50
MAX_PAGINAS = 5  # uma proposta não tem centenas de planos de trabalho


def _valores_por_termos(linha: dict, termos: tuple[tuple[str, ...], ...]) -> list[str]:
    achados: list[str] = []
    for chave, valor in linha.items():
        if not isinstance(chave, str) or valor in (None, "", [], {}):
            continue
        p = palavras(chave)
        if any(p.issuperset(t) for t in termos):
            achados.append(str(valor))
    return achados


def linha_e_da_proposta(linha: dict, chaves: dict[str, Any]) -> bool | None:
    """A linha é desta proposta? `None` = a resposta não permite afirmar."""
    identidade = _valores_por_termos(linha, _TERMOS_IDENTIDADE)
    if not identidade:
        return None
    alvos = {so_digitos(v) for v in chaves.values() if so_digitos(v)}
    return any(so_digitos(v) in alvos for v in identidade)


def id_da_linha(linha: dict) -> str | None:
    """O id do plano de trabalho dentro da linha — só serve se for INTEIRO."""
    for valor in _valores_por_termos(linha, _TERMOS_ID_PLANO):
        digitos = so_digitos(valor)
        if digitos:
            return digitos
    return None


def id_no_registro_fonte(dados: Any) -> str | None:
    """Varre o registro-fonte (qualquer nível/caixa) atrás do id do plano.

    A coleta guarda a linha inteira da origem (§46); quando a fonte publica o id
    do plano de trabalho, ele já está no cache e não precisamos ir à rede. Mesma
    disciplina de `propostas.ano_de`: ler do que já temos corrige o dado JÁ
    ingerido, sem esperar re-sync.
    """
    if isinstance(dados, dict):
        for chave, valor in dados.items():
            if isinstance(chave, str) and isinstance(valor, (str, int)):
                p = palavras(chave)
                if any(p.issuperset(t) for t in _TERMOS_ID_PLANO):
                    digitos = so_digitos(valor)
                    if digitos:
                        return digitos
        for valor in dados.values():
            achado = id_no_registro_fonte(valor)
            if achado:
                return achado
    elif isinstance(dados, list):
        for item in dados:
            achado = id_no_registro_fonte(item)
            if achado:
                return achado
    return None


class PlanoTrabalhoConnector:
    source_id = SOURCE_ID

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url

    async def base(self) -> str:
        return (
            self._base_url or await config_service.resolver("especiais_base_url") or BASE_PADRAO
        )

    async def rota(self) -> Rota:
        """Override do painel > spec do módulo > o endpoint documentado."""
        endpoint = await config_service.resolver("planos_trabalho_esp_endpoint")
        if endpoint:
            chave = await config_service.resolver("planos_trabalho_esp_chave") or CHAVES[0]
            return Rota(
                endpoint=endpoint.strip("/"),
                chave=chave,
                param_pagina="pagina",
                param_tamanho="tamanho_da_pagina",
            )

        descoberta = await descobrir(await self.base(), PALAVRAS_ROTA, CHAVES)
        if descoberta is not None:
            return descoberta

        return Rota(
            endpoint=ENDPOINT_PADRAO,
            chave=CHAVES[0],
            param_pagina="pagina",
            param_tamanho="tamanho_da_pagina",
            confirmada=False,
        )

    async def id_por_proposta(self, chaves: dict[str, Any]) -> str | None:
        """Id do plano de trabalho da proposta, ou None quando não dá para afirmar.

        Nunca levanta: quem chama já tem um caminho de degradação (o parecer
        simplesmente não sai) e um erro aqui viraria falha de página inteira.
        """
        disponiveis = {
            k: str(v).strip() for k, v in (chaves or {}).items() if str(v or "").strip()
        }
        if not disponiveis:
            return None

        try:
            rota = await self.rota()
            valor = disponiveis.get(rota.chave)
            if not valor:
                return None

            base = await self.base()
            brutos: list[dict] = []
            for pagina in range(1, MAX_PAGINAS + 1):
                dados = await get_json(
                    base,
                    rota.endpoint,
                    {**rota.filtro(valor), **rota.paginacao(pagina, TAMANHO_PAGINA)},
                )
                if isinstance(dados, dict):
                    dados = dados.get("itens") or dados.get("items") or dados.get("data") or []
                linhas = [d for d in dados if isinstance(d, dict)]
                brutos.extend(linhas)
                if len(linhas) < TAMANHO_PAGINA:
                    break
        except Exception:  # noqa: BLE001 — fonte fora do ar não é erro do painel
            return None

        indeterminadas: list[dict] = []
        for linha in brutos:
            veredito = linha_e_da_proposta(linha, disponiveis)
            if veredito is True:
                achado = id_da_linha(linha)
                if achado:
                    return achado
            elif veredito is None:
                indeterminadas.append(linha)

        # Sem coluna de identificação só confiamos no servidor quando o spec
        # confirmou que a rota aceita o filtro — senão seria plano de outro.
        if indeterminadas and rota.confirmada:
            for linha in indeterminadas:
                achado = id_da_linha(linha)
                if achado:
                    return achado
        return None


def get_connector() -> PlanoTrabalhoConnector:
    return PlanoTrabalhoConnector()
