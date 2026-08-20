"""Acesso DEMO — sandbox de apresentação/vendas sobre dados reais do cache.

O demo não é um ambiente paralelo: é um USUÁRIO comum (`usuarios.is_demo`)
cujo território aponta para municípios que JÁ têm dados coletados — o RLS de
sempre recorta o que ele vê, e cada clique exercita o produto de verdade
(favoritar, pastas, alertas, copiloto, PDF). Três regras fazem dele um
sandbox à prova de apresentação:

1. **Coleta sempre cache-only** — a busca ao vivo nunca vai às fontes na
   sessão demo (`consulta_avulsa.live_search(somente_cache=True)`), então
   nenhuma fonte fora do ar vira mensagem de erro na frente do cliente.
2. **Escrita destrutiva/de identidade bloqueada** — zerar perfil, refazer
   onboarding, trocar senha/e-mail, convidar membros e conectar agendas
   respondem 403 `DEMO_SOMENTE_LEITURA` (a conta é compartilhada).
3. **Auto-seed** — o boot (e cada `POST /auth/demo`) garante usuário,
   território com dados, curadoria de exemplo e o pacote inicial do Class
   (artigos + hints ⓘ, com vídeo quando `demo_video_url` está configurada).

Liga/desliga em runtime pela chave `demo_ativo` do painel admin (default on).
"""

from __future__ import annotations

import logging
import secrets
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.users import current_user_optional
from ..db.session import SessionLocal, plataforma_session, rls_session
from ..models.favorito import Favorito
from ..models.helpdesk import (
    HelpdeskArtigo,
    HelpdeskCategoria,
    HelpdeskHint,
    HelpdeskMidia,
    HelpdeskModulo,
)
from ..models.municipio_interesse import MunicipioInteresse
from ..models.pasta import Pasta, PastaProposta
from ..models.preferencias import PreferenciasUsuario
from ..models.proposta import Proposta
from ..models.usuario import Usuario
from . import config as config_service
from . import fontes as fontes_service
from . import helpdesk as helpdesk_service
from . import monitoramentos as monitoramentos_service
from .municipios import uf_do_ibge

logger = logging.getLogger("hubcapture.demo")

DEMO_SOMENTE_LEITURA = "DEMO_SOMENTE_LEITURA"

# Perfil semeado na conta demo — áreas que existem em `perfil.AREAS`.
_DEMO_AREAS = ["saude", "educacao", "infraestrutura"]
_DEMO_MUNICIPIOS_MAX = 3
_DEMO_FAVORITOS = 3
_DEMO_PASTA = "Prioridades"


def eh_demo(user: Usuario | None) -> bool:
    return bool(getattr(user, "is_demo", False))


def bloquear_escrita(user: Usuario | None) -> None:
    """403 nas ações que quebrariam o sandbox (conta compartilhada)."""
    if eh_demo(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=DEMO_SOMENTE_LEITURA)


async def negar_escrita_demo(
    request: Request,
    user: Usuario | None = Depends(current_user_optional),
) -> None:
    """Dependency de ROUTER: bloqueia métodos de escrita para a conta demo.

    Leituras (GET/HEAD/OPTIONS) passam — o demo é vitrine, não cofre. Usada
    nos routers em que só a escrita é problema (conta, /users, integrações),
    sem duplicar checagem endpoint a endpoint.
    """
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if isinstance(user, Usuario):
        bloquear_escrita(user)


async def esta_ativo() -> bool:
    """Flag runtime `demo_ativo` (painel admin > .env; default on)."""
    valor = (await config_service.resolver("demo_ativo") or "on").strip().lower()
    return valor != "off"


async def usuario_demo(session: AsyncSession) -> Usuario | None:
    return (
        await session.execute(
            select(Usuario).where(Usuario.email == settings.demo_email.strip().lower())
        )
    ).scalar_one_or_none()


async def demo_disponivel() -> bool:
    """O botão 'Ver demonstração' só aparece com a flag on E a conta de pé."""
    if not await esta_ativo():
        return False
    async with SessionLocal() as s:
        user = await usuario_demo(s)
    return user is not None and bool(user.is_active)


# ── Bootstrap (idempotente; roda no lifespan e a cada /auth/demo) ───────────


