"""Módulos da plataforma — liga/desliga eixos do produto em runtime (admin).

Cada módulo é uma LENTE do painel (captação/recebidos/conformidade/obras/
copiloto). O estado vive na tabela `configuracoes` (nível-plataforma, chave
`modulo_<nome>`), com default no registro abaixo — desligar um módulo esconde
a dimensão do perfil/menu e faz os endpoints do eixo responderem 404, sem
redeploy. Conformidade e obras nascem DESATIVADOS (reativar pelo painel).
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import SessionLocal
from ..models.configuracao import Configuracao

_PREFIXO = "modulo_"
_CATEGORIA = "modulos"

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
        "padrao": True,
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
        "chave": "copiloto",
        "label": "Copiloto",
        "descricao": "Chat com IA sobre as propostas e base de conhecimento",
        "padrao": True,
    },
]
_POR_CHAVE = {m["chave"]: m for m in MODULOS}


def modulo_valido(chave: str) -> bool:
    return chave in _POR_CHAVE


async def ativos(session: AsyncSession) -> dict[str, bool]:
    """Estado efetivo de todos os módulos (banco > padrão do registro)."""
    rows = (
        await session.execute(
            select(Configuracao).where(Configuracao.chave.like(f"{_PREFIXO}%"))
        )
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


async def esta_ativo(chave: str) -> bool:
    """Acesso runtime com sessão própria (guards de endpoint)."""
    async with SessionLocal() as s:
        return (await ativos(s)).get(chave, False)


def require_modulo(chave: str):
    """Dependency de router: módulo desligado → 404 (o eixo some da API)."""

    async def _dep() -> None:
        if not await esta_ativo(chave):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"MODULO_DESATIVADO: {chave}"
            )

    return _dep
