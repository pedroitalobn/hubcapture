"""Helpers comuns de coluna (uuid pk, timestamps)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def updated_at_col() -> Mapped[datetime | None]:
    """`updated_at` carimbado no LADO PYTHON, não por `onupdate=func.now()`.

    Com `onupdate` em SQL, o valor é gerado pelo banco e o SQLAlchemy EXPIRA o
    atributo depois do UPDATE — a próxima leitura vira um refresh com I/O. Num
    endpoint async isso acontece fora do greenlet (`MissingGreenlet`), então
    todo router que serializa o objeto logo após o `flush()` quebrava com 500
    (foi o caso do PATCH do artigo do Class: salvar não salvava). Carimbar em
    Python deixa o valor conhecido no cliente: nada expira, nada faz I/O extra
    e o UPDATE não precisa de RETURNING (que, sob RLS, ainda leria pela policy
    de SELECT — ver §50).
    """
    return mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(UTC),
        nullable=True,
    )
