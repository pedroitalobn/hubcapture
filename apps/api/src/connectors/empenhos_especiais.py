"""Empenhos da proposta — `/empenhos_especiais` (transferências especiais).

O empenho é o fato que diz se o recurso saiu do papel: sem ele a proposta é
promessa. Ele NÃO vem na linha do plano de ação (por isso `execucao.
valor_empenhado` chegava vazio e a faixa de destaque não mostrava nada) — mora
em rota própria do módulo, consultada pelo **número da proposta**.

Coleta POR PROPOSTA, como `pareceres` e `emendas_especiais`; não implementa o
Protocol de `base.py` (que é por município).

**Refiltro no cliente, sempre.** A rota é conhecida (o endpoint está fixado
abaixo), mas o nome do parâmetro de filtro não é garantido — e FastAPI IGNORA
query param desconhecido em vez de recusar. Mandar `numero_proposta` numa rota
que espera outro nome devolveria a tabela NACIONAL de empenhos paginada, e o
gestor veria empenho de outro município como se fosse da proposta dele. Então
toda linha é conferida contra o número da proposta antes de entrar; linha que
não casa é descartada, e resposta que não ecoa NENHUMA coluna de identificação
só é aceita quando o spec confirmou o filtro.
"""

from __future__ import annotations

from typing import Any

from ..ingestion._campos import palavras, so_digitos
from ..services import config as config_service
from ._especiais import Rota, descobrir
from ._http import ConnectorClientError, get_json

SOURCE_ID = "transferegov_empenho"

BASE_PADRAO = "https://api-publica.transferegov.gestao.gov.br/especiais/"
# Rota informada pela documentação do módulo. Fica como PADRÃO (e não como
# palpite a descobrir) porque é dado real; a descoberta no spec ainda roda para
# confirmar o nome do parâmetro de filtro.
ENDPOINT_PADRAO = "empenhos_especiais"

PALAVRAS_ROTA = ("empenho",)

# O empenho é consultado pelo NÚMERO DA PROPOSTA — daí ele liderar a ordem de
# especificidade. Os demais entram como retaguarda para rotas irmãs.
CHAVES = (
    "numero_proposta",
    "id_proposta",
    "id_plano_acao",
    "numero_plano_acao",
    "id_plano_trabalho",
)

# colunas que identificam a proposta na linha devolvida (para o refiltro)
_TERMOS_IDENTIDADE = (("proposta",), ("plano", "acao"), ("plano", "trabalho"))

TAMANHO_PAGINA = 100
MAX_PAGINAS = 20  # trava: uma proposta não tem 2000 empenhos


def _valores_de_identidade(linha: dict) -> list[str]:
    """Todo valor da linha que possa ser o identificador da proposta."""
    achados: list[str] = []
    for chave, valor in linha.items():
        if not isinstance(chave, str) or valor in (None, "", [], {}):
            continue
        p = palavras(chave)
        if any(p.issuperset(termos) for termos in _TERMOS_IDENTIDADE):
            achados.append(str(valor))
    return achados


def linha_e_da_proposta(linha: dict, chaves: dict[str, Any]) -> bool | None:
    """A linha pertence a esta proposta?

    `None` = a resposta não trouxe coluna de identificação, então não dá para
    afirmar nem negar — quem chama decide se confia no filtro do servidor.
    """
    identidade = _valores_de_identidade(linha)
    if not identidade:
        return None
    alvos = {so_digitos(v) for v in chaves.values() if so_digitos(v)}
    return any(so_digitos(v) in alvos for v in identidade)


class EmpenhoEspecialConnector:
    source_id = SOURCE_ID

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url

    async def base(self) -> str:
        return (
            self._base_url
            or await config_service.resolver("especiais_base_url")
            or BASE_PADRAO
        )

    async def rota(self) -> Rota:
        """Override do painel > spec do módulo > o endpoint documentado.

        O último caso vem com `confirmada=False`: sabemos a rota, não sabemos se
        ela aceita o nome de parâmetro que vamos mandar.
        """
        endpoint = await config_service.resolver("empenhos_esp_endpoint")
        if endpoint:
            chave = await config_service.resolver("empenhos_esp_chave") or CHAVES[0]
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

    async def collect_por_proposta(self, chaves: dict[str, Any]) -> list[dict]:
        """Empenhos da proposta. `chaves` = o que sabemos dela; a rota escolhe
        por qual filtrar, e o resultado é conferido linha a linha."""
        disponiveis = {
            k: str(v).strip() for k, v in (chaves or {}).items() if str(v or "").strip()
        }
        if not disponiveis:
            return []

        rota = await self.rota()
        valor = disponiveis.get(rota.chave)
        if not valor:
            raise ConnectorClientError(
                f"a rota de empenho filtra por `{rota.chave}` e esta proposta não "
                f"tem esse dado (tenho: {', '.join(disponiveis)})"
            )

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

        # Refiltro: só entra o que comprovadamente é desta proposta.
        confirmados: list[dict] = []
        indeterminados = 0
        for linha in brutos:
            veredito = linha_e_da_proposta(linha, disponiveis)
            if veredito is True:
                confirmados.append(linha)
            elif veredito is None:
                indeterminados += 1

        if confirmados:
            return confirmados
        if indeterminados and rota.confirmada:
            # o servidor filtrou (o spec garante que a rota aceita a chave) e a
            # resposta simplesmente não repete a coluna de identificação
            return brutos
        if indeterminados:
            raise ConnectorClientError(
                f"a rota `{rota.endpoint}` respondeu {indeterminados} empenho(s) sem "
                f"coluna que identifique a proposta, e o filtro `{rota.chave}` não "
                "foi confirmado no spec do módulo — descartei para não misturar "
                "empenho de outra proposta. Calibre `empenhos_esp_endpoint`/"
                "`empenhos_esp_chave` no painel admin (Fontes)."
            )
        return []

    async def health_check(self) -> bool:
        try:
            await get_json(
                await self.base(), (await self.rota()).endpoint, {"tamanho_da_pagina": "1"}
            )
            return True
        except Exception:  # noqa: BLE001
            return False


def get_connector() -> EmpenhoEspecialConnector:
    return EmpenhoEspecialConnector()
