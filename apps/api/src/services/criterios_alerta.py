"""Critérios de alerta — QUAIS mudanças o usuário quer receber.

Antes, monitorar era tudo-ou-nada: qualquer alteração virava alerta e o painel
enchia de ruído. Aqui mora o registro dos critérios (o catálogo que o front
mostra no multi-select) e a resolução do que está EFETIVAMENTE ligado num
monitoramento.

Dois escopos, porque as duas configurações são de naturezas diferentes:

- `proposta`  → monitorar uma proposta-chave (`monitoramentos`): o que mudou
  NELA (parecer, empenho, pagamento, publicação, vigência, situação…).
- `territorio` → monitorar um município (`monitoramentos_busca`): o que aparece
  no território (proposta nova, oportunidade não aproveitada).

`criterios = NULL` (coluna vazia) significa "os padrões do registro" — é o que
vale para todo monitoramento criado antes desta feature, então ninguém deixa de
receber o que já recebia. Critério novo = mais uma entrada em `CRITERIOS`; o
catálogo, a validação da API e o multi-select do front acompanham sozinhos.
"""

from __future__ import annotations

from dataclasses import dataclass

ESCOPO_PROPOSTA = "proposta"
ESCOPO_TERRITORIO = "territorio"
ESCOPOS = (ESCOPO_PROPOSTA, ESCOPO_TERRITORIO)

# Janela do aviso de vencimento: convênio que vence dentro dela gera alerta uma
# vez (na entrada da janela), não a cada varredura.
JANELA_VENCIMENTO_DIAS = 30


@dataclass(frozen=True)
class Criterio:
    chave: str
    rotulo: str
    descricao: str
    escopo: str
    padrao: bool = True


CRITERIOS: tuple[Criterio, ...] = (
    Criterio(
        chave="parecer",
        rotulo="Atualização de pareceres",
        descricao=(
            "Novo parecer do plano de trabalho ou mudança no veredito "
            "(aprovar, reprovar, solicitar complementação)."
        ),
        escopo=ESCOPO_PROPOSTA,
    ),
    Criterio(
        chave="empenho",
        rotulo="Valor empenhado",
        descricao="Novo empenho ou alteração do valor empenhado da proposta.",
        escopo=ESCOPO_PROPOSTA,
    ),
    Criterio(
        chave="pagamento",
        rotulo="Pagamento",
        descricao="Valor pago ou liberado (desembolso) mudou.",
        escopo=ESCOPO_PROPOSTA,
    ),
    Criterio(
        chave="publicacao",
        rotulo="Publicação",
        descricao="Publicação do instrumento na fonte (situação ou valor publicado).",
        escopo=ESCOPO_PROPOSTA,
    ),
    Criterio(
        chave="vencimento",
        rotulo="Vencimento do convênio",
        descricao=(
            f"Fim de vigência alterado ou a menos de {JANELA_VENCIMENTO_DIAS} dias do vencimento."
        ),
        escopo=ESCOPO_PROPOSTA,
    ),
    Criterio(
        chave="situacao",
        rotulo="Situação e movimentação",
        descricao="Mudança de situação ou nova movimentação na tramitação.",
        escopo=ESCOPO_PROPOSTA,
    ),
    Criterio(
        chave="prazo",
        rotulo="Prazos",
        descricao="Prazos da proposta incluídos, alterados ou removidos.",
        escopo=ESCOPO_PROPOSTA,
    ),
    Criterio(
        chave="pendencia",
        rotulo="Pendências",
        descricao="Pendência aberta ou resolvida na proposta.",
        escopo=ESCOPO_PROPOSTA,
    ),
    Criterio(
        chave="nova_proposta",
        rotulo="Novas propostas no território",
        descricao="Proposta que aparece nas fontes para o município monitorado.",
        escopo=ESCOPO_TERRITORIO,
    ),
    Criterio(
        chave="oportunidade",
        rotulo="Oportunidades não aproveitadas",
        descricao=(
            "Recursos recebidos de uma fonte sem nenhuma proposta de captação cadastrada nela."
        ),
        escopo=ESCOPO_TERRITORIO,
    ),
)

_POR_CHAVE = {c.chave: c for c in CRITERIOS}

# Tipos de alerta que existiam antes do registro (o `tipo` gravado em alertas
# antigos). Só para o de-para de leitura — não são escolhíveis.
LEGADOS = {"status": "situacao"}


def catalogo(escopo: str | None = None) -> list[Criterio]:
    if escopo is None:
        return list(CRITERIOS)
    return [c for c in CRITERIOS if c.escopo == escopo]


def chaves(escopo: str | None = None) -> set[str]:
    return {c.chave for c in catalogo(escopo)}


def padroes(escopo: str) -> set[str]:
    return {c.chave for c in catalogo(escopo) if c.padrao}


def validar(escolhidos: list[str] | None, escopo: str) -> list[str] | None:
    """Normaliza a escolha do usuário (sem duplicata, na ordem do registro).

    `None` continua `None` — é "os padrões", e gravar a lista expandida
    congelaria a escolha de hoje num monitoramento que nunca a fez.
    """
    if escolhidos is None:
        return None
    validas = chaves(escopo)
    desconhecidas = sorted(set(escolhidos) - validas)
    if desconhecidas:
        raise ValueError(
            f"critério de alerta desconhecido para {escopo}: {', '.join(desconhecidas)}"
        )
    escolha = set(escolhidos)
    return [c.chave for c in CRITERIOS if c.chave in escolha]


def efetivos(escolhidos: list[str] | None, escopo: str) -> set[str]:
    """O que está ligado: a escolha do usuário ou, sem escolha, os padrões.

    Lista VAZIA é escolha legítima ("não quero nenhum") e não vira padrão —
    senão desmarcar tudo religaria o ruído inteiro.
    """
    if escolhidos is None:
        return padroes(escopo)
    return {c for c in escolhidos if c in _POR_CHAVE}


def rotulo(chave: str | None) -> str:
    alvo = LEGADOS.get(chave or "", chave or "")
    criterio = _POR_CHAVE.get(alvo)
    return criterio.rotulo if criterio else (chave or "Alerta")
