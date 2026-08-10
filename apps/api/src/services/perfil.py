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
from typing import Any

from sqlalchemy import ColumnElement, Select, func, select
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
    PlanoPerfil,
    SyncRunStatus,
    VisaoGeralPerfil,
)
from . import fontes as fontes_service
from . import modulos as modulos_service
from . import plano_gates
from ._territorio import Municipios
from ._territorio import filtrar as filtrar_municipio

# Áreas de interesse → fontes que as servem. Usado só como RECORTE do feed de
# novidades (a navegação continua profile-centric; fonte nunca vira aba).
#
# Com o recorte de duas fontes (`services/fontes.py`), o TransfereGov atende
# todas as áreas — ele não é setorial — e o FNS entra só na saúde. Quando uma
# fonte setorial voltar (FNDE na educação, CAIXA em infra), é aqui que ela
# reaparece.
AREAS = (
    "saude",
    "educacao",
    "infraestrutura",
    "assistencia_social",
    "cultura",
    "esporte",
    "meio_ambiente",
    "agricultura",
)
AREA_FONTES: dict[str, set[str]] = {
    area: set(fontes_service.TRANSFEREGOV) | ({"fns"} if area == "saude" else set())
    for area in AREAS
}


def _brl(v: Decimal | None) -> str:
    n = float(v or 0)
    return f"R$ {n:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


async def _municipios(
    session: AsyncSession, municipios: Municipios = None
) -> list[MunicipioPerfil]:
    """Território do usuário — inteiro, ou só o recorte escolhido no painel."""
    stmt = select(MunicipioInteresse).order_by(MunicipioInteresse.nome)
    stmt = filtrar_municipio(stmt, MunicipioInteresse.ibge, municipios)
    rows = (await session.execute(stmt)).scalars()
    return [MunicipioPerfil.model_validate(m) for m in rows]


async def municipios_do_recorte(
    session: AsyncSession, municipios: Municipios = None
) -> list[MunicipioPerfil]:
    """Municípios do território — todos, ou só os do recorte ativo no painel."""
    return await _municipios(session, municipios)


async def _preferencias(session: AsyncSession, usuario_id) -> PreferenciasUsuario | None:
    return (
        await session.execute(
            select(PreferenciasUsuario).where(PreferenciasUsuario.usuario_id == usuario_id)
        )
    ).scalar_one_or_none()


async def _config_plano(
    session: AsyncSession, usuario: Usuario
) -> tuple[plano_gates.PlanoConfig, PlanoPerfil | None]:
    """Config do plano do usuário + resumo p/ o front. Superuser não é limitado
    por plano (admin enxerga tudo); sem plano → sem restrição."""
    plano = await plano_gates.plano_do_usuario(session, usuario.id)
    cfg = (
        plano_gates.SEM_RESTRICAO
        if getattr(usuario, "is_superuser", False)
        else plano_gates.normalizar(plano.limites if plano else None)
    )
    grupos = plano_gates.grupos_liberados(cfg)
    resumo = (
        PlanoPerfil(
            nome=plano.nome,
            slug=plano.slug,
            municipios_max=cfg.municipios_max,
            membros_max=cfg.membros_max,
            features=plano_gates.features_efetivas(cfg),
            fontes=sorted(grupos) if grupos is not None else None,
            modulos=sorted(cfg.modulos) if cfg.modulos is not None else None,
        )
        if plano
        else None
    )
    return cfg, resumo


async def get_perfil(session: AsyncSession, usuario: Usuario) -> PerfilRead:
    pref = await _preferencias(session, usuario.id)
    ativos = await modulos_service.ativos(session)
    cfg, plano = await _config_plano(session, usuario)
    fontes_pref = list(pref.fontes or []) if pref else []
    return PerfilRead(
        nome=usuario.nome,
        papel=usuario.papel,
        municipios=await _municipios(session),
        areas=list(pref.areas or []) if pref else [],
        # fonte escolhida no onboarding que o plano deixou de incluir some da
        # navegação (o dado gravado fica; um upgrade a traz de volta)
        fontes=plano_gates.filtrar_fontes(cfg, fontes_pref),
        monitorar_ativo=bool(pref.monitorar_ativo) if pref else True,
        modulos=[
            chave for chave, on in ativos.items() if on and plano_gates.modulo_liberado(cfg, chave)
        ],
        plano=plano,
    )


