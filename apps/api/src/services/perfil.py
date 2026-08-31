"""Serviço de perfil — a navegação parte do usuário, não da fonte de dados.

`get_perfil` devolve o território (municípios de interesse), áreas e papel.
`visao_geral` agrega as dimensões do ciclo (captação/recebidos/conformidade/
obras) JÁ filtradas pelo território do usuário — o RLS de cada tabela cache-
global restringe ao(s) município(s) do usuário, então basta contar/somar aqui.
Nenhuma consulta é feita "por fonte": o recorte é sempre o perfil.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlencode
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.alerta import Alerta
from ..models.audit_log import AuditLog
from ..models.conformidade import Conformidade
from ..models.favorito import Favorito
from ..models.monitoramento import Monitoramento, MonitoramentoBusca
from ..models.municipio_interesse import MunicipioInteresse
from ..models.obra import Obra
from ..models.pasta import Pasta
from ..models.preferencias import PreferenciasUsuario
from ..models.proposta import Proposta
from ..models.repasse import Repasse
from ..models.sync_run import SyncRun
from ..models.usuario import Usuario
from ..schemas.perfil import (
    AnoDisponivel,
    DimensaoResumo,
    MunicipioPerfil,
    NovidadeItem,
    NovidadesPerfil,
    OrigemFonte,
    PerfilRead,
    PlanoPerfil,
    QuebraDimensao,
    RemocaoMunicipioResultado,
    ResetPerfilResultado,
    SyncRunStatus,
    VisaoGeralPerfil,
)
from . import fontes as fontes_service
from . import modulos as modulos_service
from . import municipios as municipios_service
from . import plano_gates
from . import propostas as propostas_service
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
#: fontes SETORIAIS por área — o TransfereGov serve todas (não é setorial), e
#: cada fundo entra na sua área com AS DUAS granularidades que publica: o FNS
#: dá repasse (`fns`) e proposta (`fns_propostas`); o FNDE dá liberação.
#: Sem isto, quem escolhe "educação" no onboarding nunca recebia o FNDE.
_AREA_SETORIAIS: dict[str, set[str]] = {
    "saude": {"fns", "fns_propostas"},
    "educacao": {"fnde"},
}

AREA_FONTES: dict[str, set[str]] = {
    area: set(fontes_service.TRANSFEREGOV) | _AREA_SETORIAIS.get(area, set())
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
    # As fontes do perfil são as ESCOLHIDAS no onboarding MAIS as derivadas das
    # ÁREAS de interesse (AREA_FONTES). Sem a segunda parcela, fonte setorial
    # criada depois do onboarding — o FNDE virou grupo próprio quando o gestor
    # já tinha "educação" marcada — nunca chegava a quem já estava cadastrado:
    # ela não entrava na coleta dele nem no filtro de origem, e a plataforma
    # parecia "não ter" um dado que tem. É o mesmo princípio da reexpansão por
    # grupo em `fontes.expandir`: o usuário escolheu o ASSUNTO, não a lista de
    # connectors do dia.
    areas = list(pref.areas or []) if pref else []
    escolhidas = list(pref.fontes or []) if pref else []
    das_areas = sorted({f for a in areas for f in AREA_FONTES.get(a, set())})
    fontes_pref = fontes_service.expandir(escolhidas) or []
    fontes_pref += [f for f in das_areas if f not in fontes_pref]
    return PerfilRead(
        nome=usuario.nome,
        papel=usuario.papel,
        municipios=await _municipios(session),
        areas=areas,
        # fonte escolhida no onboarding que o plano deixou de incluir some da
        # navegação (o dado gravado fica; um upgrade a traz de volta)
        fontes=plano_gates.filtrar_fontes(cfg, fontes_pref),
        # o filtro de origem do trilho oferece exatamente estas opções
        origens=[
            OrigemFonte.model_validate(o)
            for o in fontes_service.origens_do_perfil(plano_gates.filtrar_fontes(cfg, fontes_pref))
        ],
        monitorar_ativo=bool(pref.monitorar_ativo) if pref else True,
        modulos=[
            chave for chave, on in ativos.items() if on and plano_gates.modulo_liberado(cfg, chave)
        ],
        plano=plano,
        demo=bool(getattr(usuario, "is_demo", False)),
    )


# Caches GLOBAIS recortados por município (§4): não pertencem ao usuário, são
# só a cópia local do que a fonte publicou sobre o território dele. `propostas`
# tem soft delete próprio; os demais só perdem o frescor.
_CACHES_DO_TERRITORIO = (Repasse, Conformidade, Obra)


class MunicipioNaoEncontrado(Exception):
    """O IBGE pedido não está no território deste usuário."""


async def remover_municipio(
    session: AsyncSession, usuario: Usuario, ibge: str
) -> RemocaoMunicipioResultado:
    """Tira UM município do território (ponto 01 do feedback do cliente).

    Até aqui o onboarding só INSERIA: quem errou o município, ou deixou de
    acompanhar uma cidade, não tinha caminho — só o `DELETE /profile`, que zera
    o perfil inteiro. Esta é a saída cirúrgica.

    Apaga o que é do TENANT e diz respeito só a este município: a linha do
    território e as buscas monitoradas dele. O que é cache GLOBAL — propostas,
    repasses, conformidades, obras — não é tocado: a mesma cidade pode estar no
    território de outro cliente, e o cascade das FKs ignora RLS (§41). Sair do
    território já esconde tudo pelo próprio RLS.

    Favoritos e pastas ficam de pé de propósito: se o município voltar, a
    curadoria volta com ele — e, enquanto fora, o RLS não os deixa aparecer.
    """
    alvo = str(ibge or "").strip()
    existe = (
        await session.execute(
            select(MunicipioInteresse.ibge).where(
                MunicipioInteresse.usuario_id == usuario.id,
                MunicipioInteresse.ibge == alvo,
            )
        )
    ).scalar_one_or_none()
    if existe is None:
        raise MunicipioNaoEncontrado(alvo)

    buscas = await session.execute(
        delete(MonitoramentoBusca).where(
            MonitoramentoBusca.usuario_id == usuario.id,
            MonitoramentoBusca.municipio_ibge == alvo,
        )
    )
    await session.execute(
        delete(MunicipioInteresse).where(
            MunicipioInteresse.usuario_id == usuario.id,
            MunicipioInteresse.ibge == alvo,
        )
    )

    # A memória de coleta em processo acompanha: sem isso, readicionar o
    # município logo depois não recoletaria nada por até 6h (§38) e a tela
    # abriria vazia como se a cidade não tivesse dados.
    from . import consulta_avulsa  # import tardio: consulta_avulsa usa AREA_FONTES

    consulta_avulsa.esquecer_municipio(alvo)

    session.add(
        AuditLog(usuario_id=usuario.id, acao="remover_municipio", entidade=f"municipio:{alvo}")
    )
    return RemocaoMunicipioResultado(ibge=alvo, buscas_monitoradas=int(buscas.rowcount or 0))


async def zerar(session: AsyncSession, usuario: Usuario) -> ResetPerfilResultado:
    """Zona de perigo: devolve a conta ao estado PRÉ-ONBOARDING.

    Apaga o que é do usuário — território, preferências e toda a curadoria
    (favoritos, pastas, monitoramentos, buscas monitoradas e alertas). Login,
    dados da conta e agenda de contatos ficam: zerar o perfil não é excluir a
    conta.

    As propostas do território são zeradas por SOFT DELETE (`excluido_em`), e
    os demais caches (repasses, conformidades, obras) perdem o frescor. Nada é
    apagado do banco: o cache é global (§4) — outro usuário pode acompanhar o
    mesmo município — e as FKs `ON DELETE CASCADE` ignoram RLS, então um DELETE
    levaria junto o favorito, a pasta e o monitoramento DELE. Marcada, a linha
    some do painel (os serviços de leitura filtram `excluido_em IS NULL`) e a
    coleta seguinte a RESSUSCITA quando a fonte ainda a publica.
    """
    ibges = list(
        (
            await session.execute(
                select(MunicipioInteresse.ibge).where(MunicipioInteresse.usuario_id == usuario.id)
            )
        )
        .scalars()
        .all()
    )

    # ORDEM IMPORTA: o cache é zerado ENQUANTO o território ainda existe. Os
    # UPDATEs têm WHERE, então leem linha — e leitura passa pela policy de
    # SELECT, que só enxerga município em `municipios_interesse`. Apagando o
    # território antes, nada seria encontrado e o cache ficaria fresco para
    # sempre (a próxima coleta serviria dados velhos).
    propostas_n = 0
    invalidado = 0
    if ibges:  # sem território não há o que zerar (e um IN vazio é perigoso)
        result = await session.execute(
            update(Proposta)
            .where(Proposta.municipio_ibge.in_(ibges))
            .values(excluido_em=datetime.now(UTC), cache_atualizado_em=None)
        )
        propostas_n = int(result.rowcount or 0)
        for model in _CACHES_DO_TERRITORIO:
            result = await session.execute(
                update(model)
                .where(model.municipio_ibge.in_(ibges))
                .values(cache_atualizado_em=None)
            )
            invalidado += int(result.rowcount or 0)
        # a memória de coleta em processo acompanha: senão a busca ao vivo
        # pularia essas fontes por até 6h e o onboarding novo abriria vazio
        from . import consulta_avulsa  # import tardio: consulta_avulsa usa AREA_FONTES

        for ibge in ibges:
            consulta_avulsa.esquecer_municipio(ibge)

    async def _apagar(model: Any, coluna: ColumnElement[Any]) -> int:
        # o RLS FOR ALL já escopa ao tenant da sessão; o filtro explícito é
        # cinto-e-suspensório — numa operação destrutiva o alcance fica no SQL
        result = await session.execute(delete(model).where(coluna == usuario.id))
        return int(result.rowcount or 0)

    alertas_n = await _apagar(Alerta, Alerta.usuario_id)
    monitoramentos_n = await _apagar(Monitoramento, Monitoramento.usuario_id)
    monitoramentos_n += await _apagar(MonitoramentoBusca, MonitoramentoBusca.usuario_id)
    favoritos_n = await _apagar(Favorito, Favorito.usuario_id)
    pastas_n = await _apagar(Pasta, Pasta.usuario_id)  # pasta_propostas cascateia
    await _apagar(PreferenciasUsuario, PreferenciasUsuario.usuario_id)
    municipios_n = await _apagar(MunicipioInteresse, MunicipioInteresse.usuario_id)

    session.add(AuditLog(usuario_id=usuario.id, acao="zerar_perfil", entidade="perfil"))

    return ResetPerfilResultado(
        municipios=municipios_n,
        propostas=propostas_n,
        favoritos=favoritos_n,
        pastas=pastas_n,
        monitoramentos=monitoramentos_n,
        alertas=alertas_n,
        cache_invalidado=invalidado,
    )


def _safras(ano: str | Sequence[str] | None) -> list[str]:
    """Normaliza o filtro de safra: um ano, vários ou nenhum → lista limpa.

    Multi-seleção como o município (§33): o painel soma safras repetindo o
    parâmetro. Valor que não é AAAA é descartado aqui — a validação fina saiu
    do router quando o parâmetro virou lista.
    """
    brutos = [ano] if isinstance(ano, str) else list(ano or [])
    vistos: list[str] = []
    for a in brutos:
        valor = str(a).strip()
        if len(valor) == 4 and valor.isdigit() and valor not in vistos:
            vistos.append(valor)
    return vistos


def _qs_anos(anos: list[str]) -> str:
    """Sufixo `&ano=…` repetido — a safra viaja para os links da captação."""
    return "".join(f"&ano={a}" for a in anos)


async def visao_geral(
    session: AsyncSession,
    usuario: Usuario,
    *,
    municipios_filtro: Municipios = None,
    fontes_filtro: fontes_service.Fontes = None,
    ano: str | Sequence[str] | None = None,
) -> VisaoGeralPerfil:
    """'Meu painel' por dimensão. `municipios_filtro` recorta o território para
    os municípios que o usuário escolheu ver AGORA (subconjunto do onboarding).

    `ano` recorta a safra nas dimensões que TÊM safra — captação (ano da
    proposta) e recebidos (ano do repasse) — e aceita VÁRIAS safras (parâmetro
    repetido), somando os recortes. Conformidade e obras são estado ATUAL do
    município, não fluxo anual: continuam inteiras e se anunciam assim
    (`recorte_ano=False`), em vez de fingir um recorte que não existe.

    `fontes_filtro` é a ORIGEM DO RECURSO escolhida no trilho (grupo, §30) e
    recorta as dimensões cujo dado vem dessas fontes — captação e recebidos.
    Conformidade (Siconfi/CAUC) e obras (SISMOB/SIMEC/CAIXA) não saem do
    catálogo de origens do gestor: aplicar o recorte nelas as zeraria sempre,
    o que seria mentira, não filtro.
    """
    anos = _safras(ano)
    origens = fontes_service.connectors(fontes_filtro)
    pref = await _preferencias(session, usuario.id)
    municipios = await _municipios(session, municipios_filtro)
    # O Meu painel é INDEPENDENTE dos módulos (§40): os módulos ligam/desligam
    # a EXPLORAÇÃO de cada eixo (as páginas, os filtros, a consulta ativa), mas
    # o dado do território que já está no cache continua sendo do painel. A
    # regra por dimensão: módulo ativo → card com link; módulo desligado mas
    # COM dado no cache → card informativo (href None); desligado e sem dado →
    # fora da visão (não há o que mostrar).
    ativos = await modulos_service.ativos(session)
    cfg, _ = await _config_plano(session, usuario)
    ativos = {chave: on and plano_gates.modulo_liberado(cfg, chave) for chave, on in ativos.items()}

    def _no_territorio(stmt: Select[Any], coluna: ColumnElement[Any]) -> Select[Any]:
        """Recorte do painel sobre o que o RLS já limitou ao território."""
        return filtrar_municipio(stmt, coluna, municipios_filtro)

    dimensoes: list[DimensaoResumo] = []

    def _dimensao(
        chave: str,
        titulo: str,
        total: int,
        destaque: str,
        href: str,
        quebras: list[QuebraDimensao] | None = None,
        recorte_ano: bool = True,
    ) -> None:
        if not ativos.get(chave) and not total:
            return
        ativo = bool(ativos.get(chave))
        dimensoes.append(
            DimensaoResumo(
                chave=chave,
                titulo=titulo,
                total=total,
                destaque=destaque,
                href=href if ativo else None,
                # sem navegação (módulo desligado) a quebra não tem para onde ir
                quebras=(quebras or []) if ativo else [],
                recorte_ano=recorte_ano,
            )
        )

    # Captação (propostas) — RLS já restringe ao território do usuário.
    # Com safra escolhida o recorte sai do SQL: `ano_de` é derivado (ANO_PROP no
    # jsonb, data da proposta, nº da proposta), então quem sabe filtrar é o
    # serviço de propostas — o MESMO critério da lista e do resumo da captação.
    propostas: list[Proposta] = []
    if anos or origens:
        propostas = await propostas_service.listar(
            session, municipio=municipios_filtro, fonte=origens or None, ano=anos
        )
        prop_n = len(propostas)
        prop_valor = sum((p.valor_total or Decimal(0) for p in propostas), Decimal(0))
    else:
        prop_n, prop_valor = (
            await session.execute(
                _no_territorio(
                    select(
                        func.count(Proposta.id),
                        func.coalesce(func.sum(Proposta.valor_total), 0),
                    ).where(Proposta.excluido_em.is_(None)),  # zerada não conta
                    Proposta.municipio_ibge,
                )
            )
        ).one()
    # Quebra por natureza jurídica do proponente — as duas lentes da captação.
    # Derivada de jsonb/registro-fonte, então conta em Python (o recorte já é o
    # território); só vale a pena quando há propostas.
    quebras_captacao: list[QuebraDimensao] = []
    if prop_n:
        if not propostas:
            propostas = list(
                (
                    await session.execute(
                        fontes_service.filtrar(
                            _no_territorio(
                                select(Proposta).where(Proposta.excluido_em.is_(None)),
                                Proposta.municipio_ibge,
                            ),
                            Proposta.fonte,
                            origens,
                        )
                    )
                )
                .scalars()
                .all()
            )
        contagem = Counter(propostas_service.grupo_natureza_de(p) for p in propostas)
        quebras_captacao = [
            QuebraDimensao(
                chave=slug,
                rotulo=rotulo,
                total=contagem.get(slug, 0),
                # a safra viaja junto: o card e a lista da captação mostram o
                # mesmo recorte quando o usuário clica na quebra
                href=f"/panel/funding?natureza_grupo={slug}" + _qs_anos(anos),
            )
            for slug, rotulo in propostas_service.GRUPOS_NATUREZA
        ]

    _dimensao(
        "captacao",
        "Propostas",
        int(prop_n),
        # O card mostra só a CONTAGEM: o valor somado no destaque dizia pouco
        # (soma de propostas em estágios diferentes) e competia com o Panorama
        # financeiro logo abaixo, que é onde o dinheiro é lido.
        "" if prop_n else "sem propostas ainda",
        "/panel/funding" + (f"?{_qs_anos(anos)[1:]}" if anos else ""),
        quebras_captacao,
    )

    # Recebidos (repasses) — safra é o ano do pagamento (sem data, a competência).
    stmt_rep = fontes_service.filtrar(
        _no_territorio(
            select(func.count(Repasse.id), func.coalesce(func.sum(Repasse.valor), 0)),
            Repasse.municipio_ibge,
        ),
        Repasse.fonte,
        origens,
    )
    if anos:
        stmt_rep = stmt_rep.where(
            or_(
                func.extract("year", Repasse.data_repasse).in_([int(a) for a in anos]),
                and_(
                    Repasse.data_repasse.is_(None),
                    or_(*[Repasse.competencia.like(f"{a}%") for a in anos]),
                ),
            )
        )
    rep_n, rep_valor = (await session.execute(stmt_rep)).one()
    _dimensao(
        "recebidos",
        "Recursos recebidos",
        int(rep_n),
        f"{_brl(rep_valor)} recebidos" if rep_n else "sem repasses ainda",
        "/panel/transfers",
    )

    # Conformidade fiscal — destaque é o que falta comprovar.
    conf_n = (
        await session.execute(
            _no_territorio(select(func.count(Conformidade.id)), Conformidade.municipio_ibge)
        )
    ).scalar_one()
    if ativos.get("conformidade") or conf_n:
        conf_pendentes = (
            await session.execute(
                _no_territorio(
                    select(func.count(Conformidade.id)).where(Conformidade.status == "a_comprovar"),
                    Conformidade.municipio_ibge,
                )
            )
        ).scalar_one()
        _dimensao(
            "conformidade",
            "Conformidade fiscal",
            int(conf_n),
            f"{conf_pendentes} a comprovar" if conf_n else "sem dados fiscais ainda",
            "/panel/compliance",
            # CAUC/CAPAG é a foto de HOJE do município, não um fluxo anual — a
            # dimensão avisa que ignora a safra em vez de fingir o recorte
            recorte_ano=False,
        )

    # Obras (execução) — destaque é o que está em andamento.
    obras_n = (
        await session.execute(_no_territorio(select(func.count(Obra.id)), Obra.municipio_ibge))
    ).scalar_one()
    if ativos.get("obras") or obras_n:
        obras_exec = (
            await session.execute(
                _no_territorio(
                    select(func.count(Obra.id)).where(Obra.situacao == "em_execucao"),
                    Obra.municipio_ibge,
                )
            )
        ).scalar_one()
        _dimensao(
            "obras",
            "Obras",
            int(obras_n),
            f"{obras_exec} em execução" if obras_n else "sem obras ainda",
            "/panel/works",
            # obra atravessa exercícios (começa num ano, executa noutro): o card
            # mostra o estado atual da carteira, sem recorte por safra
            recorte_ano=False,
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


def _ano_do_repasse(r: Repasse) -> str | None:
    """Safra do repasse: o ano do pagamento; sem data, o da competência."""
    if r.data_repasse:
        return str(r.data_repasse.year)
    competencia = (r.competencia or "").strip()
    if len(competencia) >= 4 and competencia[:4].isdigit():
        return competencia[:4]
    return None


def _ordem_novidade(item: NovidadeItem) -> tuple[str, date]:
    """Chave de ordenação do feed: safra decrescente e, dentro dela, a data.

    Item sem safra definida (proposta sem nenhum sinal de criação na fonte) não
    é jogado para o fim: entra pelo ano da data que temos dele — some da safra
    dos filtros, não da ordem cronológica da lista.
    """
    ano = item.ano or (str(item.data.year) if item.data else "0000")
    return (ano, item.data or date.min)


async def novidades(
    session: AsyncSession,
    usuario: Usuario,
    *,
    limite: int = 20,
    municipios_filtro: Municipios = None,
    fontes_filtro: fontes_service.Fontes = None,
    ano: str | Sequence[str] | None = None,
    estado: str | None = None,
) -> NovidadesPerfil:
    """Últimas novidades do território: propostas (captação) e verbas (recebidos).

    O RLS já recorta pelo(s) município(s) do usuário; aqui aplicamos o recorte
    do painel (`municipios_filtro` — quais dos municípios do perfil o usuário
    quer ver agora) e o recorte fino do perfil (fontes escolhidas + fontes das
    áreas de interesse), intercalando os dois eixos por SAFRA, mais recente
    primeiro.

    `fontes_filtro` é a origem do recurso do trilho: escolher FNS tira do feed
    o que veio das demais fontes — e vale para os DOIS eixos (proposta e
    repasse), porque a origem é do registro, não da lente.

    `ano` filtra pela safra do item — a mesma do resto do app (`ano_de` na
    captação, ano do pagamento nos recebidos) — e aceita VÁRIAS safras
    (parâmetro repetido), somando os recortes. O filtro é aplicado ANTES da
    janela (`limite`): filtrar só o que coube na janela deixava anos anteriores
    permanentemente vazios, porque a janela nunca alcançava esses itens. `anos`
    volta sempre com o território inteiro, para o filtro não perder as opções
    que ele mesmo escondeu.

    `estado` é o recorte dos CARDS do painel (empenhado/publicado/pago, §06):
    clicar no card mostra as propostas que compõem aquele número. Ele vale só
    para o eixo captação — repasse é dinheiro que já caiu, não tem empenho nem
    publicação —, então com o filtro ligado o feed é só de propostas. Como o
    ano, é aplicado ANTES da janela: filtrar depois deixaria o recorte
    permanentemente vazio quando a janela não alcançasse os itens.
    """
    safras = set(_safras(ano))
    pref = await _preferencias(session, usuario.id)
    # o recorte fino do perfil continua valendo; a ORIGEM escolhida no trilho
    # (grupo, §30) INTERSECTA com ele — o filtro da tela nunca amplia o que o
    # perfil deixa ver, só estreita.
    fontes = _fontes_do_perfil(pref)
    origens = set(fontes_service.connectors(fontes_filtro))
    if origens:
        fontes = (fontes & origens) if fontes else origens

    stmt_p = (
        select(Proposta)
        .where(Proposta.excluido_em.is_(None))
        .order_by(Proposta.data_proposta.desc().nullslast())
    )
    stmt_r = select(Repasse).order_by(Repasse.data_repasse.desc().nullslast())
    stmt_p = filtrar_municipio(stmt_p, Proposta.municipio_ibge, municipios_filtro)
    stmt_r = filtrar_municipio(stmt_r, Repasse.municipio_ibge, municipios_filtro)
    if fontes:
        stmt_p = stmt_p.where(Proposta.fonte.in_(fontes))
        stmt_r = stmt_r.where(Repasse.fonte.in_(fontes))

    # A safra da proposta é derivada (ANO_PROP no jsonb, data da proposta, nº)
    # — o SQL não sabe fazer esse recorte, então o território vem inteiro e o
    # filtro/contagem acontecem em Python (mesma disciplina de `propostas.
    # listar`; o recorte já está limitado pelo RLS).
    propostas = list((await session.execute(stmt_p)).scalars().all())
    repasses = list((await session.execute(stmt_r)).scalars().all())

    anos_conta: Counter[str] = Counter()
    for p in propostas:
        safra = propostas_service.ano_de(p)
        if safra:
            anos_conta[safra] += 1
    for r in repasses:
        safra = _ano_do_repasse(r)
        if safra:
            anos_conta[safra] += 1

    if safras:
        propostas = [p for p in propostas if propostas_service.ano_de(p) in safras]
        repasses = [r for r in repasses if _ano_do_repasse(r) in safras]

    if estado in propostas_service.ESTADOS_FINANCEIROS:
        propostas = await propostas_service.filtrar_por_estado(session, propostas, estado)
        repasses = []

    itens = [
        NovidadeItem(
            tipo="captacao",
            titulo=p.titulo or p.objeto or f"Proposta {p.numero_proposta or p.id_externo}",
            descricao=p.situacao or p.movimentacao,
            valor=p.valor_total,
            # a data da PROPOSTA (a mesma safra que a lista da captação mostra);
            # sem ela, a última notícia que temos do item
            data=p.data_proposta
            or p.data_atualizacao_fonte
            or (p.cache_atualizado_em.date() if p.cache_atualizado_em else None),
            ano=propostas_service.ano_de(p),
            fonte=p.fonte,
            fonte_rotulo=fontes_service.rotulo_connector(p.fonte),
            municipio_ibge=p.municipio_ibge,
            municipio_nome=p.municipio_nome,
            uf=p.uf,
            # detalhe da proposta (antes ia pra lista da Captação e "sumia")
            href=f"/panel/funding/{p.id}",
            proposta_id=str(p.id),
            numero_proposta=p.numero_proposta,
        )
        for p in propostas[:limite]
    ] + [
        NovidadeItem(
            tipo="recebido",
            titulo=r.descricao or r.categoria or "Repasse recebido",
            descricao=r.orgao_superior,
            valor=r.valor,
            data=r.data_repasse,
            ano=_ano_do_repasse(r),
            fonte=r.fonte,
            fonte_rotulo=fontes_service.rotulo_connector(r.fonte),
            municipio_ibge=r.municipio_ibge,
            municipio_nome=r.municipio_nome,
            uf=r.uf,
            # o repasse não tem página própria — mas mandar TODOS para a
            # mesma URL nua fazia a tela abrir no recorte padrão, sem relação
            # com a linha clicada ("nada carrega"). O link leva o município e
            # a origem daquele lançamento, então a lente abre no contexto dele.
            href=(
                "/panel/transfers?"
                + urlencode(
                    {
                        k: v
                        for k, v in (
                            ("municipio", r.municipio_ibge),
                            ("fonte", fontes_service.grupo_de(r.fonte) or r.fonte),
                        )
                        if v
                    }
                )
            ),
            documento=r.documento,
        )
        for r in repasses[:limite]
    ]
    itens = sorted(itens, key=_ordem_novidade, reverse=True)[:limite]
    # o município lidera a linha (§35) — o repasse costuma vir da fonte sem
    # nome, e o feed mostrava a linha inteira sem território
    itens = await municipios_service.enriquecer(session, itens)

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

    return NovidadesPerfil(
        itens=itens,
        sync_runs=sync_runs,
        anos=[
            AnoDisponivel(ano=a, total=n)
            for a, n in sorted(anos_conta.items(), key=lambda kv: kv[0], reverse=True)
        ],
    )
