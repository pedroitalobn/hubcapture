"""A publicação do instrumento — leitura ÚNICA de um dado que a fonte publica
de três jeitos diferentes.

O gestor pergunta "saiu ou não saiu?" e o Hub respondia "Publicado" para uma
proposta que o TransfereGov mostrava como **Não Publicado** (ponto 09 do
feedback de 28/08). A causa é de leitura, não de coleta: a regra antiga era
"qualquer texto que não comece por 'não' é publicado", então um `sim`, um
código ou um pedaço de outra célula capturado pelo scraping viravam uma
afirmação categórica na faixa de destaque.

Aqui a leitura é TRI-ESTADO e o desconhecido não vira afirmação:

- `publicado`      — valor publicado > 0, marcador afirmativo ou uma DATA de
                     publicação (a fonte só data o que saiu);
- `nao_publicado`  — marcador negativo explícito;
- `sem_informacao` — vazio, valor irreconhecível, ou aquele `sim` solto.

"Sem informação" é resposta legítima e é a mais honesta das três quando a fonte
não diz: o gestor confere no portal em vez de agir sobre uma certeza inventada.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

PUBLICADO = "publicado"
NAO_PUBLICADO = "nao_publicado"
SEM_INFORMACAO = "sem_informacao"

ROTULOS = {
    PUBLICADO: "Publicado",
    NAO_PUBLICADO: "Não publicado",
    SEM_INFORMACAO: "Sem informação na fonte",
}

# A negativa é conferida ANTES da afirmativa: "não publicado" contém
# "publicado", e a ordem inversa leria toda negativa como positiva.
_NEGATIVOS = (
    "nao publicad",
    "nao public",
    "sem publicac",
    "aguardando public",
    "pendente de public",
    "a publicar",
    "nao houve public",
    # "Publicação Pendente" é o estado que o SIconv usa para o que ainda não
    # saiu — é resposta NEGATIVA, não ausência de informação.
    "pendente",
)
_AFIRMATIVOS = ("publicado", "publicada", "publicacao realizada", "publicado no dou")

_DATA = re.compile(r"^\s*(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})")


def _sem_acento(v: Any) -> str:
    texto = str(v or "").strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _positivo(valor: Any) -> bool:
    try:
        return Decimal(str(valor)) > 0
    except (TypeError, ValueError, InvalidOperation):
        return False


def _e_data(texto: str) -> bool:
    return bool(_DATA.match(texto))


def estado(situacao: Any, valor: Any = None) -> str:
    """O estado da publicação a partir do que a fonte informou."""
    if _positivo(valor):
        return PUBLICADO
    texto = _sem_acento(situacao)
    if not texto:
        return SEM_INFORMACAO
    if any(m in texto for m in _NEGATIVOS):
        return NAO_PUBLICADO
    if any(m in texto for m in _AFIRMATIVOS) or _e_data(texto):
        return PUBLICADO
    # Chega aqui o que NÃO é resposta a "saiu ou não saiu?": o `sim` do campo
    # vizinho, um código, um rótulo cortado. Não vira afirmação.
    return SEM_INFORMACAO


def esta_publicada(situacao: Any, valor: Any = None) -> bool:
    return estado(situacao, valor) == PUBLICADO


def do_execucao(execucao: dict | None) -> str:
    ex = execucao if isinstance(execucao, dict) else {}
    return estado(ex.get("situacao_publicacao"), ex.get("valor_publicado"))


# ── proveniência ───────────────────────────────────────────────────────────
# Divergência entre o Hub e o portal só é diagnosticável quando a tela diz DE
# ONDE veio o dado: a consulta ao vivo (webapp do SIconv) e o pacote público
# (~mensal) discordam legitimamente por alguns dias.
_ORIGENS = (
    ("webapp", "consulta ao vivo do SIconv"),
    ("convenio", "pacote de dados do SIconv (convênio)"),
)


def origem(execucao: dict | None) -> str | None:
    """Rótulo de onde veio a situação da publicação que está sendo exibida."""
    ex = execucao if isinstance(execucao, dict) else {}
    atual = ex.get("situacao_publicacao")
    if atual in (None, ""):
        return None
    for chave, rotulo in _ORIGENS:
        bloco = ex.get(chave)
        if isinstance(bloco, dict) and bloco.get("situacao_publicacao") == atual:
            return rotulo
    return "relatório da fonte"


def data_publicacao(execucao: dict | None) -> date | None:
    """A data de publicação, quando a fonte a informa (no convênio ou na
    própria situação, que às vezes vem como a data)."""
    ex = execucao if isinstance(execucao, dict) else {}
    convenio = ex.get("convenio")
    candidatos = [
        convenio.get("publicado_em") if isinstance(convenio, dict) else None,
        ex.get("data_publicacao"),
        ex.get("situacao_publicacao"),
    ]
    for bruto in candidatos:
        texto = str(bruto or "").strip()
        m = _DATA.match(texto)
        if not m:
            continue
        crua = m.group(1)
        try:
            if "/" in crua:
                d, mes, a = crua.split("/")
                return date(int(a), int(mes), int(d))
            return date.fromisoformat(crua)
        except ValueError:
            continue
    return None
