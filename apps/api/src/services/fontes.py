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

import time
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import SessionLocal
from ..models.configuracao import Configuracao

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

#: FNDE — liberações da educação (SIMAD, consulta pública). Produz REPASSES.
FNDE: tuple[str, ...] = ("fnde",)

GRUPOS: dict[str, dict] = {
    "transferegov": {
        "label": "TransfereGov",
        "descricao": "Fundo a Fundo, Especiais, Voluntárias e Discricionárias",
        "connectors": TRANSFEREGOV,
    },
    "fnde": {
        "label": "FNDE — Fundo Nac. de Desenvolvimento da Educação",
        "descricao": "Liberações do FNDE ao município (salário-educação, PDDE, PNAE…)",
        "connectors": FNDE,
    },
    "fns": {
        "label": "FNS — Fundo Nacional de Saúde",
        "descricao": "Propostas e repasses do Fundo Nacional de Saúde ao município",
        "connectors": FNS,
    },
}

#: todos os connector ids em operação
HABILITADAS: tuple[str, ...] = TRANSFEREGOV + FNS + FNDE

#: fontes cujo connector produz PROPOSTAS (eixo captação)
CAPTACAO: tuple[str, ...] = TRANSFEREGOV + ("fns_propostas",)

#: fontes cujo connector produz REPASSES (eixo recebidos)
RECEBIDOS: tuple[str, ...] = ("fns", "fnde")