async def bootstrap() -> None:
    """Boot best-effort: nunca derruba a API (banco pode estar subindo)."""
    try:
        if not await esta_ativo():
            return
        await ensure_demo()
    except Exception:  # noqa: BLE001 — demo é acessório, o boot segue
        logger.warning("bootstrap do acesso demo falhou", exc_info=True)
    try:
        if await esta_ativo():
            await semear_class()
    except Exception:  # noqa: BLE001
        logger.warning("seed do Class (demo) falhou", exc_info=True)


async def ensure_demo() -> Usuario | None:
    """Garante a conta demo com território e curadoria semeados (idempotente)."""
    email = settings.demo_email.strip().lower()
    if not email:
        return None
    async with SessionLocal() as session:
        user = await usuario_demo(session)
        if user is None:
            user = await _criar_usuario_demo(session, email)
        elif not (user.is_demo and user.is_active):
            await session.execute(
                update(Usuario)
                .where(Usuario.id == user.id)
                .values(is_demo=True, is_active=True, is_verified=True)
            )
            await session.commit()
            user.is_demo = True
    await _semear_perfil(user.id)
    await _semear_curadoria(user.id)
    return user


async def _criar_usuario_demo(session: AsyncSession, email: str) -> Usuario:
    # via UserManager (hash de senha + hook de preferências), como o admin do
    # boot. Sem DEMO_PASSWORD a senha é aleatória: a porta é o /auth/demo.
    from ..core.users import UserManager
    from ..db.user_db import get_user_db
    from ..schemas.user import UserCreate

    senha = settings.demo_password or secrets.token_urlsafe(24)
    user_db_gen = get_user_db(session)
    user_db = await user_db_gen.__anext__()
    manager = UserManager(user_db)
    user = await manager.create(
        UserCreate(
            email=email,
            password=senha,
            nome="Conta de demonstração",
            papel="executivo",
        ),
        safe=True,
    )
    await session.execute(
        update(Usuario)
        .where(Usuario.id == user.id)
        .values(is_demo=True, is_active=True, is_verified=True)
    )
    await session.commit()
    user.is_demo = True
    logger.info("conta demo criada: %s", email)
    return user


async def _semear_perfil(usuario_id: uuid.UUID) -> None:
    """Território + preferências + buscas monitoradas (só quando ainda não há)."""
    async with rls_session(usuario_id) as session:
        tem_territorio = (
            await session.execute(
                select(func.count(MunicipioInteresse.id)).where(
                    MunicipioInteresse.usuario_id == usuario_id
                )
            )
        ).scalar_one()
    if tem_territorio:
        return

    municipios = await _municipios_alvo()
    if not municipios:
        logger.info(
            "acesso demo sem território: nenhum IBGE em demo_ibges e nenhum "
            "município com propostas no cache ainda — o seed roda de novo no "
            "próximo /auth/demo"
        )
        return

    async with rls_session(usuario_id) as session:
        for ibge, nome, uf in municipios:
            await session.execute(
                pg_insert(MunicipioInteresse)
                .values(
                    usuario_id=usuario_id,
                    ibge=ibge,
                    nome=nome,
                    uf=uf or uf_do_ibge(ibge),
                    modo="monitorado",
                )
                .on_conflict_do_nothing(constraint="uq_municipios_usuario_ibge")
            )
        fontes = list(fontes_service.HABILITADAS)
        prefs = pg_insert(PreferenciasUsuario).values(
            usuario_id=usuario_id,
            fontes=fontes,
            areas=_DEMO_AREAS,
            monitorar_ativo=True,
        )
        await session.execute(
            prefs.on_conflict_do_update(
                index_elements=["usuario_id"],
                set_={"fontes": fontes, "areas": _DEMO_AREAS, "monitorar_ativo": True},
            )
        )
        # monitoramento de futuras propostas por município — a central de
        # alertas do demo mostra configuração viva, não uma tela vazia
        for ibge, _nome, _uf in municipios:
            await monitoramentos_service.criar_busca(
                session,
                usuario_id,
                municipio_ibge=ibge,
                area=None,
                fonte=None,
                canais=["painel"],
            )
    logger.info("território do acesso demo semeado: %s", [m[0] for m in municipios])


