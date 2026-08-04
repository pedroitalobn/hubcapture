"""Verificação de segurança no boot — segredos de assinatura de token.

`JWT_SECRET`/`JWT_REFRESH_SECRET` têm valor PADRÃO no repositório (para o dev
local subir sem configurar nada). Em produção, esse padrão é crítico: quem lê o
código consegue forjar um token de qualquer usuário.

Política:
  - ambiente de DEV (APP_BASE_URL/CORS apontando para localhost): só avisa;
  - ambiente de PRODUÇÃO (domínio real): RECUSA subir, com a instrução exata.

O ambiente é inferido do `app_base_url` — não exige variável nova. Para casos
legítimos (homologação atrás de domínio, teste de fumaça), `PERMITIR_SEGREDO_PADRAO=true`
libera o boot mantendo o aviso no log.
"""

from __future__ import annotations

import logging

from .config import Settings

logger = logging.getLogger("hubcapture.seguranca")

# valores versionados no .env.example — nunca podem assinar token em produção
SEGREDOS_PADRAO = frozenset(
    {
        "troque-este-segredo-em-producao",
        "troque-este-segredo-de-refresh",
        "",
    }
)

_LOCAIS = ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal", ".local")

_INSTRUCAO = (
    "Defina JWT_SECRET e JWT_REFRESH_SECRET com valores fortes e distintos "
    "(ex.: `openssl rand -hex 32` para cada um) nas variáveis de ambiente do "
    "deploy e suba de novo. Trocar os segredos desloga todo mundo uma vez — "
    "é o esperado."
)


def eh_ambiente_local(settings: Settings) -> bool:
    """Dev local? Inferido da URL pública do app (sem variável nova)."""
    base = (settings.app_base_url or "").lower()
    if not base:
        return False
    return any(marca in base for marca in _LOCAIS)


def segredos_fracos(settings: Settings) -> list[str]:
    """Nomes das variáveis cujo segredo ainda é o padrão do repositório."""
    fracos = []
    if settings.jwt_secret in SEGREDOS_PADRAO:
        fracos.append("JWT_SECRET")
    if settings.jwt_refresh_secret in SEGREDOS_PADRAO:
        fracos.append("JWT_REFRESH_SECRET")
    return fracos


def verificar_segredos(settings: Settings) -> None:
    """Aborta o boot se estiver em produção com segredo padrão."""
    fracos = segredos_fracos(settings)
    if not fracos:
        return

    quais = " e ".join(fracos)
    if eh_ambiente_local(settings) or settings.permitir_segredo_padrao:
        logger.warning(
            "%s ainda usa(m) o segredo PADRÃO do repositório — aceitável só fora "
            "de produção. %s",
            quais,
            _INSTRUCAO,
        )
        return

    raise RuntimeError(
        f"BOOT ABORTADO: {quais} está(ão) com o segredo padrão do repositório e "
        f"o app aponta para um domínio público ({settings.app_base_url}). "
        f"Qualquer pessoa com acesso ao código poderia forjar tokens de login. "
        f"{_INSTRUCAO} (Para liberar conscientemente em homologação: "
        f"PERMITIR_SEGREDO_PADRAO=true.)"
    )
