"""Fontes habilitadas — o corte de escopo da v1 (TransfereGov + FNS).

Enquanto as demais fontes não estão calibradas contra as APIs vivas, o produto
opera com DUAS fontes: **TransfereGov** (captação) e **FNS** (recebidos). Este
módulo é a fonte de verdade desse recorte — os connectors dos demais provedores
continuam no repositório (registrados, testados, prontos), só não entram na
escolha do usuário nem nas rodadas de coleta.

Dois vocabulários convivem, de propósito:

* **grupo** — o que o usuário escolhe no onboarding ("transferegov", "fns").
  É a granularidade do produto: ninguém precisa saber que TransfereGov são
  quatro connectors distintos.
* **connector id** — o `source_id` de cada connector, que é o que fica gravado
  em `preferencias_usuario.fontes` e o que os serviços de coleta consomem.

`expandir()` faz a ponte na entrada do onboarding, então TODO o resto do sistema
segue falando connector id como sempre falou.

Ligar uma fonte de volta = adicionar o connector aqui (e ao grupo certo); nada
mais no core muda.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Select, or_

# TransfereGov é UM grupo para o usuário e cinco connectors para a ingestão.
#
# `serpro` está aqui de propósito: apesar do source_id, o que ele coleta é o
# painel público da VISÃO GERAL DO TRANSFEREGOV
# (dd-publico.serpro.gov.br/extensions/painel/TransferegovbrVisaoGeral.html) —
# o SERPRO só hospeda. É a via de SCRAPING do TransfereGov, complementar às
# APIs PostgREST, e é de onde vem a execução financeira (empenhado/pago/saldo).
TRANSFEREGOV: tuple[str, ...] = (
    "transferegov_ff",
    "transferegov_esp",
    "transferegov_voluntarias",
    "transferegov_disc",
    "serpro",
)
FNS: tuple[str, ...] = ("fns",)

GRUPOS: dict[str, dict] = {
    "transferegov": {
        "label": "TransfereGov",
        "descricao": "Fundo a Fundo, Especiais, Voluntárias e Discricionárias",
        "connectors": TRANSFEREGOV,
    },
    "fns": {
        "label": "FNS — Fundo Nacional de Saúde",
        "descricao": "Repasses do Fundo Nacional de Saúde ao município",
        "connectors": FNS,
    },
}

#: todos os connector ids em operação
HABILITADAS: tuple[str, ...] = TRANSFEREGOV + FNS

#: fontes cujo connector produz PROPOSTAS (eixo captação)
CAPTACAO: tuple[str, ...] = TRANSFEREGOV

#: fontes cujo connector produz REPASSES (eixo recebidos)
RECEBIDOS: tuple[str, ...] = FNS


def habilitada(fonte: str) -> bool:
    return fonte in HABILITADAS


def expandir(escolhas: list[str] | None) -> list[str]:
    """Escolhas do onboarding → connector ids habilitados.

    Aceita tanto grupo ("transferegov") quanto connector id
    ("transferegov_ff") — o segundo caso cobre perfis gravados antes do corte
    e chamadas diretas à API. Fonte fora do recorte é descartada em silêncio
    (o usuário não escolheu algo inválido: ela apenas não está em operação).
    Ordem estável e sem duplicatas.
    """
    saida: list[str] = []
    for escolha in escolhas or []:
        alvos = GRUPOS[escolha]["connectors"] if escolha in GRUPOS else (escolha,)
        for connector in alvos:
            if habilitada(connector) and connector not in saida:
                saida.append(connector)
    return saida


def grupo_de(fonte: str) -> str | None:
    """Connector id → grupo que o usuário reconhece (None se fora do recorte)."""
    for chave, grupo in GRUPOS.items():
        if fonte in grupo["connectors"]:
            return chave
    return None


def rotulo(fonte: str) -> str:
    """Connector id → rótulo do grupo, para exibição."""
    chave = grupo_de(fonte)
    return GRUPOS[chave]["label"] if chave else fonte


def catalogo() -> list[dict]:
    """Catálogo dos grupos, na ordem em que o onboarding os oferece."""
    return [
        {
            "chave": chave,
            "label": grupo["label"],
            "descricao": grupo["descricao"],
            "connectors": list(grupo["connectors"]),
        }
        for chave, grupo in GRUPOS.items()
    ]


# ── Recorte de fonte (o filtro do trilho lateral) ───────────────────────────
# Irmão do recorte de território (`_territorio.py`): o usuário escolhe no
# onboarding as fontes que acompanha e, no painel, decide QUAIS delas quer ver
# naquele momento. O recorte é global (vale para todas as lentes do menu) e é um
# SUBCONJUNTO — nunca amplia: fonte fora do perfil/plano simplesmente não
# devolve linha, porque a coleta nunca a gravou para este usuário.
#
# O vocabulário da ENTRADA é o do usuário (grupo: "transferegov", "fns"); a
# consulta fala connector id. `recorte()` faz a ponte com o mesmo `expandir()`
# do onboarding, então a tela nunca precisa saber que TransfereGov são cinco
# connectors.

#: um grupo, um connector id, vários, ou nada (todas as fontes)
Fontes = str | Sequence[str] | None


def recorte(valor: Fontes) -> list[str]:
    """Normaliza o filtro para uma lista de CONNECTOR IDS (vazia = sem recorte).

    Aceita grupo e connector id misturados (o painel manda grupo; chamadas
    diretas à API e perfis antigos mandam connector id). Fonte fora do recorte
    em operação é descartada em silêncio — ela não existe, e não é o usuário que
    escolheu algo inválido.
    """
    if valor is None:
        return []
    brutos: Sequence[Any] = [valor] if isinstance(valor, str) else list(valor)
    return expandir([str(b).strip() for b in brutos if str(b).strip()])


def condicao(coluna: ColumnElement[Any], valor: Fontes) -> ColumnElement[bool] | None:
    """Condição SQL do recorte de fonte, ou None quando não há recorte.

    O recorte só manda DENTRO do universo que o seletor oferece (`HABILITADAS`).
    Linha de fonte fora desse universo passa intacta — senão escolher
    "TransfereGov" zeraria obras e conformidade, que vêm de connectors que o
    seletor sequer lista: o usuário teria filtrado a captação e visto sumir um
    eixo que não tem nada a ver com a escolha dele.

    ATENÇÃO: uma escolha que expande para NADA (grupo desconhecido, fonte
    desligada) não pode virar "sem recorte" — isso devolveria todo o universo
    justamente quando o usuário pediu um subconjunto dele.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    escolhidos = recorte(valor)
    fora_do_universo = coluna.notin_(HABILITADAS)
    if not escolhidos:
        return fora_do_universo  # pedido explícito que não casa nenhuma fonte
    return or_(coluna.in_(escolhidos), fora_do_universo)


def filtrar(stmt: Select[Any], coluna: ColumnElement[Any], valor: Fontes) -> Select[Any]:
    """Aplica o recorte de fonte na query (nenhuma, uma ou várias)."""
    cond = condicao(coluna, valor)
    return stmt.where(cond) if cond is not None else stmt
