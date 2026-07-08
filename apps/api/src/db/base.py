"""Base declarativa do SQLAlchemy. Todos os models herdam de `Base`."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
