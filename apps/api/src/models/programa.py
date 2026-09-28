"""Programa do TransfereGov — o que um município PODE captar (§63).

Catálogo NACIONAL vindo do pacote SIconv (`programa.csv`), sem RLS: o programa
não pertence a um município. Quem decide se "Apuiarés pode se inscrever" é o
serviço (`services/programas.py`), cruzando a UF habilitada e a natureza
jurídica aceita pelo programa com o território do gestor.

O arquivo publica UMA LINHA POR (programa × UF × natureza jurídica); a carga
agrega por `ID_PROGRAMA` e guarda as listas em `ufs`/`naturezas`/`modalidades`.
Lista vazia = a fonte não restringiu (vale para todos).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TEXT
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from ..db.base import Base
from ._mixins import created_at_col, updated_at_col, uuid_pk


class Programa(Base):
    __tablename__ = "programas"
    __table_args__ = (
        UniqueConstraint("fonte", "id_externo", name="uq_programas_fonte_id_externo"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    fonte: Mapped[str] = mapped_column(String(32))
    id_externo: Mapped[str] = mapped_column(String(64))
    codigo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nome: Mapped[str | None] = mapped_column(Text, nullable=True)
    orgao_superior: Mapped[str | None] = mapped_column(String(255), nullable=True)
    orgao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    situacao: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ano: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acao_orcamentaria: Mapped[str | None] = mapped_column(String(255), nullable=True)
    modalidades: Mapped[list[str] | None] = mapped_column(ARRAY(TEXT), nullable=True)
    naturezas: Mapped[list[str] | None] = mapped_column(ARRAY(TEXT), nullable=True)
    ufs: Mapped[list[str] | None] = mapped_column(ARRAY(TEXT), nullable=True)
    disponibilizado_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    # As três janelas do SIconv — cada uma é uma porta de entrada diferente:
    # proposta voluntária (qualquer proponente elegível), emenda parlamentar
    # (precisa de indicação) e beneficiário específico (lista do concedente).
    inicio_proposta: Mapped[date | None] = mapped_column(Date, nullable=True)
    fim_proposta: Mapped[date | None] = mapped_column(Date, nullable=True)
    inicio_emenda: Mapped[date | None] = mapped_column(Date, nullable=True)
    fim_emenda: Mapped[date | None] = mapped_column(Date, nullable=True)
    inicio_beneficiario: Mapped[date | None] = mapped_column(Date, nullable=True)
    fim_beneficiario: Mapped[date | None] = mapped_column(Date, nullable=True)
    municipios_historico: Mapped[list[str] | None] = mapped_column(ARRAY(TEXT), nullable=True)
    detalhe: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    hash_conteudo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cache_atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime | None] = updated_at_col()
