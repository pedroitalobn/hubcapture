"""A publicação do instrumento — leitura ÚNICA de um dado que só a FONTE afirma.

O gestor pergunta "saiu ou não saiu?" e o Hub respondia "Publicado" para uma
proposta que o TransfereGov mostrava como **Não Publicado**. A causa nunca foi
de coleta: era de LEITURA. Duas gerações do mesmo defeito:

1. "qualquer texto que não comece por 'não' é publicado" — um `sim` do campo
   vizinho virava afirmação categórica (corrigido pelo tri-estado);
2. **um VALOR em reais valendo por resposta**. `valor_publicado > 0` decidia
   "publicado" ANTES de olhar a situação, então uma proposta que a fonte dava
   como não publicada aparecia publicada por causa de uma coluna de dinheiro.

O cliente fechou a ambiguidade que a versão anterior deixou em aberto: **a
resposta está nos DADOS DA PROPOSTA do TransfereGov, no campo de situação da
publicação**. Logo, aqui:

- a decisão sai do que a fonte AFIRMA, em texto ou em data de publicação;
- dinheiro não é afirmação — `valor_publicado` continua sendo exibido como
  valor, nunca como veredito;
- a precedência entre as fontes do dado é EXPLÍCITA (consulta ao vivo > pacote
  > relatório), e não "quem gravou por último no jsonb".

Os três estados:

- `publicado`      — marcador afirmativo ou uma DATA de publicação (a fonte só
                     data o que saiu);
- `nao_publicado`  — marcador negativo explícito;
- `sem_informacao` — vazio, valor irreconhecível, ou aquele `sim` solto.

"Sem informação" é resposta legítima e é a mais honesta das três quando a fonte
não diz: o gestor confere no portal em vez de agir sobre uma certeza inventada.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
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

#: O campo é resposta a uma pergunta de sim/não — "Publicado", "Não Publicado",
#: "Publicado no D.O.U. de 12/03/2026". Texto mais longo que isto não é o campo:
#: é frase de outro lugar da página (o nome de um arquivo na lista de
#: documentos digitalizados chega a começar com "Publicação…"). Ler uma frase
#: como se fosse o campo é como o "Publicado" apareceu onde a fonte dizia o
#: contrário — na dúvida, `sem_informacao`.
_MAX_CARACTERES = 60


def _sem_acento(v: Any) -> str:
    texto = str(v or "").strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _contem(texto: str, marcadores: tuple[str, ...]) -> bool:
    """O marcador aparece como INÍCIO DE PALAVRA no texto.

    Substring pura casaria "publicado" dentro de "republicado" e — pior — dentro
    de qualquer frase que só mencione o assunto. O casamento é por palavra,
    aceitando sufixo (`publicado` casa `publicados`), que é como as fontes
    variam o termo.
    """
    return any(re.search(rf"(?<![0-9a-z]){re.escape(m)}", texto) for m in marcadores)


def _e_data(texto: str) -> bool:
    return bool(_DATA.match(texto))


def estado(situacao: Any) -> str:
    """O estado da publicação a partir do que a fonte AFIRMOU.

    Só entra texto que seja resposta à pergunta "saiu ou não saiu?" — nunca um
    valor em reais, que é dado de outra pergunta.
    """
    texto = _sem_acento(situacao)
    if not texto or len(texto) > _MAX_CARACTERES:
        return SEM_INFORMACAO
    if _contem(texto, _NEGATIVOS):
        return NAO_PUBLICADO
    if _contem(texto, _AFIRMATIVOS) or _e_data(texto):
        return PUBLICADO
    # Chega aqui o que NÃO é resposta a "saiu ou não saiu?": o `sim` do campo
    # vizinho, um código, um rótulo cortado. Não vira afirmação.
    return SEM_INFORMACAO


def esta_publicada(situacao: Any) -> bool:
    return estado(situacao) == PUBLICADO


# ── proveniência ───────────────────────────────────────────────────────────
# A situação da publicação chega por três caminhos que gravam no MESMO jsonb
# (`propostas.execucao`), em jobs diferentes e sem ordem garantida entre eles.
# Enquanto a leitura era a chave de topo, quem tinha razão era quem escrevesse
# por último — o pacote (~mensal) apagava a consulta ao vivo tanto quanto o
# contrário. A precedência agora é declarada aqui, e é a da VERACIDADE:
# o que a fonte mostra hoje vence o espelho de um mês atrás.
#
# Divergência com o portal também só é diagnosticável quando a tela diz DE ONDE
# veio o dado: o pacote e a consulta ao vivo discordam legitimamente por alguns
# dias, e isso não é defeito.
# O DOU abre a lista porque não é declaração de sistema nenhum: é o ATO. O
# extrato do contrato de repasse na Seção 3, com o município e a NE na mesma
# linha, é a publicação — e `services/publicacao_dou` só carimba esta chave
# quando encontrou a matéria, nunca para registrar que não encontrou (§56c).
ORIGEM_DOU = "extrato no Diário Oficial da União (Seção 3)"
_FONTES = (
    ("dou", ORIGEM_DOU),
    ("webapp", "consulta ao vivo do SIconv (dados da proposta)"),
    ("convenio", "pacote de dados do SIconv (convênio)"),
)
_ORIGEM_TOPO = "relatório da fonte"


@dataclass(frozen=True)
class Leitura:
    """O que a fonte disse sobre a publicação, e quem disse."""

    estado: str
    situacao: str | None = None
    origem: str | None = None


def declaracoes(execucao: dict | None) -> list[Leitura]:
    """Tudo que cada fonte DECLAROU, na ordem de veracidade.

    Só entra quem responde à pergunta; fonte que gravou algo irreconhecível fica
    de fora em vez de transformar um dado ilegível em "sem informação" quando
    outra fonte respondeu de verdade. Mais de um item = as fontes discordam, e
    é isso que a tela mostra lado a lado no double-check (§56c) — divergência
    entre o DOU e a ficha é informação, não defeito a esconder.
    """
    ex = execucao if isinstance(execucao, dict) else {}
    candidatos: list[tuple[Any, str]] = []
    for chave, rotulo in _FONTES:
        bloco = ex.get(chave)
        if isinstance(bloco, dict):
            candidatos.append((bloco.get("situacao_publicacao"), rotulo))
    candidatos.append((ex.get("situacao_publicacao"), _ORIGEM_TOPO))

    saida: list[Leitura] = []
    for bruto, rotulo in candidatos:
        situacao = estado(bruto)
        if situacao != SEM_INFORMACAO:
            saida.append(
                Leitura(estado=situacao, situacao=str(bruto).strip(), origem=rotulo)
            )
    return saida


def resolver(execucao: dict | None) -> Leitura:
    """A leitura da publicação, com a fonte que a sustenta — a primeira que
    responde na ordem de veracidade."""
    declaradas = declaracoes(execucao)
    return declaradas[0] if declaradas else Leitura(estado=SEM_INFORMACAO)


def do_execucao(execucao: dict | None) -> str:
    return resolver(execucao).estado


def origem(execucao: dict | None) -> str | None:
    """Rótulo de onde veio a situação da publicação que está sendo exibida."""
    return resolver(execucao).origem


def prova_dou(execucao: dict | None) -> dict | None:
    """O extrato do DOU que confirma a publicação, quando a conferência achou.

    É o que dá ao gestor o LINK para conferir — confirmação sem a matéria seria
    mais uma afirmação para acreditar.
    """
    ex = execucao if isinstance(execucao, dict) else {}
    prova = ex.get("dou")
    return prova if isinstance(prova, dict) and prova.get("url") else None


def data_publicacao(execucao: dict | None) -> date | None:
    """A data de publicação, quando a fonte a informa (no convênio ou na
    própria situação, que às vezes vem como a data).

    Só é devolvida quando a leitura diz PUBLICADO: data de publicação em
    proposta não publicada é resíduo de outro campo, e a tela a exibiria como
    "publicado em …" — a afirmação que este módulo existe para não fazer.
    """
    ex = execucao if isinstance(execucao, dict) else {}
    if resolver(ex).estado != PUBLICADO:
        return None
    convenio = ex.get("convenio")
    webapp = ex.get("webapp")
    prova = ex.get("dou")
    candidatos = [
        prova.get("publicado_em") if isinstance(prova, dict) else None,
        convenio.get("publicado_em") if isinstance(convenio, dict) else None,
        webapp.get("situacao_publicacao") if isinstance(webapp, dict) else None,
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
