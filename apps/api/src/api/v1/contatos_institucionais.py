"""Diretório institucional — a relação de gabinetes, assessorias e SEIs.

Ponto 19 do feedback. É lista CURADA de nível-plataforma (igual para todos os
clientes), então usa a sessão de plataforma e não a RLS: não há dono, não há
tenant. Fica sob o mesmo módulo `contatos` da agenda pessoal — é a mesma tela
do gestor, com duas abas.

Este router é registrado ANTES de `contatos`: `/contacts/institutional` precisa
casar antes de `/contacts/{contato_id}`, senão o FastAPI trataria "institutional"
como um UUID de contato e responderia 422.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user, current_superuser
from ...models.usuario import Usuario
from ...schemas.contatos_institucionais import (
    CategoriaInstitucional,
    ContatoInstitucionalRead,
    DiretorioInstitucionalSet,
)
from ...services import contatos_institucionais as service
from ...services.modulos import require_modulo
from ..deps import get_platform_db

router = APIRouter(tags=["contatos-institucionais"])


@router.get(
    "/contacts/institutional",
    response_model=list[ContatoInstitucionalRead],
    dependencies=[Depends(require_modulo("contatos"))],
)
async def listar_institucionais(
    q: str | None = Query(default=None, description="nome, órgão, cargo, e-mail ou nº do SEI"),
    categoria: str | None = Query(default=None, description="chave da categoria"),
    _user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ContatoInstitucionalRead]:
    itens = await service.listar(session, q=q, categoria=categoria)
    return [ContatoInstitucionalRead(**c) for c in itens]


@router.get(
    "/contacts/institutional/categories",
    response_model=list[CategoriaInstitucional],
    dependencies=[Depends(require_modulo("contatos"))],
)
async def listar_categorias(
    _user: Usuario = Depends(current_active_user),
) -> list[CategoriaInstitucional]:
    return [CategoriaInstitucional(chave=c, rotulo=r) for c, r in service.CATEGORIAS]


# ── Administração do diretório ────────────────────────────────────────────
# Sem gate de módulo: o admin precisa poder preparar a lista mesmo com o eixo
# desligado para os usuários (mesma disciplina do painel de configuração).


@router.get("/admin/contacts/institutional", response_model=list[ContatoInstitucionalRead])
async def admin_listar(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ContatoInstitucionalRead]:
    return [ContatoInstitucionalRead(**c) for c in await service.listar(session)]


@router.put("/admin/contacts/institutional", response_model=list[ContatoInstitucionalRead])
async def admin_definir(
    body: DiretorioInstitucionalSet,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ContatoInstitucionalRead]:
    """Substitui o diretório inteiro — a tela do admin manda a lista completa."""
    await service.definir(session, [c.model_dump() for c in body.contatos])
    return [ContatoInstitucionalRead(**c) for c in await service.listar(session)]