async def _municipios_alvo() -> list[tuple[str, str | None, str | None]]:
    """IBGEs do demo: override do painel/.env, ou os municípios com MAIS
    propostas no cache — demo sempre abre com dado na tela."""
    from sqlalchemy import text

    bruto = (await config_service.resolver("demo_ibges")) or ""
    escolhidos = [i.strip() for i in bruto.split(",") if i.strip()]
    async with plataforma_session() as session:
        # A leitura é pela policy PERMISSIVE de plataforma, mas a policy
        # por-tenant também é AVALIADA — e numa conexão reciclada do pool
        # `app.usuario_id` volta como STRING VAZIA, cujo cast ::uuid explode a
        # consulta inteira. Um tenant nulo válido faz a policy por-tenant
        # avaliar limpo (para falso) e a de plataforma abrir o SELECT.
        await session.execute(
            text("SELECT set_config('app.usuario_id', :uid, true)"),
            {"uid": "00000000-0000-0000-0000-000000000000"},
        )
        if escolhidos:
            saida: list[tuple[str, str | None, str | None]] = []
            for ibge in escolhidos[:_DEMO_MUNICIPIOS_MAX]:
                row = (
                    await session.execute(
                        select(Proposta.municipio_nome, Proposta.uf)
                        .where(
                            Proposta.municipio_ibge == ibge,
                            Proposta.municipio_nome.is_not(None),
                        )
                        .limit(1)
                    )
                ).first()
                saida.append((ibge, row[0] if row else None, row[1] if row else None))
            return saida
        rows = (
            await session.execute(
                select(
                    Proposta.municipio_ibge,
                    func.max(Proposta.municipio_nome),
                    func.max(Proposta.uf),
                    func.count(Proposta.id),
                )
                .where(
                    Proposta.municipio_ibge.is_not(None),
                    Proposta.excluido_em.is_(None),
                )
                .group_by(Proposta.municipio_ibge)
                .order_by(func.count(Proposta.id).desc())
                .limit(_DEMO_MUNICIPIOS_MAX)
            )
        ).all()
    return [(ibge, nome, uf) for ibge, nome, uf, _n in rows]


async def _semear_curadoria(usuario_id: uuid.UUID) -> None:
    """Favoritos + pasta de exemplo (só quando o demo ainda não tem nenhum).

    A aba Acompanhamento e as pastas são parte da demonstração — abrir tudo
    vazio esconderia metade do produto.
    """
    async with rls_session(usuario_id) as session:
        tem_favorito = (
            await session.execute(
                select(func.count()).select_from(Favorito).where(Favorito.usuario_id == usuario_id)
            )
        ).scalar_one()
        if tem_favorito:
            return
        # o RLS já recorta ao território do demo; as mais recentes lideram
        propostas = (
            (
                await session.execute(
                    select(Proposta.id)
                    .where(Proposta.excluido_em.is_(None))
                    .order_by(
                        Proposta.data_proposta.desc().nullslast(),
                        Proposta.cache_atualizado_em.desc().nullslast(),
                    )
                    .limit(_DEMO_FAVORITOS)
                )
            )
            .scalars()
            .all()
        )
        if not propostas:
            return
        for pid in propostas:
            await session.execute(
                pg_insert(Favorito)
                .values(usuario_id=usuario_id, proposta_id=pid)
                .on_conflict_do_nothing()
            )
        pasta_id = (
            await session.execute(
                select(Pasta.id).where(Pasta.usuario_id == usuario_id, Pasta.nome == _DEMO_PASTA)
            )
        ).scalar_one_or_none()
        if pasta_id is None:
            pasta = Pasta(usuario_id=usuario_id, nome=_DEMO_PASTA, cor="lime")
            session.add(pasta)
            await session.flush()
            pasta_id = pasta.id
        for pid in propostas:
            await session.execute(
                pg_insert(PastaProposta)
                .values(pasta_id=pasta_id, proposta_id=pid)
                .on_conflict_do_nothing()
            )


