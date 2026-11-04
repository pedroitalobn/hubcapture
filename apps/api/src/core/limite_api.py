"""Limite de requisições da API de integração (§67) — a API não cai por parceiro.

Vale só para quem entra por CHAVE DE API (`X-API-Key: hub_…`, ou
`Authorization: Bearer hub_…`). O tráfego do painel (login JWT) segue
intocado. Três camadas, da mais ampla para a mais estreita:

1. **Simultâneas** — requisições de parceiro EM ANDAMENTO, no total
   (`api_max_simultaneas`) e por chave (`api_max_simultaneas_por_chave`). É a
   trava que protege o painel: o processo tem um event loop e um pool de
   conexões (§38); sem teto de concorrência, um parceiro disparando 200
   requisições em paralelo esgotaria o pool e o gestor esperaria na fila.
2. **Teto global por minuto** (`api_limite_global_por_minuto`) — a soma de
   todos os parceiros, para que vinte integrações "dentro do limite" não
   somem uma sobrecarga.
3. **Por chave** — por minuto e por dia, vindos da chave, do plano ou do
   padrão do servidor (`services/api_chaves.resolver`).

Além do volume, a POLÍTICA DE ROTAS (`motivo_bloqueio`): uma chave não alcança
administração, autenticação, gestão da conta (não cria outra chave), copiloto
(custo de IA) nem nada que dispare coleta ao vivo nas fontes do governo
(Chromium/CSV de 1 GB — o que derruba o servidor de verdade). Chave de
`leitura` só faz GET.

Contadores em memória, janela fixa: a API roda num processo só (uvicorn de 1
worker). Se um dia subir mais de um worker, cada um conta o seu — os tetos
passam a valer por processo e precisam ser divididos (ou ir para o Redis).

ASGI puro (como `core/latencia.py`): não embrulha o corpo, então o streaming
continua funcionando e a vaga de concorrência só é devolvida quando a resposta
termina de verdade.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import parse_qsl

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import settings

log = logging.getLogger("hubcapture.api_parceiros")

PREFIXO_API = "/api/v1"

# ── Política de rotas ───────────────────────────────────────────────────────
# Prefixos (depois de /api/v1) que uma chave de API nunca alcança.
_PREFIXOS_BLOQUEADOS = (
    "/admin",  # administração da plataforma
    "/auth",  # login/cadastro/senha: a chave já É a autenticação
    "/account",  # membros e chaves da conta: chave não cria chave
    "/copilot",  # custo de IA por mensagem
    "/webhooks",
    "/integrations",  # OAuth de agendas (Google/Microsoft)
    "/notifications",  # inscrição de push do navegador
    "/onboarding",  # dispara o 1º sync (coleta pesada)
    "/proposals/live-search",  # coleta ao vivo nas fontes
    "/alerts/scan",  # a varredura roda no cron, depois da coleta
)
# Sufixos que disparam coleta/download na fonte (Chromium, sync).
_SUFIXOS_BLOQUEADOS = ("/sync", "/file", "/publication/pdf")
# Parâmetros que transformam leitura de cache em consulta ao vivo.
_PARAMETROS_COLETA = ("atualizar", "conferir", "forcar")
_METODOS_LEITURA = ("GET", "HEAD", "OPTIONS")


def motivo_bloqueio(metodo: str, caminho: str, query: str, escopo: str) -> str | None:
    """Código do bloqueio de política, ou None se a chave pode seguir."""
    if not caminho.startswith(PREFIXO_API):
        return None
    rota = caminho[len(PREFIXO_API) :].rstrip("/") or "/"
    metodo = metodo.upper()

    if rota == "/users/me":
        if metodo not in _METODOS_LEITURA:
            return "API_ROTA_NAO_DISPONIVEL"
    elif rota.startswith("/users"):
        return "API_ROTA_NAO_DISPONIVEL"
    for prefixo in _PREFIXOS_BLOQUEADOS:
        if rota == prefixo or rota.startswith(prefixo + "/"):
            return "API_ROTA_NAO_DISPONIVEL"
    if rota.endswith(_SUFIXOS_BLOQUEADOS):
        return "API_ROTA_NAO_DISPONIVEL"
    if rota == "/profile" and metodo == "DELETE":  # zerar a conta
        return "API_ROTA_NAO_DISPONIVEL"
    for nome, valor in parse_qsl(query, keep_blank_values=True):
        if nome in _PARAMETROS_COLETA and valor.strip().lower() not in ("", "0", "false", "no"):
            return "API_COLETA_AO_VIVO_NAO_DISPONIVEL"
    if escopo != "escrita" and metodo not in _METODOS_LEITURA:
        return "API_CHAVE_SOMENTE_LEITURA"
    return None


MENSAGENS = {
    "API_CHAVE_INVALIDA": "Chave de API inválida, revogada ou expirada.",
    "API_CHAVE_AMBIENTE_ERRADO": (
        "Esta chave é de outro ambiente: use hub_test_… no sandbox e hub_live_… em produção."
    ),
    "API_ROTA_NAO_DISPONIVEL": "Esta rota não está disponível para integrações por chave de API.",
    "API_COLETA_AO_VIVO_NAO_DISPONIVEL": (
        "Consulta ao vivo nas fontes não está disponível pela API; os dados vêm do "
        "cache, atualizado diariamente."
    ),
    "API_CHAVE_SOMENTE_LEITURA": "Esta chave é somente leitura (escopo 'leitura').",
    "API_LIMITE_MINUTO": "Limite de requisições por minuto desta chave atingido.",
    "API_LIMITE_DIARIO": "Cota diária de requisições desta chave atingida.",
    "API_LIMITE_GLOBAL": "A API está no limite de integrações agora. Tente em instantes.",
    "API_SIMULTANEAS": "Requisições simultâneas demais. Aguarde as anteriores terminarem.",
}


# ── Limitador ───────────────────────────────────────────────────────────────
@dataclass
class Decisao:
    ok: bool
    codigo: str | None = None
    retry_after: int = 0
    limite_minuto: int = 0
    restante_minuto: int = 0
    reset_minuto: int = 0
    limite_dia: int = 0
    restante_dia: int = 0


class Limitador:
    """Contadores de janela fixa (minuto e dia UTC) + vagas de concorrência."""

    def __init__(self, relogio=time.time) -> None:
        self._relogio = relogio
        self.reiniciar()

    def reiniciar(self) -> None:
        self._minuto: dict[tuple[uuid.UUID, int], int] = {}
        self._dia: dict[tuple[uuid.UUID, date], int] = {}
        self._global: dict[int, int] = {}
        self._em_andamento = 0
        self._em_andamento_chave: dict[uuid.UUID, int] = {}
        self._dias_semeados: set[tuple[uuid.UUID, date]] = set()

    def _agora(self) -> tuple[int, int, date]:
        t = self._relogio()
        janela = int(t // 60)
        return janela, 60 - int(t % 60), datetime.fromtimestamp(t, UTC).date()

    def dia_atual(self) -> date:
        return self._agora()[2]

    def precisa_semente(self, chave_id: uuid.UUID) -> bool:
        return (chave_id, self.dia_atual()) not in self._dias_semeados

    def semear_dia(self, chave_id: uuid.UUID, ja_usadas: int) -> None:
        """Retoma a contagem do dia após um restart (lida de `api_uso`)."""
        dia = self.dia_atual()
        if (chave_id, dia) in self._dias_semeados:
            return
        self._dias_semeados.add((chave_id, dia))
        chave = (chave_id, dia)
        self._dia[chave] = max(self._dia.get(chave, 0), int(ja_usadas or 0))

    def _podar(self, janela: int, dia: date) -> None:
        if len(self._minuto) > 10000:
            self._minuto = {k: v for k, v in self._minuto.items() if k[1] >= janela}
        if len(self._global) > 5:
            self._global = {k: v for k, v in self._global.items() if k >= janela}
        if len(self._dia) > 10000:
            self._dia = {k: v for k, v in self._dia.items() if k[1] >= dia}
            self._dias_semeados = {k for k in self._dias_semeados if k[1] >= dia}

    def entrar(self, chave_id: uuid.UUID, limite_minuto: int, limite_dia: int) -> Decisao:
        """Admite (e conta) ou recusa uma requisição. Admitida → chamar `sair`."""
        janela, reset, dia = self._agora()
        self._podar(janela, dia)
        usadas_min = self._minuto.get((chave_id, janela), 0)
        usadas_dia = self._dia.get((chave_id, dia), 0)
        base = Decisao(
            ok=False,
            limite_minuto=limite_minuto,
            restante_minuto=max(0, limite_minuto - usadas_min),
            reset_minuto=reset,
            limite_dia=limite_dia,
            restante_dia=max(0, limite_dia - usadas_dia),
        )

        def recusa(codigo: str, retry: int) -> Decisao:
            base.codigo = codigo
            base.retry_after = max(1, retry)
            return base

        if self._em_andamento >= settings.api_max_simultaneas:
            return recusa("API_SIMULTANEAS", 1)
        if self._em_andamento_chave.get(chave_id, 0) >= settings.api_max_simultaneas_por_chave:
            return recusa("API_SIMULTANEAS", 1)
        if usadas_dia >= limite_dia:
            meia_noite = 86400 - int(self._relogio() % 86400)
            return recusa("API_LIMITE_DIARIO", meia_noite)
        if usadas_min >= limite_minuto:
            return recusa("API_LIMITE_MINUTO", reset)
        if self._global.get(janela, 0) >= settings.api_limite_global_por_minuto:
            return recusa("API_LIMITE_GLOBAL", reset)

        self._minuto[(chave_id, janela)] = usadas_min + 1
        self._dia[(chave_id, dia)] = usadas_dia + 1
        self._global[janela] = self._global.get(janela, 0) + 1
        self._em_andamento += 1
        self._em_andamento_chave[chave_id] = self._em_andamento_chave.get(chave_id, 0) + 1
        base.ok = True
        base.restante_minuto = max(0, limite_minuto - usadas_min - 1)
        base.restante_dia = max(0, limite_dia - usadas_dia - 1)
        return base

    def sair(self, chave_id: uuid.UUID) -> None:
        self._em_andamento = max(0, self._em_andamento - 1)
        n = self._em_andamento_chave.get(chave_id, 0) - 1
        if n > 0:
            self._em_andamento_chave[chave_id] = n
        else:
            self._em_andamento_chave.pop(chave_id, None)


limitador = Limitador()


# ── Consumo (gravado em lote, nunca por requisição) ─────────────────────────
class Consumo:
    def __init__(self) -> None:
        self.contagens: dict[tuple[uuid.UUID, date], list[int]] = {}
        self.ultimo_uso: dict[uuid.UUID, datetime] = {}

    def registrar(self, chave_id: uuid.UUID, dia: date, *, bloqueada: bool) -> None:
        par = self.contagens.setdefault((chave_id, dia), [0, 0])
        par[1 if bloqueada else 0] += 1
        if not bloqueada:
            self.ultimo_uso[chave_id] = datetime.now(UTC)

    def retirar(self) -> tuple[dict, dict]:
        contagens = {k: (v[0], v[1]) for k, v in self.contagens.items()}
        ultimo = dict(self.ultimo_uso)
        self.contagens.clear()
        self.ultimo_uso.clear()
        return contagens, ultimo


consumo = Consumo()


def reiniciar() -> None:
    """Zera contadores e consumo pendente (testes/ops)."""
    limitador.reiniciar()
    consumo.contagens.clear()
    consumo.ultimo_uso.clear()


async def gravar_consumo() -> None:
    contagens, ultimo = consumo.retirar()
    if not contagens and not ultimo:
        return
    from ..db.session import SessionLocal
    from ..services import api_chaves

    try:
        async with SessionLocal() as s:
            async with s.begin():
                await api_chaves.gravar_uso(s, contagens, ultimo)
    except Exception:  # noqa: BLE001 — consumo é contabilidade, não derruba nada
        log.warning("falha ao gravar consumo da API (%d linhas)", len(contagens), exc_info=True)


async def laco_de_consumo(intervalo: float = 60.0) -> None:
    """Grava o consumo acumulado a cada `intervalo` segundos (task do lifespan)."""
    try:
        while True:
            await asyncio.sleep(intervalo)
            await gravar_consumo()
    except asyncio.CancelledError:
        await gravar_consumo()  # o que estava pendente não se perde no shutdown
        raise


async def _semear_dia(chave_id: uuid.UUID) -> None:
    if not limitador.precisa_semente(chave_id):
        return
    usadas = 0
    try:
        from sqlalchemy import select

        from ..db.session import SessionLocal
        from ..models.api_chave import ApiUso

        async with SessionLocal() as s:
            usadas = (
                await s.execute(
                    select(ApiUso.requisicoes).where(
                        ApiUso.chave_id == chave_id, ApiUso.dia == limitador.dia_atual()
                    )
                )
            ).scalar_one_or_none() or 0
    except Exception:  # noqa: BLE001 — sem a semente, conta do zero
        usadas = 0
    limitador.semear_dia(chave_id, usadas)


# ── Middleware ──────────────────────────────────────────────────────────────
def _chave_do_request(scope: Scope) -> tuple[str | None, list[tuple[bytes, bytes]]]:
    """Extrai a chave (X-API-Key ou Bearer hub_…) e devolve os cabeçalhos
    sem `Authorization`: com chave, a identidade é a da chave e só ela —
    um JWT junto não pode trocar quem está chamando."""
    chave: str | None = None
    outros: list[tuple[bytes, bytes]] = []
    autorizacao: bytes | None = None
    for nome, valor in scope.get("headers", []):
        if nome == b"x-api-key":
            chave = valor.decode("latin-1").strip()
        elif nome == b"authorization":
            autorizacao = valor
            outros.append((nome, valor))
        else:
            outros.append((nome, valor))
    if chave is None and autorizacao is not None:
        texto = autorizacao.decode("latin-1").strip()
        if texto.lower().startswith("bearer hub_"):
            chave = texto[7:].strip()
    if chave is None:
        return None, outros
    sem_auth = [(n, v) for n, v in outros if n != b"authorization"]
    sem_auth.append((b"x-api-key", chave.encode("latin-1")))
    return chave, sem_auth


async def _responder(
    send: Send, status: int, codigo: str, extras: dict[str, str] | None = None
) -> None:
    corpo = json.dumps(
        {"detail": codigo, "mensagem": MENSAGENS.get(codigo, codigo)}, ensure_ascii=False
    ).encode()
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(corpo)).encode()),
    ]
    for k, v in (extras or {}).items():
        headers.append((k.lower().encode(), v.encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": corpo})


def _cabecalhos_limite(d: Decisao) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(d.limite_minuto),
        "X-RateLimit-Remaining": str(d.restante_minuto),
        "X-RateLimit-Reset": str(d.reset_minuto),
        "X-RateLimit-Limit-Day": str(d.limite_dia),
        "X-RateLimit-Remaining-Day": str(d.restante_dia),
    }


class LimiteApiMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(PREFIXO_API):
            await self.app(scope, receive, send)
            return
        texto, headers = _chave_do_request(scope)
        if texto is None:  # tráfego do painel (JWT) — não é com este middleware
            await self.app(scope, receive, send)
            return
        if scope.get("method") == "OPTIONS":  # preflight de CORS
            await self.app(scope, receive, send)
            return

        from ..services import api_chaves

        ambiente = api_chaves.ambiente_da_chave(texto)
        if ambiente is not None and ambiente != api_chaves.ambiente_atual():
            await _responder(send, 401, "API_CHAVE_AMBIENTE_ERRADO")
            return
        chave = await api_chaves.resolver(texto)
        if chave is None:
            await _responder(send, 401, "API_CHAVE_INVALIDA")
            return

        dia = limitador.dia_atual()
        motivo = motivo_bloqueio(
            scope.get("method", "GET"),
            scope["path"],
            scope.get("query_string", b"").decode("latin-1"),
            chave.escopo,
        )
        if motivo:
            consumo.registrar(chave.id, dia, bloqueada=True)
            await _responder(send, 403, motivo)
            return

        await _semear_dia(chave.id)
        decisao = limitador.entrar(chave.id, chave.limite_por_minuto, chave.limite_por_dia)
        if not decisao.ok:
            consumo.registrar(chave.id, dia, bloqueada=True)
            extras = _cabecalhos_limite(decisao)
            extras["Retry-After"] = str(decisao.retry_after)
            if decisao.codigo == "API_LIMITE_GLOBAL":
                log.warning("teto global da API de parceiros atingido (chave %s)", chave.prefixo)
            await _responder(send, 429, decisao.codigo or "API_LIMITE_MINUTO", extras)
            return

        consumo.registrar(chave.id, dia, bloqueada=False)
        escopo = dict(scope)
        escopo["headers"] = headers
        estado = dict(scope.get("state") or {})
        estado["api_chave"] = chave
        escopo["state"] = estado
        limites = _cabecalhos_limite(decisao)

        async def send_com_limites(message: Message) -> None:
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                for k, v in limites.items():
                    h[k] = v
            await send(message)

        try:
            await self.app(escopo, receive, send_com_limites)
        finally:
            limitador.sair(chave.id)
