"""Codec vCard 3.0 — usado pelo CardDAV (Apple/iCloud) e pelo import/export .vcf.

Escopo proposital: as propriedades que a agenda do Hub usa (FN/N/ORG/TITLE/
EMAIL/TEL/ADR/NOTE/CATEGORIES/UID). Propriedades desconhecidas são ignoradas na
leitura — não quebram o parse.

Também é a rota de fuga sem credencial: quem não quiser conectar conta consegue
exportar um .vcf e importar no Google/Apple/Outlook na mão.
"""

from __future__ import annotations

import re
import uuid as _uuid

from ...schemas.contato import (
    ContatoCanonico,
    ContatoEmail,
    ContatoEndereco,
    ContatoTelefone,
)

_TIPO_EMAIL = {"work": "trabalho", "home": "pessoal", "internet": None, "pref": None}
_TIPO_TEL = {
    "cell": "celular",
    "mobile": "celular",
    "work": "trabalho",
    "home": "casa",
    "voice": None,
    "pref": None,
    "fax": "fax",
}
_TIPO_TEL_SAIDA = {"celular": "CELL", "trabalho": "WORK", "casa": "HOME", "fax": "FAX"}
_TIPO_EMAIL_SAIDA = {"trabalho": "WORK", "pessoal": "HOME"}


def _escapar(valor: str | None) -> str:
    if not valor:
        return ""
    return (
        valor.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _desescapar(valor: str) -> str:
    saida: list[str] = []
    escapando = False
    for ch in valor:
        if escapando:
            saida.append({"n": "\n", "N": "\n"}.get(ch, ch))
            escapando = False
        elif ch == "\\":
            escapando = True
        else:
            saida.append(ch)
    return "".join(saida)


def _partes(valor: str) -> list[str]:
    """Divide um valor estruturado em `;` respeitando escape."""
    campos: list[str] = []
    atual: list[str] = []
    escapando = False
    for ch in valor:
        if escapando:
            atual.append("\\" + ch)
            escapando = False
        elif ch == "\\":
            escapando = True
        elif ch == ";":
            campos.append("".join(atual))
            atual = []
        else:
            atual.append(ch)
    campos.append("".join(atual))
    return [_desescapar(c) for c in campos]


def _dobrar(linha: str) -> str:
    """Fold em 75 octetos (RFC 6350): continuação começa com espaço."""
    if len(linha.encode("utf-8")) <= 75:
        return linha
    pedacos: list[str] = []
    atual = ""
    for ch in linha:
        if len((atual + ch).encode("utf-8")) > 75:
            pedacos.append(atual)
            atual = " " + ch
        else:
            atual += ch
    pedacos.append(atual)
    return "\r\n".join(pedacos)


def serializar(canonico: ContatoCanonico, *, uid: str | None = None) -> str:
    """Canônico → vCard 3.0 (CRLF, como manda o RFC)."""
    linhas = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"UID:{uid or _uuid.uuid4()}",
        f"FN:{_escapar(canonico.nome_completo or canonico.nome)}",
        "N:"
        + ";".join(
            [_escapar(canonico.sobrenome), _escapar(canonico.nome), "", "", ""]
        ),
    ]
    if canonico.organizacao:
        linhas.append(f"ORG:{_escapar(canonico.organizacao)}")
    if canonico.cargo:
        linhas.append(f"TITLE:{_escapar(canonico.cargo)}")
    for email in canonico.emails:
        tipo = _TIPO_EMAIL_SAIDA.get((email.tipo or "").lower(), "INTERNET")
        linhas.append(f"EMAIL;TYPE={tipo}:{_escapar(email.valor)}")
    for tel in canonico.telefones:
        tipo = _TIPO_TEL_SAIDA.get((tel.tipo or "").lower(), "VOICE")
        linhas.append(f"TEL;TYPE={tipo}:{_escapar(tel.valor)}")
    for end in canonico.enderecos:
        tipo = "WORK" if (end.tipo or "").lower() == "trabalho" else "HOME"
        linhas.append(
            f"ADR;TYPE={tipo}:;;"
            + ";".join(
                [
                    _escapar(end.logradouro),
                    _escapar(end.cidade),
                    _escapar(end.uf),
                    _escapar(end.cep),
                    "",
                ]
            )
        )
    if canonico.tags:
        linhas.append("CATEGORIES:" + ",".join(_escapar(t) for t in canonico.tags))
    if canonico.notas:
        linhas.append(f"NOTE:{_escapar(canonico.notas)}")
    linhas.append("END:VCARD")
    return "\r\n".join(_dobrar(linha) for linha in linhas) + "\r\n"