# ── Pacote inicial do Class (artigos + hints ⓘ + vídeo) ─────────────────────
# Conteúdo FACTUAL sobre o vocabulário das fontes (empenho, contrapartida,
# situação…) — é o que o hint contextual explica no momento em que o dado
# aparece na tela. Só entra num Class VIRGEM (nenhum artigo/hint): a curadoria
# do admin nunca é sobrescrita nem ressuscitada.

_CLASS_CATEGORIA = ("Conceitos do dia a dia", "Vocabulário das fontes, explicado no contexto")
_CLASS_MODULO = (
    "Primeiros passos no Hub Capture",
    "Do território ao recurso: como ler o painel e agir sobre cada proposta.",
)

# (título, resumo, corpo HTML, chaves de hint, é aula do módulo?)
_CLASS_ARTIGOS: list[tuple[str, str, str, list[str], bool]] = [
    (
        "O que é o valor empenhado?",
        "Empenho é a reserva do orçamento: o recurso saiu do papel e está "
        "comprometido com a sua proposta.",
        "<h2>Empenho: a promessa virou reserva</h2>"
        "<p>O <strong>empenho</strong> é o primeiro estágio da despesa pública: o órgão "
        "reserva no orçamento o valor destinado à transferência. Um valor "
        "<strong>empenhado</strong> ainda não caiu na conta — mas já está comprometido "
        "com o seu instrumento.</p>"
        "<p>No Hub, a execução financeira aparece em camadas: "
        "<strong>pago ⊂ liberado ⊂ empenhado</strong> sobre o valor global. "
        "Empenhado e ainda não pago é recurso disponibilizado à espera da execução "
        "— é onde o gestor deve agir primeiro.</p>"
        "<ul><li><strong>Empenhado</strong>: reservado no orçamento.</li>"
        "<li><strong>Liberado</strong>: autorizado a sair.</li>"
        "<li><strong>Pago</strong>: efetivamente transferido.</li></ul>",
        ["proposta.empenhado", "proposta.execucao"],
        True,
    ),
    (
        "Situação e movimentação da proposta",
        "A situação diz em que etapa a proposta está na fonte; a movimentação, "
        "qual foi o último passo registrado.",
        "<h2>Onde a proposta está agora</h2>"
        "<p>Cada fonte publica a <strong>situação</strong> da proposta (em análise, "
        "celebrada, em execução, prestação de contas…) e a última "
        "<strong>movimentação</strong> da tramitação. O Hub coleta os dois lados — API "
        "e página de consulta — e mostra o mais atual.</p>"
        "<p>Mudança de situação em proposta monitorada gera <strong>alerta</strong> "
        "na central (e por e-mail/WhatsApp, quando configurados).</p>",
        ["proposta.situacao"],
        True,
    ),
    (
        "Nº da proposta: a referência que o portal reconhece",
        "É pelo número da proposta (ex.: 14275/2026) que você confere o registro "
        "no portal da fonte e conversa com o órgão concedente.",
        "<h2>A referência do gestor</h2>"
        "<p>O <strong>nº da proposta</strong> (como <strong>14275/2026</strong>) é a "
        "referência oficial publicada pela fonte — é o que se digita no portal do "
        "TransfereGov para conferir o registro e o que o gabinete usa ao falar com o "
        "órgão concedente.</p>"
        "<p>No Hub ele aparece como uma pílula destacada nas listas e no detalhe; "
        "clique para copiar. Não confunda com identificadores internos de integração, "
        "que aparecem discretos no fim da página.</p>",
        ["proposta.numero_proposta"],
        True,
    ),
    (
        "Cadastrada × disponível: os dois lados da captação",
        "Cadastrada é a proposta que o município já registrou; disponível é o "
        "recurso aberto aguardando proposta.",
        "<h2>Dois momentos do mesmo ciclo</h2>"
        "<p><strong>Cadastrada</strong> é a proposta que o ente já registrou na fonte "
        "e agora tramita. <strong>Disponível</strong> é a oportunidade: programa ou "
        "recurso aberto que ainda não tem proposta do seu município.</p>"
        "<p>O filtro da Captação separa os dois — e o alerta de "
        "<strong>oportunidade</strong> avisa quando há recurso disponível sem proposta "
        "cadastrada no seu território.</p>",
        ["funding.tipo"],
        False,
    ),
    (
        "Valor total e contrapartida",
        "Valor total é o montante do instrumento; contrapartida é a parte que o "
        "proponente assume com recursos próprios.",
        "<h2>Quem paga o quê</h2>"
        "<p>O <strong>valor total</strong> (ou valor global) é o montante do "
        "instrumento publicado pela fonte. A <strong>contrapartida</strong> é a "
        "parcela que o proponente — em geral o município — se compromete a aportar "
        "com recursos próprios, em dinheiro ou em bens e serviços mensuráveis.</p>"
        "<p>A contrapartida mínima varia por porte do município e por programa; o "
        "valor exato de cada proposta vem da própria fonte e aparece no detalhe.</p>",
        ["proposta.valor_total", "proposta.contrapartida"],
        False,
    ),
    (
        "Prazos e pendências: o relógio da proposta",
        "Prazos dizem o que vence e quando; pendências, o que a fonte está " "esperando de você.",
        "<h2>O que vence — e o que falta</h2>"
        "<p>Os <strong>prazos</strong> estruturados da proposta (fim de vigência, "
        'datas-limite de etapa) alimentam a visão "o que vence na janela" e o '
        "Copiloto. As <strong>pendências</strong> são exigências registradas pela "
        "fonte — complementação de documento, ajuste de plano de trabalho.</p>"
        "<p>Monitore a proposta com os critérios de <strong>prazo</strong> e "
        "<strong>pendência</strong> para receber alerta quando algo entrar na "
        "janela.</p>",
        ["proposta.prazo", "proposta.pendencias"],
        False,
    ),
]


