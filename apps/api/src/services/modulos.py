"""Módulos da plataforma — liga/desliga eixos do produto em runtime (admin).

Cada módulo é uma LENTE do painel (captação/recebidos/conformidade/obras/
copiloto). O estado vive na tabela `configuracoes` (nível-plataforma, chave
`modulo_<nome>`), com default no registro abaixo — desligar um módulo esconde
a dimensão do perfil/menu e faz os endpoints do eixo responderem 404, sem
redeploy. Conformidade e obras nascem DESATIVADOS (reativar pelo painel).
"""

from __future__ import annotations

import time

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import SessionLocal
from ..models.configuracao import Configuracao

_PREFIXO = "modulo_"
_CATEGORIA = "modulos"

# O guard `require_modulo` roda em TODA request dos routers guardados — sem
# cache, cada request pagava uma sessão de banco só para ler o estado dos
# módulos. TTL curto: um toggle no painel admin propaga em segundos.
_CACHE_TTL = 10.0
_cache_ativos: tuple[float, dict[str, bool]] | None = None


def limpar_cache() -> None:
    """Invalida o snapshot (chamado ao definir módulo; testes/ops)."""
    global _cache_ativos
    _cache_ativos = None

# Registro dos módulos com o estado padrão (sem linha no banco → vale o padrão).
MODULOS: list[dict] = [
    {
        "chave": "captacao",
        "label": "Captação",
        "descricao": "Propostas e editais (TransfereGov, FNS, FNDE…)",
        "padrao": True,
    },
    {
        "chave": "recebidos",
        "label": "Recursos recebidos",
        "descricao": "Repasses recebidos (FPM, emendas, fundos)",
        # Desligado por ora (foco na validação da Captação). Reative pelo painel
        # admin → Módulos quando quiser — o toggle sobrescreve este default.
        "padrao": False,
    },
    {
        "chave": "conformidade",
        "label": "Conformidade fiscal",
        "descricao": "CAUC/CAPAG — pendências e capacidade de pagamento",
        "padrao": False,
    },
    {
        "chave": "obras",
        "label": "Obras",
        "descricao": "Execução de obras (SISMOB, SIMEC, CAIXA)",
        "padrao": False,
    },
    {
        "chave": "contatos",
        "label": "Agenda de contatos",
        "descricao": "Contatos do gestor sincronizados com Google, Apple e Outlook",
        "padrao": True,
    },
    {
        "chave": "copiloto",
        "label": "Copiloto",
        "descricao": "Chat com IA sobre as propostas e base de conhecimento",
        "padrao": True,
    },
    {
        "chave": "assessoria",
        "label": "Assessoria",
        "descricao": "Dúvidas orçamentárias direto com a assessoria pelo WhatsApp",
        "padrao": True,
    },
    {
        # chave interna estável (config `modulo_ajuda` pode já existir no banco);
        # o nome de produto é Class — rotas /class, página /panel/class.
        "chave": "ajuda",
        "label": "Class",
        "descricao": "Class (help desk) — artigos, módulos de aulas, vídeos e hints (ⓘ) nas telas",
        "padrao": True,
    },
]
_POR_CHAVE = {m["chave"]: m for m in MODULOS}


def modulo_valido(chave: str) -> bool:
    return chave in _POR_CHAVE


async def ativos(session: AsyncSession) -> dict[str, bool]:
    """Estado efetivo de todos os módulos (banco > padrão do registro)."""
    rows = (
        await session.execute(select(Configuracao).where(Configuracao.chave.like(f"{_PREFIXO}%")))
    ).scalars()
    no_banco = {r.chave.removeprefix(_PREFIXO): r.valor for r in rows}
    return {
        m["chave"]: (
            no_banco[m["chave"]] == "on"
            if m["chave"] in no_banco and no_banco[m["chave"]] is not None
            else bool(m["padrao"])
        )
        for m in MODULOS
    }


async def listar(session: AsyncSession) -> list[dict]:
    """Catálogo dos módulos com o estado efetivo (para o painel admin)."""
    estado = await ativos(session)
    return [{**m, "ativo": estado[m["chave"]]} for m in MODULOS]


async def definir(session: AsyncSession, chave: str, ativo: bool) -> None:
    """Liga/desliga um módulo conhecido (upsert em `configuracoes`)."""
    meta = _POR_CHAVE[chave]
    valor = "on" if ativo else "off"
    stmt = (
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
    await session.execute(stmt)
    limpar_cache()


async def esta_ativo(chave: str) -> bool:
    """Acesso runtime com snapshot cacheado (guards de endpoint)."""
    global _cache_ativos
    agora = time.monotonic()
    if _cache_ativos is not None and agora - _cache_ativos[0] < _CACHE_TTL:
        return _cache_ativos[1].get(chave, False)
    try:
        async with SessionLocal() as s:
            estado = await ativos(s)
    except Exception:  # noqa: BLE001 — banco fora do ar não derruba a navegação
        estado = {m["chave"]: bool(m["padrao"]) for m in MODULOS}
    _cache_ativos = (agora, estado)
    return estado.get(chave, False)


def require_modulo(chave: str):
    """Dependency de router: módulo desligado → 404 (o eixo some da API)."""

    async def _dep() -> None:
        if not await esta_ativo(chave):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"MODULO_DESATIVADO: {chave}")

    return _dep
