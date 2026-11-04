"""Dados de TESTE do sandbox de integração (§67).

No sandbox não há coleta (core/sandbox.py bloqueia toda saída), então quem dá
corpo às respostas da API são dados FICTÍCIOS gerados aqui — propostas,
repasses e alertas para cada município do território da conta de teste. Tudo é
determinístico (mesmo município → mesmos números) e as datas são relativas ao
dia de hoje, para que "prazos próximos" e "novidades" continuem fazendo
sentido depois de cada recriação.

Os registros são marcados para ninguém confundir com dado real: objeto/
descrição começam com "[SANDBOX]", o nº da proposta com "SBX", e
`dados_fonte`/`detalhe` levam `{"sandbox": true}`.

A gravação passa pelos MESMOS serviços da coleta (`propostas.upsert`,
`repasses.upsert`) dentro da sessão RLS da conta — a mesma porta que a busca
ao vivo usa em produção. Recriar = apagar a curadoria da conta (favoritos,
pastas, monitoramentos, alertas, consultas salvas) e regravar os valores
originais dos dados de teste.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..core.config import settings
from ..db.session import SessionLocal, rls_session
from ..models.alerta import Alerta
from ..models.consulta_proposta import ConsultaProposta
from ..models.favorito import Favorito
from ..models.monitoramento import Monitoramento, MonitoramentoBusca
from ..models.municipio_interesse import MunicipioInteresse
from ..models.pasta import Pasta, PastaProposta
from ..models.preferencias import PreferenciasUsuario
from ..models.proposta import Proposta
from ..models.usuario import Usuario
from ..schemas.proposta import PropostaCanonica
from ..schemas.repasse import RepasseCanonico
from . import fontes as fontes_service
from . import propostas as propostas_service
from . import repasses as repasses_service
from .municipios import uf_do_ibge

log = logging.getLogger("hubcapture.sandbox")

#: território semeado em conta de teste que ainda não tem município
MUNICIPIOS_PADRAO: tuple[tuple[str, str, str], ...] = (
    ("3550308", "São Paulo", "SP"),
    ("2304400", "Fortaleza", "CE"),
    ("2611606", "Recife", "PE"),
)

_OBJETOS = (
    ("Construção de Unidade Básica de Saúde", "MINISTERIO DA SAUDE", "saude"),
    ("Aquisição de equipamentos para escola de tempo integral", "MINISTERIO DA EDUCACAO", "educ"),
    ("Pavimentação e drenagem de vias urbanas", "MINISTERIO DAS CIDADES", "infra"),
    ("Reforma de quadra poliesportiva", "MINISTERIO DO ESPORTE", "esporte"),
    ("Aquisição de ambulância tipo A", "MINISTERIO DA SAUDE", "saude"),
    ("Implantação de sistema de abastecimento de água", "MINISTERIO DAS CIDADES", "san"),
    ("Apoio a festival cultural municipal", "MINISTERIO DA CULTURA", "cultura"),
    ("Aquisição de trator agrícola", "MINISTERIO DA AGRICULTURA E PECUARIA", "agro"),
)
_SITUACOES = (
    "Proposta/Plano de Trabalho Cadastrados",
    "Proposta/Plano de Trabalho em Análise",
    "Proposta/Plano de Trabalho Aprovado",
    "Em execução",
    "Proposta/Plano de Trabalho Complementado em Análise",
    "Em execução",
    "Proposta/Plano de Trabalho Cadastrados",
    "Prestação de Contas em Análise",
)
_FONTES_PROPOSTA = ("transferegov_disc", "transferegov_esp", "transferegov_voluntarias")
_REPASSES = (
    ("fns", "[SANDBOX] Atenção Primária — Piso de Atenção Primária", "Atenção Primária"),
    ("fns", "[SANDBOX] Média e Alta Complexidade — Teto MAC", "Média e Alta Complexidade"),
    ("fns", "[SANDBOX] Emenda parlamentar — Incremento Temporário", "Atenção Primária"),
    ("fnde", "[SANDBOX] PNAE — Alimentação Escolar", "PNAE"),
    ("fnde", "[SANDBOX] Salário-Educação — Quota Municipal", "Salário-Educação"),
    ("fnde", "[SANDBOX] PDDE — Dinheiro Direto na Escola", "PDDE"),
)


def _semente(ibge: str) -> int:
    return int(hashlib.sha256(ibge.encode()).hexdigest()[:8], 16)


def dados_ficticios(
    ibge: str, nome: str | None, uf: str | None, hoje: date | None = None
) -> tuple[list[PropostaCanonica], list[RepasseCanonico]]:
    """Propostas e repasses de teste de UM município (puro, determinístico)."""
    hoje = hoje or datetime.now(UTC).date()
    uf = uf or uf_do_ibge(ibge)
    nome = nome or f"Município {ibge}"
    base = _semente(ibge)

    propostas: list[PropostaCanonica] = []
    for i, (objeto, orgao, _area) in enumerate(_OBJETOS):
        valor = Decimal(150_000 + ((base >> i) % 40) * 25_000)
        empenhado = valor if i % 3 == 2 else (valor / 2 if i % 3 == 1 else Decimal(0))
        pago = empenhado / 2 if i in (3, 5) else Decimal(0)
        criada = hoje - timedelta(days=20 + i * 37)
        fim_vigencia = hoje + timedelta(days=10 + i * 25)
        publicada = i in (2, 3, 5)
        propostas.append(
            PropostaCanonica(
                fonte=_FONTES_PROPOSTA[i % len(_FONTES_PROPOSTA)],
                id_externo=f"sbx-{ibge}-{i + 1}",
                numero_proposta=f"SBX{(base + i) % 10000:04d}{i + 1}/{criada.year}",
                titulo=f"[SANDBOX] {objeto}",
                objeto=f"[SANDBOX] {objeto} — dado fictício para testes de integração.",
                orgao_superior=orgao,
                modalidade="CONTRATO DE REPASSE" if i % 2 else "CONVENIO",
                municipio_ibge=ibge,
                municipio_nome=nome,
                uf=uf,
                valor_total=valor,
                contrapartida=(valor * Decimal("0.02")).quantize(Decimal("0.01")),
                situacao=_SITUACOES[i],
                emenda=f"SBX{base % 1000:03d}000{i}" if i % 4 == 0 else None,
                prazos=[{"tipo": "fim_vigencia", "data_limite": fim_vigencia.isoformat()}],
                pendencias=(
                    [{"descricao": "[SANDBOX] Anexar projeto básico", "prazo": None}]
                    if i == 1
                    else []
                ),
                movimentacao="[SANDBOX] Proposta atualizada pelo convenente",
                data_proposta=criada,
                data_atualizacao_fonte=hoje - timedelta(days=1),
                url_origem=None,
                proveniencia={"origem": "sandbox"},
                execucao={
                    "ano": criada.year,
                    "valor_global": float(valor),
                    "valor_empenhado": float(empenhado),
                    "valor_liberado": float(pago),
                    "valor_pago": float(pago),
                    "situacao_publicacao": "Publicado" if publicada else "Não Publicado",
                    "natureza_juridica": "Administração Pública Municipal",
                },
                dados_fonte={"sandbox": True, "ANO_PROP": str(criada.year)},
            )
        )

    repasses: list[RepasseCanonico] = []
    for i, (fonte, descricao, categoria) in enumerate(_REPASSES):
        for mes in range(3):
            indice = hoje.year * 12 + hoje.month - 1 - mes  # mês corrente e os 2 anteriores
            quando = date(indice // 12, indice % 12 + 1, 1)
            valor = Decimal(20_000 + ((base >> (i + mes)) % 50) * 3_000)
            repasses.append(
                RepasseCanonico(
                    fonte=fonte,
                    id_externo=f"sbx-{ibge}-r{i + 1}-{mes}",
                    municipio_ibge=ibge,
                    municipio_nome=nome,
                    uf=uf,
                    data_repasse=quando + timedelta(days=9),
                    competencia=quando.strftime("%Y-%m"),
                    descricao=descricao,
                    categoria=categoria,
                    orgao_superior=(
                        "MINISTERIO DA SAUDE" if fonte == "fns" else "MINISTERIO DA EDUCACAO"
                    ),
                    natureza="repasse",
                    valor=valor,
                    documento=f"SBX{quando.year}OB{(base + i * 10 + mes) % 100000:05d}",
                    emenda=i == 2,
                    detalhe={"sandbox": True}
                    | ({"parlamentar": "[SANDBOX] Dep. Fulano de Tal"} if i == 2 else {}),
                    proveniencia={"origem": "sandbox"},
                )
            )
    return propostas, repasses


async def preparar_conta(usuario_id: uuid.UUID) -> int:
    """Garante território e dados de teste da conta. Devolve nº de municípios.

    Conta sem território ganha `MUNICIPIOS_PADRAO`; conta que já escolheu os
    seus (onboarding pelo site do sandbox) recebe dados fictícios para ELES.
    """
    hoje = datetime.now(UTC).date()
    async with rls_session(usuario_id) as s:
        territorio = (
            await s.execute(
                select(
                    MunicipioInteresse.ibge, MunicipioInteresse.nome, MunicipioInteresse.uf
                ).where(MunicipioInteresse.usuario_id == usuario_id)
            )
        ).all()
        if not territorio:
            for ibge, nome, uf in MUNICIPIOS_PADRAO:
                await s.execute(
                    pg_insert(MunicipioInteresse)
                    .values(usuario_id=usuario_id, ibge=ibge, nome=nome, uf=uf, modo="monitorado")
                    .on_conflict_do_nothing(constraint="uq_municipios_usuario_ibge")
                )
            await s.execute(
                pg_insert(PreferenciasUsuario)
                .values(
                    usuario_id=usuario_id,
                    fontes=list(fontes_service.HABILITADAS),
                    areas=["saude", "educacao", "infraestrutura"],
                    monitorar_ativo=True,
                )
                .on_conflict_do_nothing(index_elements=["usuario_id"])
            )
            territorio = list(MUNICIPIOS_PADRAO)

        for ibge, nome, uf in territorio:
            propostas, repasses = dados_ficticios(ibge, nome, uf, hoje)
            for p in propostas:
                await propostas_service.upsert(s, p)
            for r in repasses:
                await repasses_service.upsert(s, r)
        await s.flush()

        # alertas de exemplo, para /alerts não chegar vazio na 1ª chamada
        tem_alerta = (
            await s.execute(select(func.count(Alerta.id)).where(Alerta.usuario_id == usuario_id))
        ).scalar_one()
        if not tem_alerta:
            ibges = [t[0] for t in territorio]
            exemplos = (
                (
                    await s.execute(
                        select(Proposta)
                        .where(
                            Proposta.municipio_ibge.in_(ibges),
                            Proposta.id_externo.like("sbx-%"),
                        )
                        .order_by(Proposta.id_externo)
                        .limit(2)
                    )
                )
                .scalars()
                .all()
            )
            for p, tipo, resumo in zip(
                exemplos,
                ("situacao", "empenho"),
                ("[SANDBOX] Situação mudou para Em execução", "[SANDBOX] Novo empenho emitido"),
                strict=False,
            ):
                s.add(
                    Alerta(
                        usuario_id=usuario_id,
                        proposta_id=p.id,
                        tipo=tipo,
                        payload={
                            "resumo": resumo,
                            "titulo": p.titulo,
                            "numero_proposta": p.numero_proposta,
                            "municipio_ibge": p.municipio_ibge,
                            "municipio_nome": p.municipio_nome,
                            "sandbox": True,
                        },
                    )
                )
    return len(territorio)


async def resetar_conta(usuario_id: uuid.UUID) -> int:
    """Apaga a curadoria da conta e regrava os dados de teste."""
    async with rls_session(usuario_id) as s:
        pastas = select(Pasta.id).where(Pasta.usuario_id == usuario_id)
        await s.execute(delete(PastaProposta).where(PastaProposta.pasta_id.in_(pastas)))
        for modelo in (
            Pasta,
            Favorito,
            Monitoramento,
            MonitoramentoBusca,
            Alerta,
            ConsultaProposta,
        ):
            await s.execute(delete(modelo).where(modelo.usuario_id == usuario_id))
    return await preparar_conta(usuario_id)


async def resetar_todas() -> int:
    """Recria os dados de toda conta de teste (não-admin, ativa). Best-effort."""
    async with SessionLocal() as s:
        ids = (
            (
                await s.execute(
                    select(Usuario.id).where(
                        Usuario.is_active.is_(True), Usuario.is_superuser.is_(False)
                    )
                )
            )
            .scalars()
            .all()
        )
    feitas = 0
    for uid in ids:
        try:
            await resetar_conta(uid)
            feitas += 1
        except Exception:  # noqa: BLE001 — uma conta com problema não segura as outras
            log.warning("sandbox: falha ao recriar a conta %s", uid, exc_info=True)
    log.info("sandbox: dados de teste recriados em %d conta(s)", feitas)
    return feitas


def _segundos_ate(hora_utc: int, agora: datetime) -> float:
    alvo = agora.replace(hour=hora_utc, minute=0, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(days=1)
    return (alvo - agora).total_seconds()


async def laco_reset_diario() -> None:
    """Task do lifespan: recria os dados de teste uma vez por dia."""
    hora = settings.sandbox_reset_hora_utc
    if hora < 0:
        return
    while True:
        await asyncio.sleep(_segundos_ate(hora % 24, datetime.now(UTC)))
        try:
            await resetar_todas()
        except Exception:  # noqa: BLE001
            log.warning("sandbox: recriação diária falhou", exc_info=True)
