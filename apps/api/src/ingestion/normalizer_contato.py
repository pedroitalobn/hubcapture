"""Normalização de contatos: canonização, chave de dedup, hash e merge.

O motor de sync compara **hash do conteúdo canônico**, não payload de provedor
— assim "mesmo contato escrito diferente" (e-mail em caixa alta, telefone com
máscara) não vira uma mudança falsa e o sync não fica escrevendo em looping.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from ..models.contato import Contato
from ..schemas.contato import (
    ContatoCanonico,
    ContatoEmail,
    ContatoEndereco,
    ContatoTelefone,
)

_SO_DIGITOS = re.compile(r"\D+")


def normalizar_email(valor: str | None) -> str | None:
    if not valor:
        return None
    limpo = valor.strip().lower()
    return limpo or None


def normalizar_telefone(valor: str | None) -> str | None:
    """Telefone em formato comparável (E.164 quando dá para inferir o Brasil).

    Não é validação — é chave de comparação: "(11) 98888-7777", "11988887777" e
    "+55 11 98888-7777" precisam colidir no dedup.
    """
    if not valor:
        return None
    tem_mais = valor.strip().startswith("+")
    digitos = _SO_DIGITOS.sub("", valor)
    if not digitos:
        return None
    if tem_mais:
        return f"+{digitos}"
    if len(digitos) in (10, 11):  # fixo/celular nacional sem DDI
        return f"+55{digitos}"
    if len(digitos) in (12, 13) and digitos.startswith("55"):
        return f"+{digitos}"
    return digitos


def _slug(texto: str | None) -> str:
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


def calcular_chave_dedup(canonico: ContatoCanonico) -> str | None:
    """E-mail principal > telefone principal > nome+organização.

    Deliberadamente NÃO é constraint única no banco: em gabinete/secretaria é
    comum duas pessoas dividirem o mesmo e-mail ou ramal.
    """
    for email in canonico.emails:
        chave = normalizar_email(email.valor)
        if chave:
            return f"email:{chave}"
    for tel in canonico.telefones:
        chave = normalizar_telefone(tel.valor)
        if chave:
            return f"tel:{chave}"
    nome = _slug(canonico.nome_completo)
    if not nome:
        return None
    org = _slug(canonico.organizacao)
    return f"nome:{nome}" + (f"@{org}" if org else "")


def _material_hash(canonico: ContatoCanonico) -> dict[str, Any]:
    return {
        "nome": (canonico.nome or "").strip(),
        "sobrenome": (canonico.sobrenome or "").strip(),
        "organizacao": (canonico.organizacao or "").strip(),
        "cargo": (canonico.cargo or "").strip(),
        "emails": sorted(e for e in (normalizar_email(x.valor) for x in canonico.emails) if e),
        "telefones": sorted(
            t for t in (normalizar_telefone(x.valor) for x in canonico.telefones) if t
        ),
        "enderecos": sorted(
            json.dumps(e.model_dump(exclude_none=True), sort_keys=True) for e in canonico.enderecos
        ),
        "notas": (canonico.notas or "").strip(),
        "tags": sorted({t.strip().lower() for t in canonico.tags if t.strip()}),
    }


def calcular_hash(canonico: ContatoCanonico) -> str:
    payload = json.dumps(_material_hash(canonico), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _dedup_lista(itens: list[Any], normalizador) -> list[Any]:
    """Remove repetidos preservando a ordem (o 1º é o principal)."""
    vistos: set[str] = set()
    saida: list[Any] = []
    for item in itens:
        chave = normalizador(item.valor)
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        saida.append(item)
    return saida


def canonizar(canonico: ContatoCanonico) -> ContatoCanonico:
    """Limpa listas, calcula `chave_dedup` e `hash_conteudo`."""
    dados = canonico.model_copy(deep=True)
    dados.nome = (dados.nome or "").strip() or "Sem nome"
    dados.emails = _dedup_lista(dados.emails, normalizar_email)
    dados.telefones = _dedup_lista(dados.telefones, normalizar_telefone)
    dados.tags = sorted({t.strip() for t in dados.tags if t and t.strip()})
    dados.chave_dedup = calcular_chave_dedup(dados)
    dados.hash_conteudo = calcular_hash(dados)
    return dados


def do_modelo(contato: Contato) -> ContatoCanonico:
    """Linha do banco → canônico (o que vai para os provedores)."""
    return canonizar(
        ContatoCanonico(
            nome=contato.nome,
            sobrenome=contato.sobrenome,
            organizacao=contato.organizacao,
            cargo=contato.cargo,
            emails=[ContatoEmail(**e) for e in (contato.emails or [])],
            telefones=[ContatoTelefone(**t) for t in (contato.telefones or [])],
            enderecos=[ContatoEndereco(**e) for e in (contato.enderecos or [])],
            notas=contato.notas,
            tags=list(contato.tags or []),
            municipio_ibge=contato.municipio_ibge,
            uf=contato.uf,
            origem=contato.origem,
        )
    )


def aplicar_no_modelo(contato: Contato, canonico: ContatoCanonico) -> None:
    """Canônico → linha do banco (não mexe em `usuario_id`/`origem` existentes)."""
    dados = canonizar(canonico)
    contato.nome = dados.nome
    contato.sobrenome = dados.sobrenome
    contato.organizacao = dados.organizacao
    contato.cargo = dados.cargo
    contato.emails = [e.model_dump(exclude_none=True) for e in dados.emails]
    contato.telefones = [t.model_dump(exclude_none=True) for t in dados.telefones]
    contato.enderecos = [e.model_dump(exclude_none=True) for e in dados.enderecos]
    contato.notas = dados.notas
    contato.tags = dados.tags
    if dados.municipio_ibge:
        contato.municipio_ibge = dados.municipio_ibge
    if dados.uf:
        contato.uf = dados.uf
    contato.chave_dedup = dados.chave_dedup
    contato.hash_conteudo = dados.hash_conteudo


def mesclar(base: ContatoCanonico, novo: ContatoCanonico) -> ContatoCanonico:
    """União não-destrutiva: `novo` preenche o que falta em `base`.

    Usada quando os dois lados mudaram (conflito) e quando um contato importado
    casa com um já existente na agenda — em vez de escolher um e perder o outro,
    soma e-mails/telefones/tags e só usa `novo` nos escalares vazios em `base`.
    """
    juntos = base.model_copy(deep=True)
    for campo in ("sobrenome", "organizacao", "cargo", "notas", "municipio_ibge", "uf"):
        if not getattr(juntos, campo) and getattr(novo, campo):
            setattr(juntos, campo, getattr(novo, campo))
    juntos.emails = _dedup_lista([*juntos.emails, *novo.emails], normalizar_email)
    juntos.telefones = _dedup_lista([*juntos.telefones, *novo.telefones], normalizar_telefone)
    conhecidos = {
        json.dumps(e.model_dump(exclude_none=True), sort_keys=True) for e in juntos.enderecos
    }
    for end in novo.enderecos:
        chave = json.dumps(end.model_dump(exclude_none=True), sort_keys=True)
        if chave not in conhecidos:
            conhecidos.add(chave)
            juntos.enderecos.append(end)
    juntos.tags = sorted({*juntos.tags, *novo.tags})
    return canonizar(juntos)
