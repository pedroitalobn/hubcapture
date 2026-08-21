"""Varredura do usuário: mudanças monitoradas + futuras propostas + oportunidades.

Três detecções, todas na sessão RLS do próprio usuário e todas recortadas pelos
CRITÉRIOS que o usuário escolheu ao configurar o monitoramento (§53) — sem isso
o painel alertava toda e qualquer alteração:

0. **mudança na proposta monitorada** — para cada `monitoramentos` ativo,
   compara a fotografia atual da proposta (`detect_changes.snapshot`) com a
   guardada e emite UM alerta por critério ligado que teve fato novo: parecer,
   empenho, pagamento, publicação, vencimento do convênio, situação, prazo,
   pendência.
1. **nova_proposta** — para cada `monitoramentos_busca` ativo, propostas do
   município (recortadas por fonte/área) que entraram no cache DEPOIS do último
   alerta da busca geram um alerta cada; o cursor `ultimo_alerta_em` avança.
2. **oportunidade** — o alerta do fluxograma "recursos disponíveis com
   propostas não cadastradas": município que RECEBE repasses de uma fonte mas
   não tem nenhuma proposta de captação dessa fonte. Dedup por alerta não-lido
   igual (mesmo município+fonte).

Ao final, os alertas criados são despachados por email/WhatsApp conforme os
`canais` das buscas (painel é implícito — o alerta já está no banco).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.alerta import Alerta
from ..models.monitoramento import Monitoramento, MonitoramentoBusca
from ..models.municipio_interesse import MunicipioInteresse
from ..models.proposta import Proposta
from ..models.repasse import Repasse
from ..models.usuario import Usuario
from ..notifications import email as email_notif
from ..notifications import uniq
from ..notifications.email_templates import alertas_resumo
from . import config as config_service
from . import criterios_alerta, detect_changes, plano_gates
from . import emendas_proposta as emendas_service
from . import empenhos_proposta as empenhos_service
from . import monitoramentos as monitoramentos_service
from . import pareceres as pareceres_service
from .perfil import AREA_FONTES


def _fontes_da_busca(busca: MonitoramentoBusca) -> set[str] | None:
    """Recorte de fontes da busca: fonte explícita > fontes da área > todas."""
    if busca.fonte:
        return {busca.fonte}
    if busca.area:
        return AREA_FONTES.get(busca.area, set()) or None
    return None


async def _mudancas_monitoradas(
    session: AsyncSession, usuario: Usuario
) -> tuple[list[Alerta], set[str]]:
    """Um alerta por CRITÉRIO ligado que teve fato novo na proposta monitorada.

    A fotografia anterior vive em `monitoramentos.snapshot`; a atual é montada
    do cache (a proposta e, só quando o critério pede, pareceres, empenhos e
    emendas — consulta ao vivo é papel da Captação, não da varredura). O
    snapshot é PODADO pelos critérios ligados: campo de critério desligado não
    vira linha de base falsa quando o usuário ligar o critério depois.

    Favoritar é acompanhar: antes de comparar, toda favorita sem monitoramento
    ganha um (`origem='favorito'`), então a novidade que o cron trouxer numa
    proposta favoritada vira alerta sem o gestor precisar configurar nada.
    """
    agora = datetime.now(UTC)
    criados: list[Alerta] = []
    canais: set[str] = set()

    await monitoramentos_service.garantir_das_favoritas(session, usuario.id)

    monitores = (
        (
            await session.execute(
                select(Monitoramento).where(
                    Monitoramento.usuario_id == usuario.id,
                    Monitoramento.ativo.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    for mon in monitores:
        ligados = criterios_alerta.efetivos(mon.criterios, criterios_alerta.ESCOPO_PROPOSTA)
        if not ligados:
            continue  # o usuário desmarcou tudo — monitoramento em silêncio
        proposta = (
            await session.execute(
                select(Proposta).where(
                    Proposta.id == mon.proposta_id,
                    Proposta.excluido_em.is_(None),
                )
            )
        ).scalar_one_or_none()
        if proposta is None:  # fora do território (RLS) ou zerada — nada a comparar
            continue

        pareceres: list = []
        if ligados & {"parecer", "parecer_novo"} and proposta.numero_plano_trabalho:
            pareceres = await pareceres_service.listar(session, proposta.numero_plano_trabalho)
        empenhos: list = []
        if ligados & {"empenho", "empenho_pago"}:
            empenhos = await empenhos_service.listar(session, proposta)
        emendas: list = []
        if "emenda" in ligados:
            emendas = await emendas_service.listar(session, proposta)

        atual = detect_changes.podar(
            detect_changes.snapshot(
                proposta, pareceres=pareceres, empenhos=empenhos, emendas=emendas
            ),
            ligados,
        )
        mudancas = detect_changes.avaliar(mon.snapshot, atual, ligados)
        for mudanca in mudancas:
            alerta = Alerta(
                usuario_id=usuario.id,
                proposta_id=proposta.id,
                tipo=mudanca.criterio,
                payload={
                    **mudanca.payload,
                    "titulo": proposta.titulo or proposta.objeto,
                    "numero_proposta": proposta.numero_proposta,
                    "fonte": proposta.fonte,
                    "municipio_ibge": proposta.municipio_ibge,
                    "municipio_nome": proposta.municipio_nome,
                },
            )
            session.add(alerta)
            criados.append(alerta)
        if mudancas:
            mon.ultimo_alerta_em = agora
            canais.update(mon.canais or [])
        mon.snapshot = atual
    return criados, canais


async def _buscas_ativas(session: AsyncSession, usuario: Usuario) -> list[MonitoramentoBusca]:
    return list(
        (
            await session.execute(
                select(MonitoramentoBusca).where(
                    MonitoramentoBusca.usuario_id == usuario.id,
                    MonitoramentoBusca.ativo.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )


def _criterios_do_territorio(buscas: list[MonitoramentoBusca]) -> set[str]:
    """União dos critérios de território das buscas ativas.

    Sem nenhuma busca configurada valem os padrões — a varredura de
    oportunidade nasceu independente das buscas e continua assim.
    """
    if not buscas:
        return criterios_alerta.padroes(criterios_alerta.ESCOPO_TERRITORIO)
    ligados: set[str] = set()
    for b in buscas:
        ligados |= criterios_alerta.efetivos(b.criterios, criterios_alerta.ESCOPO_TERRITORIO)
    return ligados


async def _novas_propostas(
    session: AsyncSession, usuario: Usuario, buscas: list[MonitoramentoBusca]
) -> tuple[list[Alerta], set[str]]:
    """Alertas 'nova_proposta' para as buscas ativas. Retorna (alertas, canais)."""
    agora = datetime.now(UTC)
    criados: list[Alerta] = []
    canais: set[str] = set()

    for busca in buscas:
        ligados = criterios_alerta.efetivos(busca.criterios, criterios_alerta.ESCOPO_TERRITORIO)
        if "nova_proposta" not in ligados:
            continue  # a busca vigia o território, mas não quer aviso de proposta nova
        corte = busca.ultimo_alerta_em or busca.created_at
        stmt = select(Proposta).where(
            Proposta.excluido_em.is_(None),
            Proposta.municipio_ibge == busca.municipio_ibge,
            Proposta.created_at > corte,
        )
        fontes = _fontes_da_busca(busca)
        if fontes:
            stmt = stmt.where(Proposta.fonte.in_(fontes))
        novas = (await session.execute(stmt)).scalars().all()
        for p in novas:
            alerta = Alerta(
                usuario_id=usuario.id,
                proposta_id=p.id,
                tipo="nova_proposta",
                payload={
                    "titulo": p.titulo or p.objeto or p.id_externo,
                    "fonte": p.fonte,
                    "municipio_ibge": p.municipio_ibge,
                    "municipio_nome": p.municipio_nome,
                    "valor_total": str(p.valor_total) if p.valor_total else None,
                },
            )
            session.add(alerta)
            criados.append(alerta)
        if novas:
            busca.ultimo_alerta_em = agora
            canais.update(busca.canais or [])
    return criados, canais


async def _oportunidades(session: AsyncSession, usuario: Usuario) -> list[Alerta]:
    """Alertas 'oportunidade': repasses recebidos sem proposta cadastrada da fonte."""
    criados: list[Alerta] = []
    municipios = (
        (
            await session.execute(
                select(MunicipioInteresse).where(MunicipioInteresse.usuario_id == usuario.id)
            )
        )
        .scalars()
        .all()
    )
    # payloads de alertas de oportunidade não lidos (dedupe)
    abertos = (
        (
            await session.execute(
                select(Alerta.payload).where(
                    Alerta.usuario_id == usuario.id,
                    Alerta.tipo == "oportunidade",
                    Alerta.lido.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    ja_abertos = {(p.get("municipio_ibge"), p.get("fonte")) for p in abertos if isinstance(p, dict)}

    for m in municipios:
        fontes_recebendo = (
            await session.execute(
                select(Repasse.fonte, func.sum(Repasse.valor))
                .where(Repasse.municipio_ibge == m.ibge)
                .group_by(Repasse.fonte)
            )
        ).all()
        if not fontes_recebendo:
            continue
        fontes_com_proposta = set(
            (
                await session.execute(
                    select(Proposta.fonte).where(Proposta.municipio_ibge == m.ibge).distinct()
                )
            )
            .scalars()
            .all()
        )
        for fonte, total in fontes_recebendo:
            if fonte in fontes_com_proposta or (m.ibge, fonte) in ja_abertos:
                continue
            alerta = Alerta(
                usuario_id=usuario.id,
                proposta_id=None,
                tipo="oportunidade",
                payload={
                    "municipio_ibge": m.ibge,
                    "municipio_nome": m.nome,
                    "fonte": fonte,
                    "valor_recebido": str(total) if total is not None else None,
                    "motivo": "recursos recebidos sem proposta de captação cadastrada",
                },
            )
            session.add(alerta)
            criados.append(alerta)
    return criados


def _linha(alerta: Alerta) -> str:
    p = alerta.payload or {}
    municipio = p.get("municipio_nome") or p.get("municipio_ibge") or "seu município"
    if p.get("resumo"):  # alerta de mudança: o critério + o que mudou
        titulo = p.get("titulo") or p.get("numero_proposta") or "proposta monitorada"
        return f"{criterios_alerta.rotulo(alerta.tipo)} em {municipio}: {titulo} — {p['resumo']}"
    if alerta.tipo == "nova_proposta":
        return f"Nova proposta em {municipio}: {p.get('titulo')} ({p.get('fonte')})"
    if alerta.tipo == "oportunidade":
        return (
            f"Oportunidade em {municipio}: recursos da fonte {p.get('fonte')} "
            "recebidos sem proposta de captação cadastrada"
        )
    return f"Atualização em {municipio}"


async def _despachar(usuario: Usuario, alertas: list[Alerta], canais: set[str]) -> None:
    """Email/WhatsApp best-effort — provider ausente degrada em silêncio."""
    if not alertas:
        return
    linhas = [_linha(a) for a in alertas]
    if "email" in canais and usuario.email:
        base = await config_service.resolver("app_base_url")
        url = f"{base.rstrip('/')}/panel/alerts" if base else None
        assunto, txt, html = alertas_resumo(linhas, url)
        await email_notif.enviar(usuario.email, assunto, txt, html)
    if "wpp" in canais and usuario.optin_wpp and usuario.telefone_wpp:
        msg = "🔔 Hub Capture — novidades:\n" + "\n".join(f"• {li}" for li in linhas)
        await uniq.enviar(usuario.telefone_wpp, msg)


async def varredura(session: AsyncSession, usuario: Usuario) -> int:
    """Roda as três detecções e despacha. Retorna o nº de alertas criados."""
    mudancas, canais = await _mudancas_monitoradas(session, usuario)
    buscas = await _buscas_ativas(session, usuario)
    do_territorio = _criterios_do_territorio(buscas)
    novos, canais_busca = await _novas_propostas(session, usuario, buscas)
    canais |= canais_busca
    oportunidades = (
        await _oportunidades(session, usuario) if "oportunidade" in do_territorio else []
    )
    # oportunidades saem também por email/wpp quando o usuário tem opt-in
    if oportunidades and usuario.optin_wpp:
        canais.add("wpp")
    if oportunidades:
        canais.add("email")
    # canal fora do plano (§39) não despacha — o alerta continua no painel
    cfg = await plano_gates.config_do_usuario(session, usuario.id)
    if not plano_gates.feature_liberada(cfg, "alertas_email"):
        canais.discard("email")
    if not plano_gates.feature_liberada(cfg, "alertas_wpp"):
        canais.discard("wpp")
    todos = mudancas + novos + oportunidades
    await session.flush()
    await _despachar(usuario, todos, canais)
    return len(todos)
