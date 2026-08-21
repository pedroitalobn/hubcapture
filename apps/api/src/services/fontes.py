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

from sqlalchemy import ColumnElement, Select

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
# `fns` produz REPASSES (recebidos); `fns_propostas` produz PROPOSTAS
# (captação) — a mesma API do ConsultaFNS em duas granularidades.
FNS: tuple[str, ...] = ("fns", "fns_propostas")

GRUPOS: dict[str, dict] = {
    "transferegov": {
        "label": "TransfereGov",
        "descricao": "Fundo a Fundo, Especiais, Voluntárias e Discricionárias",
        "connectors": TRANSFEREGOV,
    },
    "fns": {
        "label": "FNS — Fundo Nacional de Saúde",
        "descricao": "Propostas e repasses do Fundo Nacional de Saúde ao município",
        "connectors": FNS,
    },
}

#: todos os connector ids em operação
HABILITADAS: tuple[str, ...] = TRANSFEREGOV + FNS

#: fontes cujo connector produz PROPOSTAS (eixo captação)
CAPTACAO: tuple[str, ...] = TRANSFEREGOV + ("fns_propostas",)

#: fontes cujo connector produz REPASSES (eixo recebidos)
RECEBIDOS: tuple[str, ...] = ("fns",)


# Rótulo de cada CONNECTOR (o grupo tem o seu em GRUPOS). O painel mostra a
# origem do registro linha a linha, e `transferegov_disc` cru na tela é
# plumbing de integração vazando para o gestor (§35). Cobre também as fontes
# fora do recorte da v1: o cache guarda o que elas já coletaram.
LABELS_CONNECTOR: dict[str, str] = {
    "transferegov_ff": "TransfereGov — Fundo a Fundo",
    "transferegov_esp": "TransfereGov — Especiais",
    "transferegov_voluntarias": "TransfereGov — Voluntárias",
    "transferegov_disc": "TransfereGov — Discricionárias",
    "serpro": "TransfereGov — Visão Geral",
    "fns": "FNS — Fundo Nacional de Saúde",
    "fns_propostas": "FNS — Fundo Nacional de Saúde",
    "fnde": "FNDE",
    "fpm": "FPM — Fundo de Participação",
    "emendas": "Emendas parlamentares",
    "siconfi": "Siconfi/CAUC",
    "sismob": "SISMOB",
    "simec": "SIMEC",
    "caixa": "CAIXA",
}


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


def rotulo_connector(fonte: str | None) -> str:
    """Connector id → nome legível da fonte daquele registro (nunca o slug)."""
    if not fonte:
        return ""
    return LABELS_CONNECTOR.get(fonte, fonte)


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


# ── Recorte de ORIGEM DO RECURSO (o filtro do painel) ───────────────────────
# Espelho de `services/_territorio.py` para a outra dimensão global do painel:
# lá o usuário escolhe QUAIS dos seus municípios ver agora, aqui QUAIS das suas
# fontes. O vocabulário da escolha é o GRUPO ("transferegov", "fns") — que é o
# que o usuário reconhece (§30) —, mas o dado gravado em `propostas.fonte` /
# `repasses.fonte` é o connector id, então o filtro expande antes de virar SQL.
# Marcar "TransfereGov" sem expandir pescaria só `transferegov_ff` e o painel
# perderia as propostas do CSV das discricionárias — que são a maioria.

#: um grupo, vários, connector ids, ou nada (= todas as fontes do usuário)
Fontes = str | Sequence[str] | None


def connectors(valor: Fontes) -> list[str]:
    """Escolha do painel → connector ids (lista vazia = sem recorte).

    Aceita grupo e connector id na mesma lista. Diferente de `expandir()`, um
    connector id fora do recorte da v1 é PRESERVADO: o cache guarda dado de
    fontes que já rodaram (fpm, emendas…) e filtrar por elas continua sendo
    uma leitura legítima — o recorte de `HABILITADAS` governa a COLETA.
    """
    if valor is None:
        return []
    brutos: Sequence[Any] = [valor] if isinstance(valor, str) else list(valor)
    saida: dict[str, None] = {}  # dedup preservando a ordem de escolha
    for bruto in brutos:
        escolha = str(bruto).strip()
        if not escolha:
            continue
        alvos = GRUPOS[escolha]["connectors"] if escolha in GRUPOS else (escolha,)
        for connector in alvos:
            saida.setdefault(connector, None)
    return list(saida)


def condicao(coluna: ColumnElement[Any], valor: Fontes) -> ColumnElement[bool] | None:
    """Condição SQL do recorte de origem, ou None quando não há recorte."""
    escolhidos = connectors(valor)
    return coluna.in_(escolhidos) if escolhidos else None


def filtrar(stmt: Select[Any], coluna: ColumnElement[Any], valor: Fontes) -> Select[Any]:
    """Aplica o recorte de origem na query (nenhuma, uma ou várias fontes)."""
    recorte = condicao(coluna, valor)
    return stmt.where(recorte) if recorte is not None else stmt


def origens_do_perfil(fontes_perfil: Sequence[str] | None) -> list[dict]:
    """Catálogo de origens que ESTE usuário pode filtrar, na ordem do catálogo.

    O trilho do painel oferece grupo, não connector: o gestor pensa em "FNS",
    não em `fns` × `fns_propostas`. Perfil sem fonte gravada (conta antiga, ou
    onboarding que não escolheu) enxerga o catálogo inteiro — filtro vazio é
    pior que filtro amplo.
    """
    escolhidas = set(fontes_perfil or [])
    grupos = [
        chave
        for chave in GRUPOS
        if not escolhidas or chave in escolhidas or escolhidas & set(GRUPOS[chave]["connectors"])
    ]
    return [
        {
            "chave": chave,
            "label": GRUPOS[chave]["label"],
            "connectors": list(GRUPOS[chave]["connectors"]),
        }
        for chave in grupos
    ]