async def visao_geral(
    session: AsyncSession, usuario: Usuario, *, municipios_filtro: Municipios = None
) -> VisaoGeralPerfil:
    """'Meu painel' por dimensão. `municipios_filtro` recorta o território para
    os municípios que o usuário escolheu ver AGORA (subconjunto do onboarding)."""
    pref = await _preferencias(session, usuario.id)
    municipios = await _municipios(session, municipios_filtro)
    # Módulos desligados no painel admin — ou fora do PLANO do usuário (§39) —
    # nem são consultados nem aparecem.
    ativos = await modulos_service.ativos(session)
    cfg, _ = await _config_plano(session, usuario)
    ativos = {chave: on and plano_gates.modulo_liberado(cfg, chave) for chave, on in ativos.items()}

    def _no_territorio(stmt: Select[Any], coluna: ColumnElement[Any]) -> Select[Any]:
        """Recorte do painel sobre o que o RLS já limitou ao território."""
        return filtrar_municipio(stmt, coluna, municipios_filtro)

    dimensoes: list[DimensaoResumo] = []

    if ativos.get("captacao"):
        # Captação (propostas) — RLS já restringe ao território do usuário.
        prop_n, prop_valor = (
            await session.execute(
                _no_territorio(
                    select(
                        func.count(Proposta.id),
                        func.coalesce(func.sum(Proposta.valor_total), 0),
                    ),
                    Proposta.municipio_ibge,
                )
            )
        ).one()
        dimensoes.append(
            DimensaoResumo(
                chave="captacao",
                titulo="Captação",
                total=int(prop_n),
                destaque=(f"{_brl(prop_valor)} em propostas" if prop_n else "sem propostas ainda"),
                href="/panel/funding",
            )
        )

    if ativos.get("recebidos"):
        # Recebidos (repasses).
        rep_n, rep_valor = (
            await session.execute(
                _no_territorio(
                    select(func.count(Repasse.id), func.coalesce(func.sum(Repasse.valor), 0)),
                    Repasse.municipio_ibge,
                )
            )
        ).one()
        dimensoes.append(
            DimensaoResumo(
                chave="recebidos",
                titulo="Recursos recebidos",
                total=int(rep_n),
                destaque=f"{_brl(rep_valor)} recebidos" if rep_n else "sem repasses ainda",
                href="/panel/transfers",
            )
        )

    if ativos.get("conformidade"):
        # Conformidade fiscal — destaque é o que falta comprovar.
        conf_n = (
            await session.execute(
                _no_territorio(select(func.count(Conformidade.id)), Conformidade.municipio_ibge)
            )
        ).scalar_one()
        conf_pendentes = (
            await session.execute(
                _no_territorio(
                    select(func.count(Conformidade.id)).where(Conformidade.status == "a_comprovar"),
                    Conformidade.municipio_ibge,
                )
            )
        ).scalar_one()
        dimensoes.append(
            DimensaoResumo(
                chave="conformidade",
                titulo="Conformidade fiscal",
                total=int(conf_n),
                destaque=(f"{conf_pendentes} a comprovar" if conf_n else "sem dados fiscais ainda"),
                href="/panel/compliance",
            )
        )

    if ativos.get("obras"):
        # Obras (execução) — destaque é o que está em andamento.
        obras_n = (
            await session.execute(_no_territorio(select(func.count(Obra.id)), Obra.municipio_ibge))
        ).scalar_one()
        obras_exec = (
            await session.execute(
                _no_territorio(
                    select(func.count(Obra.id)).where(Obra.situacao == "em_execucao"),
                    Obra.municipio_ibge,
                )
            )
        ).scalar_one()
        dimensoes.append(
            DimensaoResumo(
                chave="obras",
                titulo="Obras",
                total=int(obras_n),
                destaque=f"{obras_exec} em execução" if obras_n else "sem obras ainda",
                href="/panel/works",
            )
        )

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
    session: AsyncSession,
    usuario: Usuario,
    *,
    limite: int = 20,
    municipios_filtro: Municipios = None,
) -> NovidadesPerfil:
    """Últimas novidades do território: propostas (captação) e verbas (recebidos).

    O RLS já recorta pelo(s) município(s) do usuário; aqui aplicamos o recorte
    do painel (`municipios_filtro` — quais dos municípios do perfil o usuário
    quer ver agora) e o recorte fino do perfil (fontes escolhidas + fontes das
    áreas de interesse), intercalando os dois eixos por data, mais recente
    primeiro.
    """
    pref = await _preferencias(session, usuario.id)
    fontes = _fontes_do_perfil(pref)

    stmt_p = select(Proposta).order_by(Proposta.cache_atualizado_em.desc().nullslast())
    stmt_r = select(Repasse).order_by(Repasse.data_repasse.desc().nullslast())
    stmt_p = filtrar_municipio(stmt_p, Proposta.municipio_ibge, municipios_filtro)
    stmt_r = filtrar_municipio(stmt_r, Repasse.municipio_ibge, municipios_filtro)
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
            # detalhe da proposta (antes ia pra lista da Captação e "sumia")
            href=f"/panel/funding/{p.id}",
            proposta_id=str(p.id),
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