async def semear_class() -> bool:
    """Pacote inicial do Class. Retorna True quando semeou algo."""
    async with SessionLocal() as session:
        async with session.begin():
            tem_conteudo = (
                await session.execute(select(func.count()).select_from(HelpdeskArtigo))
            ).scalar_one()
            tem_hint = (
                await session.execute(select(func.count()).select_from(HelpdeskHint))
            ).scalar_one()
            if tem_conteudo or tem_hint:
                return False  # Class já tem curadoria — nunca sobrescrever

            video_url = ((await config_service.resolver("demo_video_url")) or "").strip()

            nome_cat, desc_cat = _CLASS_CATEGORIA
            categoria = HelpdeskCategoria(
                nome=nome_cat,
                slug=await helpdesk_service.slug_unico(
                    session, HelpdeskCategoria, helpdesk_service.slugify(nome_cat)
                ),
                descricao=desc_cat,
            )
            session.add(categoria)

            titulo_mod, desc_mod = _CLASS_MODULO
            modulo = HelpdeskModulo(
                titulo=titulo_mod,
                slug=await helpdesk_service.slug_unico(
                    session, HelpdeskModulo, helpdesk_service.slugify(titulo_mod)
                ),
                descricao=desc_mod,
                publicado=True,
            )
            session.add(modulo)
            await session.flush()

            ordem_aula = 0
            for titulo, resumo, corpo, chaves, eh_aula in _CLASS_ARTIGOS:
                artigo = HelpdeskArtigo(
                    categoria_id=categoria.id,
                    modulo_id=modulo.id if eh_aula else None,
                    titulo=titulo,
                    slug=await helpdesk_service.slug_unico(
                        session, HelpdeskArtigo, helpdesk_service.slugify(titulo)
                    ),
                    resumo=resumo,
                    corpo=corpo,
                    publicado=True,
                    ordem=ordem_aula if eh_aula else 0,
                )
                if eh_aula:
                    ordem_aula += 1
                session.add(artigo)
                await session.flush()
                if video_url:
                    session.add(
                        HelpdeskMidia(
                            artigo_id=artigo.id,
                            tipo="video",
                            titulo=f"Vídeo: {titulo}",
                            url=video_url,
                            orientacao="horizontal",
                        )
                    )
                for chave in chaves:
                    if helpdesk_service.chave_valida(chave):
                        session.add(HelpdeskHint(chave=chave, artigo_id=artigo.id, ativo=True))
    logger.info("Class semeado com o pacote inicial do demo (%d artigos)", len(_CLASS_ARTIGOS))
    return True
