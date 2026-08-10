"""Gates de features por PLANO — o que cada assinatura libera.

Cada plano (`planos.limites`, jsonb) carrega uma CONFIG que diz o que a
assinatura inclui: quais módulos do produto (§29) ficam visíveis, quais fontes
de dados entram na coleta, até quantos municípios o usuário monitora, quantos
membros pode convidar para a conta e flags de features avulsas (PDF, CSV,
canais de alerta). Este módulo é a fonte de verdade da LEITURA dessa config:
normaliza o jsonb (aceitando as chaves legadas), cacheia por plano e expõe os
helpers de enforcement que os guards/serviços consomem.

Formato canônico de `planos.limites`:

    {
      "municipios_max": 5,            # null/ausente = ilimitado
      "membros_max": 2,               # convidados p/ conta; 0 = não convida
      "modulos": ["captacao", ...],   # ausente = todos os módulos da plataforma
      "fontes": ["transferegov"],     # grupos OU connector ids; ausente = todas
      "features": {"export_pdf": true, "alertas_wpp": false}
    }

Compat legada (seeds antigos): `municipios` → `municipios_max`; bool de módulo
no topo (`"copiloto": false`) vira exclusão do módulo; demais bools soltos
viram feature. Plano sem linha/sem config → tudo liberado (usuário sem plano
não é bloqueado — igual ao limite de municípios de sempre).

Camadas em cima da plataforma, nunca no lugar dela: o módulo precisa estar
ativo no painel admin (§29) E incluído no plano do usuário para aparecer.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import SessionLocal
from ..models.plano import Plano
from ..models.usuario import Usuario
from . import fontes as fontes_service
from . import modulos as modulos_service

# Features avulsas conhecidas (catálogo p/ o painel admin). Ausente na config
# do plano = LIBERADA — gate de feature é restrição opt-in, nunca surpresa.
FEATURES: list[dict] = [
    {
        "chave": "export_pdf",
        "label": "Espelho em PDF",
        "descricao": "Exportar/compartilhar o espelho da proposta em PDF",
    },
    {
        "chave": "relatorio_csv",
        "label": "Relatórios CSV",
        "descricao": "Baixar o recorte da tela em CSV (captação e emendas)",
    },
    {
        "chave": "alertas_email",
        "label": "Alertas por e-mail",
        "descricao": "Despacho de alertas pelo canal e-mail",
    },
    {
        "chave": "alertas_wpp",
        "label": "Alertas por WhatsApp",
        "descricao": "Despacho de alertas pelo canal WhatsApp (Uniq)",
    },
]
_FEATURE_CHAVES = {f["chave"] for f in FEATURES}

# chaves reservadas do formato canônico (não viram feature na normalização)
_RESERVADAS = {
    "municipios_max",
    "membros_max",
    "modulos",
    "fontes",
    "features",
    "municipios",
    "membros",
}


@dataclass(frozen=True)
class PlanoConfig:
    """Config normalizada de um plano. `None` em modulos/fontes = sem restrição."""

    municipios_max: int | None = None
    membros_max: int | None = None
    modulos: frozenset[str] | None = None
    fontes: frozenset[str] | None = None
    features: dict[str, bool] = field(default_factory=dict)


#: config de quem não tem plano/limites — nada é restringido
SEM_RESTRICAO = PlanoConfig()


def _inteiro(valor) -> int | None:
    try:
        return int(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def normalizar(limites: dict | None) -> PlanoConfig:
    """`planos.limites` (jsonb livre, com legado) → config canônica."""
    if not limites:
        return SEM_RESTRICAO

    municipios_max = _inteiro(limites.get("municipios_max", limites.get("municipios")))
    membros_max = _inteiro(limites.get("membros_max", limites.get("membros")))

    chaves_modulo = {m["chave"] for m in modulos_service.MODULOS}
    modulos: frozenset[str] | None = None
    if isinstance(limites.get("modulos"), list):
        modulos = frozenset(m for m in limites["modulos"] if m in chaves_modulo)
    else:
        # legado: bool de módulo no topo ("copiloto": false) exclui o módulo
        excluidos = {k for k in chaves_modulo if limites.get(k) is False}
        if excluidos:
            modulos = frozenset(chaves_modulo - excluidos)

    fontes: frozenset[str] | None = None
    if isinstance(limites.get("fontes"), list):
        expandidas: set[str] = set()
        for escolha in limites["fontes"]:
            grupo = fontes_service.GRUPOS.get(escolha)
            expandidas.update(grupo["connectors"] if grupo else (escolha,))
        fontes = frozenset(expandidas)

    features: dict[str, bool] = {}
    if isinstance(limites.get("features"), dict):
        features = {str(k): bool(v) for k, v in limites["features"].items()}
    # legado: bool solto no topo que não é módulo nem chave reservada
    for k, v in limites.items():
        if isinstance(v, bool) and k not in chaves_modulo and k not in _RESERVADAS:
            features.setdefault(k, v)

    return PlanoConfig(
        municipios_max=municipios_max,
        membros_max=membros_max,
        modulos=modulos,
        fontes=fontes,
        features=features,
    )


# ── Lookup do plano do usuário ──────────────────────────────────────────────
async def plano_do_usuario(session: AsyncSession, usuario_id: uuid.UUID) -> Plano | None:
    return (
        await session.execute(
            select(Plano)
            .join(Usuario, Usuario.plano_id == Plano.id)
            .where(Usuario.id == usuario_id)
        )
    ).scalar_one_or_none()


async def config_do_usuario(session: AsyncSession, usuario_id: uuid.UUID) -> PlanoConfig:
    """Config efetiva do usuário (sem plano → sem restrição)."""
    plano = await plano_do_usuario(session, usuario_id)
    return normalizar(plano.limites if plano else None)


# Guard de request (require_modulo) roda em TODA chamada dos routers guardados;
# sem cache, cada request pagaria uma sessão de banco só para ler o plano.
# TTL curto: editar o plano no painel admin propaga em segundos.
_CACHE_TTL = 10.0
_cache_configs: tuple[float, dict[uuid.UUID, PlanoConfig]] | None = None


def limpar_cache() -> None:
    """Invalida o snapshot (chamado ao editar plano; testes/ops)."""
    global _cache_configs
    _cache_configs = None


async def config_por_plano_id(plano_id: uuid.UUID | None) -> PlanoConfig:
    """Acesso runtime com snapshot cacheado de TODOS os planos (guards)."""
    if plano_id is None:
        return SEM_RESTRICAO
    global _cache_configs
    agora = time.monotonic()
    if _cache_configs is None or agora - _cache_configs[0] >= _CACHE_TTL:
        try:
            async with SessionLocal() as s:
                rows = (await s.execute(select(Plano))).scalars().all()
                snapshot = {p.id: normalizar(p.limites) for p in rows}
        except Exception:  # noqa: BLE001 — banco fora do ar não derruba a navegação
            return SEM_RESTRICAO  # sem cachear: a próxima chamada tenta de novo
        _cache_configs = (agora, snapshot)
    return _cache_configs[1].get(plano_id, SEM_RESTRICAO)


# ── Gates ───────────────────────────────────────────────────────────────────
def modulo_liberado(cfg: PlanoConfig | None, chave: str) -> bool:
    return cfg is None or cfg.modulos is None or chave in cfg.modulos


def fonte_liberada(cfg: PlanoConfig | None, fonte: str) -> bool:
    if cfg is None or cfg.fontes is None:
        return True
    return fonte in cfg.fontes or (fontes_service.grupo_de(fonte) or "") in cfg.fontes


def filtrar_fontes(cfg: PlanoConfig | None, fontes: list[str] | tuple[str, ...]) -> list[str]:
    """Recorta uma lista de connector ids ao que o plano libera (ordem estável)."""
    return [f for f in fontes if fonte_liberada(cfg, f)]


def grupos_liberados(cfg: PlanoConfig | None) -> set[str] | None:
    """Grupos de fonte (vocabulário do onboarding) liberados. None = todos."""
    if cfg is None or cfg.fontes is None:
        return None
    grupos = {fontes_service.grupo_de(f) for f in cfg.fontes}
    grupos |= {f for f in cfg.fontes if f in fontes_service.GRUPOS}
    return {g for g in grupos if g}


def feature_liberada(cfg: PlanoConfig | None, chave: str) -> bool:
    """Feature ausente na config = liberada (gate é opt-in)."""
    if cfg is None:
        return True
    return bool(cfg.features.get(chave, True))


def features_efetivas(cfg: PlanoConfig | None) -> dict[str, bool]:
    """Estado efetivo das features conhecidas (p/ o perfil e o front)."""
    return {chave: feature_liberada(cfg, chave) for chave in sorted(_FEATURE_CHAVES)}


async def exigir_feature(session: AsyncSession, usuario: Usuario, chave: str) -> None:
    """Guard de endpoint: feature fora do plano → 403 (o front sabe fazer upsell)."""
    if usuario.is_superuser:
        return
    cfg = await config_do_usuario(session, usuario.id)
    if not feature_liberada(cfg, chave):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=f"FEATURE_NAO_INCLUIDA_PLANO: {chave}"
        )
