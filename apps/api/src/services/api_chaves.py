"""Chaves de API de parceiros (§67): emissão, resolução e consumo.

Formato: `hub_<ambiente>_<40 caracteres base62>` — `hub_live_…` em produção,
`hub_test_…` no sandbox. O ambiente vai NO TEXTO da chave para que o erro
"usei a chave de teste em produção" seja reconhecido antes de qualquer
consulta ao banco, e para que um vazamento seja identificável num log
(`hub_live_` é o padrão que scanners de segredo procuram).

Da chave guardamos só o sha256. Não usamos bcrypt/argon2 de propósito: a chave
tem ~238 bits aleatórios (não há dicionário a atacar) e é verificada em TODA
requisição — um hash lento seria um gargalo sem ganho de segurança.

`resolver()` é o caminho quente (middleware + backend de autenticação) e tem
cache curto em memória; revogar invalida o cache deste processo na hora e os
demais em até `_CACHE_TTL` segundos.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import string
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..db.session import SessionLocal
from ..models.api_chave import ESCOPOS, ApiChave, ApiUso
from ..models.usuario import Usuario
from . import plano_gates

_ALFABETO = string.ascii_letters + string.digits
_TAMANHO_SEGREDO = 40
_TAMANHO_PREFIXO = 6  # caracteres do segredo exibidos na lista
FORMATO = re.compile(r"^hub_(live|test)_[A-Za-z0-9]{40}$")


class ChaveInvalida(Exception):
    """Pedido de criação que não pode ser atendido (mensagem vai ao usuário)."""


class LimiteChavesExcedido(Exception):
    def __init__(self, maximo: int) -> None:
        super().__init__(f"máximo de {maximo} chave(s) ativa(s)")
        self.maximo = maximo


def ambiente_atual() -> str:
    return "test" if settings.sandbox else "live"


def gerar(ambiente: str | None = None) -> tuple[str, str, str]:
    """Nova chave → (texto, prefixo de exibição, hash). O texto só sai daqui."""
    amb = ambiente or ambiente_atual()
    segredo = "".join(secrets.choice(_ALFABETO) for _ in range(_TAMANHO_SEGREDO))
    chave = f"hub_{amb}_{segredo}"
    return chave, chave[: len(f"hub_{amb}_") + _TAMANHO_PREFIXO], hash_de(chave)


def hash_de(chave: str) -> str:
    return hashlib.sha256(chave.encode()).hexdigest()


def ambiente_da_chave(chave: str) -> str | None:
    """'live'/'test' pelo texto; None quando não é uma chave do Hub."""
    m = FORMATO.match(chave or "")
    return m.group(1) if m else None


# ── Resolução (caminho quente) ──────────────────────────────────────────────
@dataclass(frozen=True)
class ChaveResolvida:
    id: uuid.UUID
    usuario_id: uuid.UUID
    prefixo: str
    nome: str
    escopo: str
    ambiente: str
    limite_por_minuto: int
    limite_por_dia: int


_CACHE_TTL = 30.0
_CACHE_NEGATIVO_TTL = 10.0
_CACHE_MAX = 5000
_cache: dict[str, tuple[float, ChaveResolvida | None]] = {}


def limpar_cache() -> None:
    _cache.clear()


async def resolver(chave: str) -> ChaveResolvida | None:
    """Chave válida, ativa, no ambiente certo e de usuário ativo → dados dela.

    Qualquer outra coisa → None (o chamador responde 401). O "não achei" também
    é cacheado por alguns segundos: chave inventada em laço não vira uma
    consulta ao banco por tentativa.
    """
    if ambiente_da_chave(chave) != ambiente_atual():
        return None
    h = hash_de(chave)
    agora = time.monotonic()
    em_cache = _cache.get(h)
    if em_cache is not None:
        expira, valor = em_cache
        if agora < expira:
            return valor
    try:
        valor = await _carregar(h)
    except Exception:  # noqa: BLE001 — banco fora do ar: nega sem cachear
        return None
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    ttl = _CACHE_TTL if valor is not None else _CACHE_NEGATIVO_TTL
    _cache[h] = (agora + ttl, valor)
    return valor


async def _carregar(h: str) -> ChaveResolvida | None:
    async with SessionLocal() as s:
        row = (
            await s.execute(
                select(ApiChave, Usuario)
                .join(Usuario, Usuario.id == ApiChave.usuario_id)
                .where(ApiChave.hash == h)
            )
        ).first()
    if row is None:
        return None
    chave, usuario = row
    agora = datetime.now(UTC)
    if chave.revogada_em is not None or (chave.expira_em and chave.expira_em <= agora):
        return None
    if chave.ambiente != ambiente_atual():
        return None
    # conta desativada para de responder; admin nunca entra por chave (as
    # rotas de administração não são lugar de integração)
    if not usuario.is_active or usuario.is_superuser:
        return None
    cfg = await plano_gates.config_por_plano_id(usuario.plano_id)
    return ChaveResolvida(
        id=chave.id,
        usuario_id=chave.usuario_id,
        prefixo=chave.prefixo,
        nome=chave.nome,
        escopo=chave.escopo,
        ambiente=chave.ambiente,
        limite_por_minuto=chave.limite_por_minuto
        or cfg.api_req_min
        or settings.api_limite_por_minuto,
        limite_por_dia=chave.limite_por_dia or cfg.api_req_dia or settings.api_limite_por_dia,
    )


# ── Gestão ──────────────────────────────────────────────────────────────────
async def _maximo_de_chaves(session: AsyncSession, usuario_id: uuid.UUID) -> int:
    cfg = await plano_gates.config_do_usuario(session, usuario_id)
    if cfg.api_chaves_max is not None:
        return cfg.api_chaves_max
    return settings.api_chaves_max_por_conta


async def contar_ativas(session: AsyncSession, usuario_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count(ApiChave.id)).where(
                ApiChave.usuario_id == usuario_id,
                ApiChave.revogada_em.is_(None),
                ApiChave.ambiente == ambiente_atual(),
            )
        )
    ).scalar_one()


async def criar(
    session: AsyncSession,
    usuario: Usuario,
    *,
    nome: str,
    escopo: str = "leitura",
    criada_por: uuid.UUID | None = None,
    limite_por_minuto: int | None = None,
    limite_por_dia: int | None = None,
    expira_em: datetime | None = None,
    respeitar_limite_plano: bool = True,
) -> tuple[ApiChave, str]:
    """Emite uma chave para `usuario`. Devolve (registro, texto da chave)."""
    if usuario.is_superuser:
        raise ChaveInvalida(
            "contas de administração não recebem chave de API — crie uma conta "
            "própria para a integração"
        )
    if not usuario.is_active:
        raise ChaveInvalida("conta desativada")
    if escopo not in ESCOPOS:
        raise ChaveInvalida(f"escopo inválido: {escopo}")
    if expira_em is not None and expira_em <= datetime.now(UTC):
        raise ChaveInvalida("a data de expiração já passou")
    if respeitar_limite_plano:
        maximo = await _maximo_de_chaves(session, usuario.id)
        if await contar_ativas(session, usuario.id) >= maximo:
            raise LimiteChavesExcedido(maximo)

    texto, prefixo, h = gerar()
    registro = ApiChave(
        usuario_id=usuario.id,
        nome=nome.strip() or "Integração",
        prefixo=prefixo,
        hash=h,
        ambiente=ambiente_atual(),
        escopo=escopo,
        limite_por_minuto=limite_por_minuto,
        limite_por_dia=limite_por_dia,
        criada_por=criada_por,
        expira_em=expira_em,
    )
    session.add(registro)
    await session.flush()
    await session.refresh(registro)
    return registro, texto


async def listar(
    session: AsyncSession, usuario_id: uuid.UUID | None = None
) -> list[tuple[ApiChave, Usuario]]:
    stmt = (
        select(ApiChave, Usuario)
        .join(Usuario, Usuario.id == ApiChave.usuario_id)
        .order_by(ApiChave.revogada_em.is_not(None), ApiChave.created_at.desc())
    )
    if usuario_id is not None:
        stmt = stmt.where(ApiChave.usuario_id == usuario_id)
    return [(c, u) for c, u in (await session.execute(stmt)).all()]


async def revogar(
    session: AsyncSession, chave_id: uuid.UUID, usuario_id: uuid.UUID | None = None
) -> bool:
    """Revoga (não apaga: o histórico de uso continua conferível)."""
    stmt = (
        update(ApiChave)
        .where(ApiChave.id == chave_id, ApiChave.revogada_em.is_(None))
        .values(revogada_em=datetime.now(UTC))
        .returning(ApiChave.hash)
    )
    if usuario_id is not None:
        stmt = stmt.where(ApiChave.usuario_id == usuario_id)
    h = (await session.execute(stmt)).scalar_one_or_none()
    if h is None:
        return False
    _cache.pop(h, None)
    return True


async def uso_por_chave(
    session: AsyncSession, chave_ids: list[uuid.UUID], desde: date
) -> dict[uuid.UUID, list[ApiUso]]:
    if not chave_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(ApiUso)
                .where(ApiUso.chave_id.in_(chave_ids), ApiUso.dia >= desde)
                .order_by(ApiUso.dia)
            )
        )
        .scalars()
        .all()
    )
    saida: dict[uuid.UUID, list[ApiUso]] = {}
    for r in rows:
        saida.setdefault(r.chave_id, []).append(r)
    return saida


async def gravar_uso(
    session: AsyncSession,
    contagens: dict[tuple[uuid.UUID, date], tuple[int, int]],
    ultimo_uso: dict[uuid.UUID, datetime],
) -> None:
    """Soma o consumo acumulado em memória (o middleware não grava por request)."""
    ids = {k[0] for k in contagens} | set(ultimo_uso)
    if not ids:
        return
    # chave cuja conta foi apagada no intervalo (cascade) quebraria a FK e
    # levaria o lote inteiro junto
    existentes = set(
        (await session.execute(select(ApiChave.id).where(ApiChave.id.in_(ids)))).scalars()
    )
    for (chave_id, dia), (ok, bloqueadas) in contagens.items():
        if chave_id not in existentes:
            continue
        stmt = pg_insert(ApiUso).values(
            chave_id=chave_id, dia=dia, requisicoes=ok, bloqueadas=bloqueadas
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["chave_id", "dia"],
                set_={
                    "requisicoes": ApiUso.requisicoes + stmt.excluded.requisicoes,
                    "bloqueadas": ApiUso.bloqueadas + stmt.excluded.bloqueadas,
                },
            )
        )
    for chave_id, quando in ultimo_uso.items():
        if chave_id not in existentes:
            continue
        await session.execute(
            update(ApiChave).where(ApiChave.id == chave_id).values(ultimo_uso_em=quando)
        )
