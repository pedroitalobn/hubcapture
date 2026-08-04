"""Cifragem simétrica em repouso (Fernet) — segredos guardados no banco.

Usada pela config runtime (`configuracoes.valor`) e pelas credenciais das
integrações de contatos (`integracoes_contatos.credenciais`). A chave sai de
`CONFIG_SECRET_KEY` (fallback: `JWT_SECRET` em dev) derivada por SHA-256 para
caber no formato de 32 bytes do Fernet.
"""

from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


@lru_cache
def _fernet() -> Fernet:
    raw = settings.config_secret_key or settings.jwt_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    return Fernet(key)


def cifrar(valor: str) -> str:
    return _fernet().encrypt(valor.encode()).decode()


def decifrar(valor: str) -> str:
    return _fernet().decrypt(valor.encode()).decode()


def cifrar_json(dados: dict[str, Any]) -> str:
    """Serializa e cifra um dicionário (tokens OAuth, senha de app)."""
    return cifrar(json.dumps(dados, ensure_ascii=False, sort_keys=True))


def decifrar_json(valor: str | None) -> dict[str, Any]:
    """Decifra um blob JSON. Blob inválido (ex.: chave trocada) vira {} —
    o chamador trata como credencial ausente e pede reconexão."""
    if not valor:
        return {}
    try:
        return json.loads(decifrar(valor))
    except (InvalidToken, ValueError):
        return {}


def mascarar(valor: str) -> str:
    return "••••" + valor[-4:] if len(valor) >= 4 else "••••"
