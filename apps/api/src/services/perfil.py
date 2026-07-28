"""Serviço de perfil — a navegação parte do usuário, não da fonte de dados.

`get_perfil` devolve o território (municípios de interesse), áreas e papel.
`visao_geral` agrega as dimensões do ciclo (captação/recebidos/conformidade/
obras) JÁ filtradas pelo território do usuário — o RLS de cada tabela cache-
global restringe ao(s) município(s) do usuário, então basta contar/somar aqui.
Nenhuma consulta é feita "por fonte": o recorte é sempre o perfil.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.conformidade import Conformidade
from ..models.municipio_interesse import MunicipioInteresse
from ..models.obra import Obra
from ..models.preferencias import PreferenciasUsuario
from ..models.proposta import Proposta
from ..models.repasse import Repasse
from ..models.sync_run import SyncRun
from ..models.usuario import Usuario
from ..schemas.perfil import (
    DimensaoResumo,
    MunicipioPerfil,
    NovidadeItem,
    NovidadesPerfil,
    PerfilRead,
    SyncRunStatus,
    VisaoGeralPerfil,
)

# Áreas de interesse → fontes que as servem. Usado só como RECORTE do feed de
# novidades (a navegação continua profile-centric; fonte nunca vira aba).
AREA_FONTES: dict[str, set[str]] = {
    "saude": {"fns", "sismob"},
    "educacao": {"fnde", "simec"},
    "infraestrutura": {"caixa", "transferegov_esp"},
    "assistencia_social": {"transferegov_ff"},
    "cultura": {"transferegov_voluntarias"},
    "esporte": {"transferegov_voluntarias"},
    "meio_ambiente": {"transferegov_voluntarias"},
    "agricultura": {"transferegov_voluntarias"},
}


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

    # Obras (execução) — destaque é o que está em andamento.
    obras_n = (await session.execute(select(func.count(Obra.id)))).scalar_one()
    obras_exec = (
        await session.execute(
            select(func.count(Obra.id)).where(Obra.situacao == "em_execucao")
        )
    ).scalar_one()

    dimensoes = [
        DimensaoResumo(
            chave="captacao",
            titulo="Captação",
            total=int(prop_n),
            destaque=f"{_brl(prop_valor)} em propostas" if prop_n else "sem propostas ainda",
            href="/panel/funding",
        ),
        DimensaoResumo(
            chave="recebidos",
            titulo="Recursos recebidos",
            total=int(rep_n),
            destaque=f"{_brl(rep_valor)} recebidos" if rep_n else "sem repasses ainda",
            href="/panel/transfers",
        ),
        DimensaoResumo(
            chave="conformidade",
            titulo="Conformidade fiscal",
            total=int(conf_n),
            destaque=(
                f"{conf_pendentes} a comprovar" if conf_n else "sem dados fiscais ainda"
            ),
            href="/panel/compliance",
        ),
        DimensaoResumo(
            chave="obras",
            titulo="Obras",
            total=int(obras_n),
            destaque=(
                f"{obras_exec} em execução" if obras_n else "sem obras ainda"
            ),
            href="/panel/works",
        ),
    ]

    return VisaoGeralPerfil(
        papel=usuario.papel,
        municipios=municipios,
        areas=list(pref.areas or []) if pref else [],
        dimensoes=dimensoes,
    )


def _fontes_do_perfil(pref: PreferenciasUsuario | None) -> set[str]:
    """Recorte de fontes do feed: as escolhidas no onboarding + as das áreas."""
    if pref is None:
        return set()
    fontes = set(pref.fontes or [])
    for area in pref.areas or []:
        fontes |= AREA_FONTES.get(area, set())
    return fontes


async def novidades(
    session: AsyncSession, usuario: Usuario, *, limite: int = 20
) -> NovidadesPerfil:
    """Últimas novidades do território: propostas (captação) e verbas (recebidos).

    O RLS já recorta pelo(s) município(s) do usuário; aqui aplicamos o recorte
    fino do perfil (fontes escolhidas + fontes das áreas de interesse) e
    intercalamos os dois eixos por data, mais recente primeiro.
    """
    pref = await _preferencias(session, usuario.id)
    fontes = _fontes_do_perfil(pref)

    stmt_p = select(Proposta).order_by(
        Proposta.cache_atualizado_em.desc().nullslast()
    )
    stmt_r = select(Repasse).order_by(Repasse.data_repasse.desc().nullslast())
    if fontes:
        stmt_p = stmt_p.where(Proposta.fonte.in_(fontes))
        stmt_r = stmt_r.where(Repasse.fonte.in_(fontes))

    propostas = (await session.execute(stmt_p.limit(limite))).scalars().all()
    repasses = (await session.execute(stmt_r.limit(limite))).scalars().all()

    itens = [
        NovidadeItem(
            tipo="captacao",
            titulo=p.titulo or p.objeto or f"Proposta {p.numero_proposta or p.id_externo}",
            descricao=p.situacao or p.movimentacao,
            valor=p.valor_total,
            data=p.data_atualizacao_fonte
            or (p.cache_atualizado_em.date() if p.cache_atualizado_em else None),
            fonte=p.fonte,
            municipio_ibge=p.municipio_ibge,
            municipio_nome=p.municipio_nome,
            href="/panel/funding",
        )
        for p in propostas
    ] + [
        NovidadeItem(
            tipo="recebido",
            titulo=r.descricao or r.categoria or "Repasse recebido",
            descricao=r.orgao_superior,
            valor=r.valor,
            data=r.data_repasse,
            fonte=r.fonte,
            municipio_ibge=r.municipio_ibge,
            municipio_nome=r.municipio_nome,
            href="/panel/transfers",
        )
        for r in repasses
    ]
    itens = sorted(itens, key=lambda i: i.data or date.min, reverse=True)[:limite]

    # Estado honesto da coleta: últimas execuções por fonte deste usuário.
    runs = (
        (
            await session.execute(
                select(SyncRun)
                .where(SyncRun.usuario_id == usuario.id)
                .order_by(SyncRun.iniciado_em.desc().nullslast())
                .limit(12)
            )
        )
        .scalars()
        .all()
    )
    vistos: set[str] = set()
    sync_runs: list[SyncRunStatus] = []
    for run in runs:
        if run.fonte in vistos:
            continue  # só a execução mais recente de cada fonte
        vistos.add(run.fonte or "")
        sync_runs.append(SyncRunStatus.model_validate(run))

    return NovidadesPerfil(itens=itens, sync_runs=sync_runs)
