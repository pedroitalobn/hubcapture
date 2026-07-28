"""Painel informativo — notícias oficiais do TransfereGov (gov.br)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ...core.users import current_active_user
from ...models.usuario import Usuario
from ...services import noticias as service

router = APIRouter(tags=["noticias"])


class NoticiaRead(BaseModel):
    titulo: str
    url: str
    data: str | None = None
    resumo: str | None = None


@router.get("/noticias", response_model=list[NoticiaRead])
async def listar_noticias(
    limite: int = Query(default=10, ge=1, le=50),
    _user: Usuario = Depends(current_active_user),
) -> list[NoticiaRead]:
    itens = await service.listar(limite=limite)
    return [NoticiaRead(titulo=n.titulo, url=n.url, data=n.data, resumo=n.resumo) for n in itens]
