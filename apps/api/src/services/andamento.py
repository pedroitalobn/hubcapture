"""Linha do tempo da proposta — o andamento em UMA narrativa.

O gestor não pergunta "quais são os pareceres?"; ele pergunta "em que pé está
isso?". A resposta está espalhada: o parecer diz o veredito da análise, a
vigência diz até quando dá para executar, a pendência diz o que trava, a
situação diz onde parou. Aqui esses fatos viram eventos de um mesmo tipo,
ordenados no tempo, para caberem numa timeline dentro da própria proposta.

Construído SOBRE os pareceres (§36): eles são a espinha do andamento — cada
análise é um passo da tramitação, com quem assinou e o que decidiu. Os marcos
da proposta (cadastro, vigência, prazos, pendências) entram para o gestor não
ler o parecer no vácuo.

O que NÃO entra: fato sem data. Datar por chute ("o ano da emenda vira 1º de
janeiro") produziria uma linha do tempo verossímil e errada — a emenda e seu
autor têm seção própria, que não depende de fingir cronologia.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.proposta import Proposta
from ..schemas.andamento import AndamentoColeta, AndamentoPagina, EventoAndamento
from ..schemas.parecer import ParecerRead
from . import documentos_proposta as documentos_service
from . import emendas_proposta as emendas_service
from . import empenhos_proposta as empenhos_service
from . import pareceres as pareceres_service

# escada de urgência do prazo — mesma de `lib/format.ts::tomPrazo` no web
DIAS_CRITICO = 7
DIAS_ATENCAO = 30


def _hoje() -> date:
    return datetime.now(UTC).date()


def _para_data(valor: Any) -> date | None:
    if isinstance(valor, date):
        return valor
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _tom_prazo(alvo: date | None) -> str:
    if alvo is None:
        return "neutral"
    dias = (alvo - _hoje()).days
    if dias < 0:
        return "danger"
    if dias <= DIAS_CRITICO:
        return "danger"
    if dias <= DIAS_ATENCAO:
        return "warn"
    return "ok"


def tom_do_veredito(situacao: str | None) -> str:
    """Aprovar é bom, reprovar é ruim, complementação exige ação do gestor."""
    s = (situacao or "").lower()
    if "aprovar" in s or "aprovad" in s:
        return "ok"
    if "reprovar" in s or "reprovad" in s:
        return "danger"
    if "complementa" in s:
        return "warn"
    return "neutral"


def _juntar(*partes: Any) -> str | None:
    texto = " · ".join(str(p).strip() for p in partes if p and str(p).strip())
    return texto or None


def _decimal(valor: Any) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor))
    except (ArithmeticError, TypeError, ValueError):
        return None


def evento_de_parecer(p: ParecerRead) -> EventoAndamento:
    """O parecer como passo da tramitação: o veredito lidera, quem assinou apoia."""
    em_elaboracao = (p.situacao_analise or "").lower().startswith("em elabora")
    return EventoAndamento(
        data=p.data_parecer,
        tipo="parecer",
        titulo=p.situacao or "Parecer emitido",
        # a análise em elaboração ainda não é decisão — o tom não pode celebrar
        tom="neutral" if em_elaboracao else tom_do_veredito(p.situacao),
        ator=p.responsavel or p.orgao_analise,
        detalhe=_juntar(
            {"concedente": "Concedente", "convenente": "Convenente"}.get(
                p.esfera or "", p.esfera
            ),
            p.papel,
            p.cargo,
            p.responsavel and p.orgao_analise,
            p.situacao_analise and f"análise {p.situacao_analise.lower()}",
        ),
        valor=p.valor_reprovado if (p.valor_reprovado or 0) > 0 else None,
        texto=p.texto,
        url=p.url_parecer,
    )


def evento_de_empenho(e: Any) -> EventoAndamento:
    """O empenho como passo: é o fato que diz que o recurso saiu do papel.

    Anulação não é celebração — empenho anulado por inteiro entra como perda, e
    a anulação parcial, como atenção. Pintar os três de verde diria ao gestor
    que tem recurso reservado onde ele foi devolvido.
    """
    empenhado = _decimal(e.valor_empenhado) or Decimal(0)
    anulado = _decimal(e.valor_anulado) or Decimal(0)
    if anulado and anulado >= empenhado > 0:
        titulo, tom = "Empenho anulado", "danger"
    elif anulado > 0:
        titulo, tom = "Empenho anulado em parte", "warn"
    else:
        titulo, tom = "Empenho emitido", "ok"
    if e.numero_empenho:
        titulo = f"{titulo} · {e.numero_empenho}"

    return EventoAndamento(
        data=e.data_empenho,
        tipo="empenho",
        titulo=titulo,
        tom=tom,
        ator=e.ug_emitente,
        detalhe=_juntar(e.tipo_empenho, e.natureza_despesa, e.situacao),
        valor=max(empenhado - anulado, Decimal(0)) or None,
    )


def marcos_da_proposta(p: Proposta) -> list[EventoAndamento]:
    """Os fatos datados que a própria proposta carrega."""
    hoje = _hoje()
    eventos: list[EventoAndamento] = []
    execucao = p.execucao if isinstance(p.execucao, dict) else {}

    if p.data_proposta:
        eventos.append(
            EventoAndamento(
                data=p.data_proposta,
                tipo="proposta",
                titulo="Proposta cadastrada na fonte",
                detalhe=_juntar(p.numero_proposta, p.orgao_superior),
                tom="neutral",
            )
        )

    assinatura = _para_data(execucao.get("data_assinatura"))
    if assinatura:
        eventos.append(
            EventoAndamento(
                data=assinatura,
                tipo="vigencia",
                titulo="Instrumento assinado",
                tom="ok",
                valor=_decimal(execucao.get("valor_global")),
            )
        )

    inicio = _para_data(execucao.get("data_inicio_vigencia"))
    if inicio:
        eventos.append(
            EventoAndamento(
                data=inicio,
                tipo="vigencia",
                titulo="Início da vigência",
                tom="neutral",
                futuro=inicio > hoje,
            )
        )

    fim = _para_data(execucao.get("data_fim_vigencia"))
    if fim:
        eventos.append(
            EventoAndamento(
                data=fim,
                tipo="vigencia",
                titulo="Fim da vigência",
                detalhe="Prazo para executar o recurso",
                tom=_tom_prazo(fim),
                futuro=fim > hoje,
            )
        )

    for prazo in p.prazos or []:
        if not isinstance(prazo, dict):
            continue
        limite = _para_data(prazo.get("data_limite"))
        if not limite or limite == fim:  # o fim de vigência já entrou acima
            continue
        eventos.append(
            EventoAndamento(
                data=limite,
                tipo="prazo",
                titulo=str(prazo.get("tipo") or "Prazo").capitalize(),
                tom=_tom_prazo(limite),
                futuro=limite > hoje,
            )
        )

    for pendencia in p.pendencias or []:
        if not isinstance(pendencia, dict):
            continue
        limite = _para_data(pendencia.get("prazo"))
        eventos.append(
            EventoAndamento(
                data=limite,
                tipo="pendencia",
                titulo="Pendência",
                detalhe=str(pendencia.get("descricao") or "").strip() or None,
                tom=_tom_prazo(limite) if limite else "warn",
                futuro=bool(limite and limite > hoje),
            )
        )

    # a situação atual só vira evento se a fonte disser QUANDO mexeu no registro
    if p.data_atualizacao_fonte and (p.situacao or p.movimentacao):
        eventos.append(
            EventoAndamento(
                data=p.data_atualizacao_fonte,
                tipo="atualizacao",
                titulo=p.situacao or "Movimentação na fonte",
                detalhe=p.movimentacao,
                tom="neutral",
            )
        )

    return eventos


def ordenar(eventos: list[EventoAndamento]) -> list[EventoAndamento]:
    """Mais recente primeiro; sem data por último (não some, mas não lidera)."""
    return sorted(
        eventos,
        key=lambda e: (e.data is None, -(e.data.toordinal() if e.data else 0), e.tipo),
    )


async def linha_do_tempo(
    session: AsyncSession,
    proposta_id: uuid.UUID,
    *,
    atualizar: bool = False,
    usuario_id: uuid.UUID | None = None,
) -> AndamentoPagina | None:
    """Andamento completo da proposta. `None` = proposta fora do território."""
    proposta = (
        await session.execute(
            select(Proposta).where(
                Proposta.id == proposta_id, Proposta.excluido_em.is_(None)
            )
        )
    ).scalar_one_or_none()
    if proposta is None:
        return None

    pareceres, coleta_pareceres = await pareceres_service.por_proposta(
        session, proposta_id, atualizar=atualizar, usuario_id=usuario_id
    )

    # Empenhos entram da LEITURA do cache: quem coleta é `/commitments`, que a
    # mesma tela chama. Sincronizar aqui também faria a página disparar duas
    # coletas concorrentes da mesma coisa a cada abertura.
    coleta_empenhos = None
    if atualizar:
        coleta_empenhos = await empenhos_service.sync_proposta(
            session, proposta, usuario_id=usuario_id
        )
    empenhos = await empenhos_service.listar(session, proposta)

    eventos = (
        marcos_da_proposta(proposta)
        + [evento_de_parecer(p) for p in pareceres]
        + [evento_de_empenho(e) for e in empenhos if e.data_empenho]
    )

    return AndamentoPagina(
        itens=ordenar(eventos),
        numero_plano_trabalho=proposta.numero_plano_trabalho,
        coleta=AndamentoColeta(pareceres=coleta_pareceres, empenhos=coleta_empenhos),
    )


async def empenhos(
    session: AsyncSession,
    proposta_id: uuid.UUID,
    *,
    atualizar: bool = False,
    usuario_id: uuid.UUID | None = None,
):
    """Empenhos da proposta + totais (`None` = proposta fora do território)."""
    proposta = (
        await session.execute(
            select(Proposta).where(
                Proposta.id == proposta_id, Proposta.excluido_em.is_(None)
            )
        )
    ).scalar_one_or_none()
    if proposta is None:
        return None
    return await empenhos_service.por_proposta(
        session, proposta, atualizar=atualizar, usuario_id=usuario_id
    )


async def documentos(
    session: AsyncSession,
    proposta_id: uuid.UUID,
    *,
    atualizar: bool = False,
    usuario_id: uuid.UUID | None = None,
):
    """Documentos digitalizados da proposta (`None` = fora do território)."""
    proposta = (
        await session.execute(
            select(Proposta).where(
                Proposta.id == proposta_id, Proposta.excluido_em.is_(None)
            )
        )
    ).scalar_one_or_none()
    if proposta is None:
        return None
    return await documentos_service.por_proposta(
        session, proposta, atualizar=atualizar, usuario_id=usuario_id
    )


async def emendas(
    session: AsyncSession,
    proposta_id: uuid.UUID,
    *,
    atualizar: bool = False,
    usuario_id: uuid.UUID | None = None,
):
    """Emendas + parlamentares autores da proposta (`None` = fora do território)."""
    proposta = (
        await session.execute(
            select(Proposta).where(
                Proposta.id == proposta_id, Proposta.excluido_em.is_(None)
            )
        )
    ).scalar_one_or_none()
    if proposta is None:
        return None
    return await emendas_service.por_proposta(
        session, proposta, atualizar=atualizar, usuario_id=usuario_id
    )
