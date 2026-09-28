"""Varredura do usuário: mudanças nas propostas monitoradas + futuras propostas.

Duas detecções, ambas na sessão RLS do próprio usuário e ambas recortadas pelos
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

O alerta **oportunidade** ("recebeu recurso da fonte X sem proposta cadastrada
em X") foi RETIRADO: a ausência de proposta numa fonte é o normal do repasse
constitucional, então o aviso disparava sempre e virou ruído de fundo na
central. Os alertas já gravados continuam legíveis (`criterios_alerta.RETIRADOS`).

Ao final, os alertas criados são despachados por email/WhatsApp conforme os
`canais` das buscas (painel é implícito — o alerta já está no banco).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.alerta import Alerta
from ..models.monitoramento import Monitoramento, MonitoramentoBusca
from ..models.proposta import Proposta
from ..models.usuario import Usuario
from ..notifications import email as email_notif
from ..notifications import uniq
from ..notifications.email_templates import alertas_resumo
from . import canais_alerta, criterios_alerta, detect_changes, plano_gates
from . import config as config_service
from . import emendas_proposta as emendas_service
from . import empenhos_proposta as empenhos_service
from . import monitoramentos as monitoramentos_service
from . import pareceres as pareceres_service
from .perfil import AREA_FONTES

log = logging.getLogger("hubcapture.alertas")


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


def _linha(alerta: Alerta) -> str:
    p = alerta.payload or {}
    municipio = p.get("municipio_nome") or p.get("municipio_ibge") or "seu município"
    if p.get("resumo"):  # alerta de mudança: o critério + o que mudou
        titulo = p.get("titulo") or p.get("numero_proposta") or "proposta monitorada"
        return f"{criterios_alerta.rotulo(alerta.tipo)} em {municipio}: {titulo} — {p['resumo']}"
    if alerta.tipo == "nova_proposta":
        return f"Nova proposta em {municipio}: {p.get('titulo')} ({p.get('fonte')})"
    if alerta.tipo == "oportunidade":  # retirado; alerta antigo ainda é despachável
        return (
            f"Oportunidade em {municipio}: recursos da fonte {p.get('fonte')} "
            "recebidos sem proposta de captação cadastrada"
        )
    return f"Atualização em {municipio}"


def mensagem_push(alertas: list[Alerta]) -> dict:
    """Payload do Web Push: UMA notificação por lote (dez alertas numa
    madrugada viram um aviso, não dez vibrações seguidas)."""
    linhas = [_linha(a) for a in alertas]
    if len(alertas) == 1:
        a = alertas[0]
        url = f"/panel/funding/{a.proposta_id}?de=alerts" if a.proposta_id else "/panel/alerts"
        titulo = criterios_alerta.rotulo(a.tipo) if a.tipo else "Atualização"
        return {"title": f"Hub Capture · {titulo}", "body": linhas[0], "url": url, "tag": "alertas"}
    corpo = "\n".join(linhas[:3]) + (f"\n+{len(linhas) - 3} outras" if len(linhas) > 3 else "")
    return {
        "title": f"Hub Capture · {len(alertas)} atualizações",
        "body": corpo,
        "url": "/panel/alerts",
        "tag": "alertas",
    }


async def _despachar(
    session: AsyncSession, usuario: Usuario, alertas: list[Alerta], canais: set[str]
) -> None:
    """E-mail/WhatsApp/push best-effort — provider ausente degrada em silêncio.

    CADA canal no seu `try`: antes, um 4xx do Uniq ou um SMTP recusado
    estourava a varredura depois do flush, a transação voltava e os alertas —
    e a fotografia do monitoramento — sumiam junto. No dia seguinte a mesma
    mudança era detectada, o mesmo canal falhava, e o gestor nunca era avisado
    nem pelo painel.
    """
    if not alertas:
        return
    linhas = [_linha(a) for a in alertas]
    if "email" in canais and usuario.email:
        try:
            base = await config_service.resolver("app_base_url")
            url = f"{base.rstrip('/')}/panel/alerts" if base else None
            assunto, txt, html = alertas_resumo(linhas, url)
            await email_notif.enviar(usuario.email, assunto, txt, html)
        except Exception:  # noqa: BLE001 — canal best-effort
            log.warning("alertas: e-mail falhou para %s", usuario.id, exc_info=True)
    if "wpp" in canais and usuario.optin_wpp and usuario.telefone_wpp:
        try:
            msg = "🔔 Hub Capture — novidades:\n" + "\n".join(f"• {li}" for li in linhas)
            await uniq.enviar(usuario.telefone_wpp, msg)
        except Exception:  # noqa: BLE001
            log.warning("alertas: WhatsApp falhou para %s", usuario.id, exc_info=True)
    if "push" in canais:
        try:
            await canais_alerta.enviar_push(session, usuario.id, mensagem_push(alertas))
        except Exception:  # noqa: BLE001
            log.warning("alertas: push falhou para %s", usuario.id, exc_info=True)


async def varredura(session: AsyncSession, usuario: Usuario) -> int:
    """Roda as duas detecções e despacha. Retorna o nº de alertas criados."""
    mudancas, canais = await _mudancas_monitoradas(session, usuario)
    buscas = await _buscas_ativas(session, usuario)
    novos, canais_busca = await _novas_propostas(session, usuario, buscas)
    canais |= canais_busca
    # os canais da CONTA valem para todo alerta (§63) — antes só o do
    # monitoramento contava, e ele nascia 'painel' em quase toda porta
    canais |= await canais_alerta.da_conta(session, usuario)
    # canal fora do plano (§39) não despacha — o alerta continua no painel
    cfg = await plano_gates.config_do_usuario(session, usuario.id)
    if not plano_gates.feature_liberada(cfg, "alertas_email"):
        canais.discard("email")
    if not plano_gates.feature_liberada(cfg, "alertas_wpp"):
        canais.discard("wpp")
    todos = mudancas + novos
    await session.flush()
    await _despachar(session, usuario, todos, canais)
    return len(todos)
