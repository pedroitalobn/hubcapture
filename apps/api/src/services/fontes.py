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
