"""Serviço de perfil — a navegação parte do usuário, não da fonte de dados.

`get_perfil` devolve o território (municípios de interesse), áreas e papel.
`visao_geral` agrega as dimensões do ciclo (captação/recebidos/conformidade/
obras) JÁ filtradas pelo território do usuário — o RLS de cada tabela cache-
global restringe ao(s) município(s) do usuário, então basta contar/somar aqui.
Nenhuma consulta é feita "por fonte": o recorte é sempre o perfil.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.conformidade import Conformidade
from ..models.municipio_interesse import MunicipioInteresse
from ..models.preferencias import PreferenciasUsuario
from ..models.proposta import Proposta
from ..models.repasse import Repasse
from ..models.usuario import Usuario
from ..schemas.perfil import (
    DimensaoResumo,
    MunicipioPerfil,
    PerfilRead,
    VisaoGeralPerfil,
)


def _brl(v: Decimal | None) -> str:
    n = float(v or 0)
    return f"R$ {n:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


async def _municipios(session: AsyncSession) -> list[MunicipioPerfil]:
    rows = (
        await session.execute(
            select(MunicipioInteresse).order_by(MunicipioInteresse.nome)
        )
    ).scalars()
    return [MunicipioPerfil.model_validate(m) for m in rows]


async def _preferencias(
    session: AsyncSession, usuario_id
) -> PreferenciasUsuario | None:
    return (
        await session.execute(
            select(PreferenciasUsuario).where(
                PreferenciasUsuario.usuario_id == usuario_id
            )
        )
    ).scalar_one_or_none()


async def get_perfil(session: AsyncSession, usuario: Usuario) -> PerfilRead:
    pref = await _preferencias(session, usuario.id)
    return PerfilRead(
        nome=usuario.nome,
        papel=usuario.papel,
        municipios=await _municipios(session),
        areas=list(pref.areas or []) if pref else [],
        fontes=list(pref.fontes or []) if pref else [],
        monitorar_ativo=bool(pref.monitorar_ativo) if pref else True,
    )


async def visao_geral(session: AsyncSession, usuario: Usuario) -> VisaoGeralPerfil:
    pref = await _preferencias(session, usuario.id)
    municipios = await _municipios(session)

    # Captação (propostas) — RLS já restringe ao território do usuário.
    prop_n, prop_valor = (
        await session.execute(
            select(func.count(Proposta.id), func.coalesce(func.sum(Proposta.valor_total), 0))
        )
    ).one()

    # Recebidos (repasses).
    rep_n, rep_valor = (
        await session.execute(
            select(func.count(Repasse.id), func.coalesce(func.sum(Repasse.valor), 0))
        )
    ).one()

    # Conformidade fiscal — destaque é o que falta comprovar.
    conf_n = (
        await session.execute(select(func.count(Conformidade.id)))
    ).scalar_one()
    conf_pendentes = (
        await session.execute(
            select(func.count(Conformidade.id)).where(
                Conformidade.status == "a_comprovar"
            )
        )
    ).scalar_one()

    dimensoes = [
        DimensaoResumo(
            chave="captacao",
            titulo="Captação",
            total=int(prop_n),
            destaque=f"{_brl(prop_valor)} em propostas" if prop_n else "sem propostas ainda",
            href="/painel/captacao",
        ),
        DimensaoResumo(
            chave="recebidos",
            titulo="Recursos recebidos",
            total=int(rep_n),
            destaque=f"{_brl(rep_valor)} recebidos" if rep_n else "sem repasses ainda",
            href="/painel/repasses",
        ),
        DimensaoResumo(
            chave="conformidade",
            titulo="Conformidade fiscal",
            total=int(conf_n),
            destaque=(
                f"{conf_pendentes} a comprovar" if conf_n else "sem dados fiscais ainda"
            ),
            href="/painel/conformidade",
        ),
        DimensaoResumo(
            chave="obras",
            titulo="Obras",
            total=0,
            destaque="em breve",
            href="/painel/obras",
        ),
    ]

    return VisaoGeralPerfil(
        papel=usuario.papel,
        municipios=municipios,
        areas=list(pref.areas or []) if pref else [],
        dimensoes=dimensoes,
    )
