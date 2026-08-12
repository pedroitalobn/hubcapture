"""Versão de UI ativa na plataforma — flag de porte da Bancada v2 → v1.

O admin escolhe em /admin/config (chave `ui_versao`, categoria `plataforma`);
o web lê aqui SEM autenticação — a flag não é segredo e precisa valer já no
/login, antes de existir sessão. Qualquer valor fora do conjunto conhecido
cai na v2 (a UI atual), para a plataforma nunca quebrar por config inválida.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...services import config as config_service
from ..deps import get_platform_db

router = APIRouter(tags=["ui"])

VERSOES_UI = ("v1", "v2")
VERSAO_PADRAO = "v2"


def versao_ui_efetiva(valor: str | None) -> str:
    """Sanitiza o valor da flag: só v1|v2 valem; o resto cai no padrão."""
    normalizado = (valor or "").strip().lower()
    return normalizado if normalizado in VERSOES_UI else VERSAO_PADRAO


class UiRead(BaseModel):
    versao: str


@router.get("/ui", response_model=UiRead)
async def get_ui(response: Response, session: AsyncSession = Depends(get_platform_db)) -> UiRead:
    # sem no-store o navegador serve a versão anterior do cache heurístico e a
    # troca no painel parece não ter surtido efeito por horas
    response.headers["Cache-Control"] = "no-store"
    return UiRead(versao=versao_ui_efetiva(await config_service.get_valor(session, "ui_versao")))