# Rótulo de cada CONNECTOR na tela do GESTOR (o grupo tem o seu em GRUPOS). O
# painel mostra a origem do registro linha a linha, e `transferegov_disc` cru
# ali é plumbing de integração vazando para o usuário (§35). Cobre também as
# fontes fora do recorte da v1: o cache guarda o que elas já coletaram.
#
# Não confundir com o `label` de `CATALOGO_FONTES` (mais abaixo), que é do
# painel ADMIN: lá a granularidade é o connector que se pausa, então as duas
# metades do FNS precisam se distinguir ("FNS — repasses" × "FNS — propostas").
# Aqui elas são a mesma fonte para quem lê a lista.
LABELS_CONNECTOR: dict[str, str] = {
    "transferegov_ff": "TransfereGov — Fundo a Fundo",
    "transferegov_esp": "TransfereGov — Especiais",
    "transferegov_voluntarias": "TransfereGov — Voluntárias",
    "transferegov_disc": "TransfereGov — Discricionárias",
    "serpro": "TransfereGov — Visão Geral",
    "fns": "FNS — Fundo Nacional de Saúde",
    "fns_propostas": "FNS — Fundo Nacional de Saúde",
    "fnde": "FNDE — Liberações",
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
        if escolha in GRUPOS:
            alvos: tuple[str, ...] = GRUPOS[escolha]["connectors"]
        else:
            # Connector id gravado no perfil: o que o usuário escolheu foi o
            # GRUPO ("FNS"), e o onboarding congelou a lista de connectors do
            # dia. Quando o grupo ganha uma granularidade nova — o FNS passou a
            # publicar PROPOSTAS além de repasses (§30b) —, o perfil antigo
            # ficaria preso na lista velha: a fonte nova não entraria na coleta
            # dele nem apareceria no filtro de origem, e o gestor veria a
            # plataforma "não ter" um dado que ela tem. Reexpandir pelo grupo
            # mantém a escolha do usuário (o grupo) e acompanha o catálogo.
            grupo = grupo_de(escolha)
            alvos = GRUPOS[grupo]["connectors"] if grupo else (escolha,)
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

# ---------------------------------------------------------------------------
# PAUSA por fonte (runtime, painel admin)
# ---------------------------------------------------------------------------
# Fonte de governo cai, muda de rota ou passa a exigir credencial — e enquanto
# não é recalibrada ela só produz incidente em `sync_runs` e atraso na coleta
# (cada tentativa paga timeout). Pausar é a válvula: o connector continua
# registrado e testável, mas sai das rodadas até alguém religá-lo. Mesmo
# desenho dos módulos (§29): estado em `configuracoes` sob `fonte_<id>`,
# default no catálogo abaixo, cache curto porque a coleta consulta em laço.
_PREFIXO = "fonte_"
_CATEGORIA = "fontes"
_CACHE_TTL = 10.0
_cache_ativas: tuple[float, dict[str, bool]] | None = None

#: rótulo e default de cada connector em operação. `padrao=False` nasce
#: PAUSADA — é o caso da fonte que ainda não passou pela calibração ao vivo.
CATALOGO_FONTES: list[dict] = [
    {"chave": "transferegov_ff", "label": "TransfereGov — Fundo a Fundo", "padrao": True},
    {"chave": "transferegov_esp", "label": "TransfereGov — Especiais", "padrao": True},
    {"chave": "transferegov_disc", "label": "TransfereGov — Discricionárias", "padrao": True},
    {"chave": "transferegov_voluntarias", "label": "TransfereGov — Voluntárias", "padrao": True},
    {"chave": "serpro", "label": "TransfereGov — Painel Visão Geral", "padrao": False},
    {"chave": "fns", "label": "FNS — repasses", "padrao": True},
    {"chave": "fns_propostas", "label": "FNS — propostas", "padrao": True},
    {"chave": "fnde", "label": "FNDE — liberações", "padrao": True},
]

_POR_CHAVE_FONTE = {f["chave"]: f for f in CATALOGO_FONTES}


def limpar_cache_fontes() -> None:
    """Invalida o snapshot de fontes ativas (toggle do painel; testes)."""
    global _cache_ativas
    _cache_ativas = None


async def ativas(session: AsyncSession) -> dict[str, bool]:
    """Estado efetivo de cada fonte do catálogo (banco > padrão)."""
    rows = (
        await session.execute(select(Configuracao).where(Configuracao.chave.like(f"{_PREFIXO}%")))
    ).scalars()
    no_banco = {r.chave.removeprefix(_PREFIXO): r.valor for r in rows}
    return {
        f["chave"]: (
            no_banco[f["chave"]] == "on"
            if f["chave"] in no_banco and no_banco[f["chave"]] is not None
            else bool(f["padrao"])
        )
        for f in CATALOGO_FONTES
    }


async def listar_fontes(session: AsyncSession) -> list[dict]:
    """Catálogo com estado efetivo e o grupo de cada fonte (painel admin)."""
    estado = await ativas(session)
    return [
        {**f, "ativa": estado[f["chave"]], "grupo": grupo_de(f["chave"])}
        for f in CATALOGO_FONTES
    ]


async def definir_fonte(session: AsyncSession, chave: str, ativa: bool) -> None:
    """Pausa/religa uma fonte conhecida (upsert em `configuracoes`)."""
    meta = _POR_CHAVE_FONTE[chave]
    valor = "on" if ativa else "off"
    await session.execute(
        pg_insert(Configuracao)
        .values(
            chave=f"{_PREFIXO}{chave}",
            valor=valor,
            secreto=False,
            cifrado=False,
            categoria=_CATEGORIA,
            descricao=meta["label"],
        )
        .on_conflict_do_update(index_elements=["chave"], set_={"valor": valor})
    )
    limpar_cache_fontes()


async def esta_ativa(fonte: str) -> bool:
    """Acesso runtime com snapshot cacheado (usado dentro das coletas).

    Fonte FORA do catálogo é considerada ativa: o catálogo governa o que se
    pode pausar, não o que existe — connector novo não pode nascer mudo por
    esquecimento de cadastro.
    """
    global _cache_ativas
    agora = time.monotonic()
    if _cache_ativas is None or agora - _cache_ativas[0] >= _CACHE_TTL:
        try:
            async with SessionLocal() as s:
                estado = await ativas(s)
        except Exception:  # noqa: BLE001 — banco fora do ar não paralisa a coleta
            estado = {f["chave"]: bool(f["padrao"]) for f in CATALOGO_FONTES}
        _cache_ativas = (agora, estado)
    return _cache_ativas[1].get(fonte, True)


async def filtrar_ativas(fontes: list[str] | tuple[str, ...]) -> list[str]:
    """Só as fontes que não estão pausadas, na ordem recebida."""
    saida = []
    for f in fontes:
        if await esta_ativa(f):
            saida.append(f)
    return saida