def _desdobrar(texto: str) -> list[str]:
    linhas: list[str] = []
    for bruta in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if bruta[:1] in (" ", "\t") and linhas:
            linhas[-1] += bruta[1:]
        else:
            linhas.append(bruta)
    return linhas


def _tipos(params: list[str]) -> list[str]:
    saida: list[str] = []
    for p in params:
        nome, _, valor = p.partition("=")
        alvo = valor if valor else nome  # `TYPE=CELL` ou o legado `;CELL`
        saida.extend(t.strip().strip('"').lower() for t in alvo.split(","))
    return [t for t in saida if t and t != "type"]


def _primeiro_tipo(tipos: list[str], mapa: dict[str, str | None]) -> str | None:
    for t in tipos:
        if t in mapa and mapa[t]:
            return mapa[t]
    return None


def parsear(texto: str) -> list[ContatoCanonico]:
    """vCard(s) → canônicos. Aceita arquivo com vários cartões."""
    contatos: list[ContatoCanonico] = []
    atual: dict | None = None

    for linha in _desdobrar(texto):
        crua = linha.strip()
        if not crua:
            continue
        if crua.upper() == "BEGIN:VCARD":
            atual = {
                "nome": "",
                "sobrenome": None,
                "fn": None,
                "organizacao": None,
                "cargo": None,
                "emails": [],
                "telefones": [],
                "enderecos": [],
                "tags": [],
                "notas": None,
            }
            continue
        if crua.upper() == "END:VCARD":
            if atual is not None:
                contatos.append(_montar(atual))
            atual = None
            continue
        if atual is None:
            continue

        cabecalho, sep, valor = crua.partition(":")
        if not sep:
            continue
        pedacos = cabecalho.split(";")
        # Apple usa grupos (`item1.EMAIL`); o nome real vem depois do ponto.
        nome_prop = pedacos[0].split(".")[-1].upper()
        tipos = _tipos(pedacos[1:])

        if nome_prop == "FN":
            atual["fn"] = _desescapar(valor)
        elif nome_prop == "N":
            campos = _partes(valor)
            atual["sobrenome"] = campos[0] or None
            atual["nome"] = campos[1] if len(campos) > 1 else ""
        elif nome_prop == "ORG":
            atual["organizacao"] = _partes(valor)[0] or None
        elif nome_prop == "TITLE":
            atual["cargo"] = _desescapar(valor) or None
        elif nome_prop == "EMAIL" and valor.strip():
            atual["emails"].append(
                ContatoEmail(
                    tipo=_primeiro_tipo(tipos, _TIPO_EMAIL),
                    valor=_desescapar(valor).strip(),
                )
            )
        elif nome_prop == "TEL" and valor.strip():
            atual["telefones"].append(
                ContatoTelefone(
                    tipo=_primeiro_tipo(tipos, _TIPO_TEL),
                    valor=_desescapar(valor).strip(),
                )
            )
        elif nome_prop == "ADR":
            # ADR: caixa-postal;complemento;logradouro;cidade;UF;CEP;país
            campos = _partes(valor)
            campos += [""] * (7 - len(campos))
            atual["enderecos"].append(
                ContatoEndereco(
                    tipo="trabalho" if "work" in tipos else "pessoal",
                    logradouro=campos[2] or None,
                    cidade=campos[3] or None,
                    uf=campos[4] or None,
                    cep=campos[5] or None,
                )
            )
        elif nome_prop == "CATEGORIES":
            atual["tags"] = [
                _desescapar(t).strip()
                for t in re.split(r"(?<!\\),", valor)
                if _desescapar(t).strip()
            ]
        elif nome_prop == "NOTE":
            atual["notas"] = _desescapar(valor) or None

    return contatos


def _montar(dados: dict) -> ContatoCanonico:
    nome = dados["nome"] or ""
    sobrenome = dados["sobrenome"]
    if not nome and dados["fn"]:  # cartão só com FN → quebra em nome/sobrenome
        partes = dados["fn"].split()
        nome = partes[0]
        sobrenome = " ".join(partes[1:]) or None
    return ContatoCanonico(
        nome=nome or (dados["fn"] or "Sem nome"),
        sobrenome=sobrenome,
        organizacao=dados["organizacao"],
        cargo=dados["cargo"],
        emails=dados["emails"],
        telefones=dados["telefones"],
        enderecos=[e for e in dados["enderecos"] if e.model_dump(exclude_none=True)],
        notas=dados["notas"],
        tags=dados["tags"],
    )
