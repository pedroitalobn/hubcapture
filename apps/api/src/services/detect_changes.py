"""Detecção de mudança da proposta monitorada — funções PURAS.

O `hash_conteudo` diz QUE algo mudou, nunca O QUE mudou — e era só isso que
existia aqui, então o alerta saía do mesmo jeito para qualquer alteração. Agora
a comparação é por CRITÉRIO (§53): `snapshot()` fotografa o estado material da
proposta (situação, publicação, empenho, pagamento, vigência, pareceres) e
`avaliar()` devolve uma mudança por critério LIGADO no monitoramento.

Sem banco e sem I/O de propósito: quem lê o cache é `services/oportunidades.py`,
que passa a proposta e as listas já carregadas. Assim o teste da regra roda sem
Postgres e a regra fica auditável.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from . import publicacao as publicacao_service
from .criterios_alerta import JANELA_VENCIMENTO_DIAS

# Campos do snapshot que cada critério observa. Campo fora desta tabela existe
# só para o payload (é o caso de `dias_para_vencer`, que muda TODO dia e, se
# comparado, geraria alerta diário sem nenhum fato novo).
CAMPOS_POR_CRITERIO: dict[str, tuple[str, ...]] = {
    "situacao": ("situacao", "movimentacao"),
    "prazo": ("prazos",),
    "pendencia": ("pendencias",),
    # publicação: `publicada` é o ESTADO (passou a publicada), os outros dois
    # cobrem a mudança de situação/valor dentro do estado já publicado
    "publicacao": ("publicada", "publicacao_situacao", "publicacao_valor"),
    "empenho": ("valor_empenhado", "empenhos_total", "empenhos_empenhado"),
    # empenho PAGO é o documento quitado; distinto do agregado da execução, que
    # a fonte publica com outra régua (e às vezes nem publica)
    "empenho_pago": ("empenhos_pago", "empenhos_liquidado"),
    "pagamento": ("valor_pago", "valor_liberado"),
    # parecer NOVO (id que não existia) ≠ parecer ATUALIZADO (veredito mudou):
    # são avisos diferentes para o gestor, então são critérios diferentes
    "parecer_novo": ("pareceres_ids",),
    "parecer": ("pareceres_veredito",),
    "emenda": ("emendas_ids", "emendas_valor", "emendas_empenhado", "emendas_pago"),
    "vencimento": ("fim_vigencia", "vencimento_proximo"),
}

# Campos que existem só para a FRASE do alerta (nunca comparados) e a quem
# pertencem. Sem este mapa a poda os deixaria para trás, gravando "0 pareceres"
# num monitoramento que sequer coletou parecer.
CAMPOS_DE_APOIO: dict[str, set[str]] = {
    "pareceres_total": {"parecer", "parecer_novo"},
    "emendas_total": {"emenda"},
    "emendas_autores": {"emenda"},
    "dias_para_vencer": {"vencimento"},
}

# rótulo humano de cada campo (entra na frase do alerta, do e-mail e do WhatsApp)
_ROTULO_CAMPO = {
    "situacao": "situação",
    "movimentacao": "movimentação",
    "prazos": "prazos",
    "pendencias": "pendências",
    "publicada": "publicação",
    "publicacao_situacao": "publicação",
    "publicacao_valor": "valor publicado",
    "valor_empenhado": "valor empenhado",
    "empenhos_total": "empenhos emitidos",
    "empenhos_empenhado": "valor empenhado (documentos)",
    "valor_pago": "valor pago",
    "valor_liberado": "valor liberado",
    "empenhos_pago": "valor pago (empenhos)",
    "empenhos_liquidado": "valor liquidado (empenhos)",
    "pareceres_ids": "pareceres",
    "pareceres_veredito": "veredito do parecer",
    "emendas_ids": "emendas",
    "emendas_valor": "valor da emenda",
    "emendas_empenhado": "emenda empenhada",
    "emendas_pago": "emenda paga",
    "fim_vigencia": "fim de vigência",
}


@dataclass(frozen=True)
class Mudanca:
    criterio: str
    payload: dict[str, Any]


def _json(valor: Any) -> Any:
    """Serializa para caber no jsonb do snapshot (o alerta é auditoria)."""
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {str(k): _json(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_json(v) for v in valor]
    return valor


def _decimal(valor: Any) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except (ArithmeticError, ValueError):
        return None


def _soma(itens: list[Any], campo: str) -> Decimal:
    return sum((getattr(x, campo, None) or Decimal("0") for x in itens), Decimal("0"))


def _data(valor: Any) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and valor.strip():
        try:
            return date.fromisoformat(valor.strip()[:10])
        except ValueError:
            return None
    return None


def _fim_vigencia(proposta: Any) -> date | None:
    """Vigência pela execução financeira e, sem ela, pelo prazo estruturado."""
    execucao = getattr(proposta, "execucao", None) or {}
    fim = _data(execucao.get("data_fim_vigencia"))
    if fim:
        return fim
    for prazo in getattr(proposta, "prazos", None) or []:
        if not isinstance(prazo, dict):
            continue
        if "vigência" in str(prazo.get("tipo") or "").lower():
            fim = _data(prazo.get("data_limite"))
            if fim:
                return fim
    return None


def _identidade(item: Any, *, prefixo: str, indice: int) -> str:
    """Id publicado pela fonte; sem ele, uma chave estável do próprio conteúdo.

    Cair no índice da lista seria armadilha (a ordem muda entre coletas e todo
    parecer/emenda pareceria novo), por isso o fallback é o hash do conteúdo.
    """
    ident = getattr(item, "id_externo", None) or getattr(item, "hash_conteudo", None)
    if ident:
        return str(ident)
    material = "|".join(
        str(getattr(item, campo, "") or "")
        for campo in ("numero_empenho", "numero", "codigo", "parlamentar", "data_parecer")
    )
    return f"{prefixo}:{material or indice}"


def _veredito(p: Any) -> str:
    """O que muda quando a análise ANDA: veredito + estado da análise."""
    return "|".join(
        str(x or "") for x in (getattr(p, "situacao", None), getattr(p, "situacao_analise", None))
    )


# publicação vem da fonte ora como texto ("Publicado"/"Não publicado"), ora
# como data, ora só como valor publicado — §28 coletou os dois sentidos. A
# leitura é a MESMA da tela (`services/publicacao`): duas regras separadas
# fariam o alerta discordar da página que ele manda o gestor abrir.
def _esta_publicada(situacao: Any, valor: Any) -> bool:
    return publicacao_service.esta_publicada(situacao, valor)


def snapshot(
    proposta: Any,
    *,
    pareceres: list[Any] | None = None,
    empenhos: list[Any] | None = None,
    emendas: list[Any] | None = None,
    hoje: date | None = None,
) -> dict[str, Any]:
    """Fotografia comparável do estado da proposta (tudo JSON-serializável)."""
    hoje = hoje or date.today()
    execucao = getattr(proposta, "execucao", None) or {}
    pareceres = list(pareceres or [])
    empenhos = list(empenhos or [])
    emendas = list(emendas or [])

    fim = _fim_vigencia(proposta)
    dias = (fim - hoje).days if fim else None
    empenhado_docs = _soma(empenhos, "valor_empenhado") - _soma(empenhos, "valor_anulado")
    ids_parecer = {
        _identidade(p, prefixo="parecer", indice=i): _veredito(p) for i, p in enumerate(pareceres)
    }
    publicacao_situacao = execucao.get("situacao_publicacao")
    publicacao_valor = execucao.get("valor_publicado")

    return {
        "situacao": proposta.situacao,
        "movimentacao": proposta.movimentacao,
        "prazos": _json(proposta.prazos),
        "pendencias": _json(proposta.pendencias),
        "publicada": _esta_publicada(publicacao_situacao, publicacao_valor),
        "publicacao_situacao": _json(publicacao_situacao),
        "publicacao_valor": _json(_decimal(publicacao_valor)),
        "valor_empenhado": _json(_decimal(execucao.get("valor_empenhado"))),
        "valor_liberado": _json(_decimal(execucao.get("valor_liberado"))),
        "valor_pago": _json(_decimal(execucao.get("valor_pago"))),
        "empenhos_total": len(empenhos),
        "empenhos_empenhado": str(max(empenhado_docs, Decimal("0"))),
        "empenhos_pago": str(_soma(empenhos, "valor_pago")),
        "empenhos_liquidado": str(_soma(empenhos, "valor_liquidado")),
        "pareceres_total": len(pareceres),
        # ids separados do veredito: parecer NOVO e parecer ATUALIZADO são
        # critérios distintos e cada um observa só o seu campo
        "pareceres_ids": sorted(ids_parecer),
        "pareceres_veredito": ids_parecer,
        "emendas_total": len(emendas),
        "emendas_ids": sorted(
            _identidade(e, prefixo="emenda", indice=i) for i, e in enumerate(emendas)
        ),
        "emendas_valor": str(_soma(emendas, "valor")),
        "emendas_empenhado": str(_soma(emendas, "valor_empenhado")),
        "emendas_pago": str(_soma(emendas, "valor_pago")),
        # só para a frase do alerta (não entra em comparação)
        "emendas_autores": sorted(
            {str(getattr(e, "parlamentar", "") or "").strip() for e in emendas} - {""}
        ),
        "fim_vigencia": fim.isoformat() if fim else None,
        # entrou na janela de vencimento? é ISTO que dispara o aviso — não o
        # número de dias, que muda a cada varredura
        "vencimento_proximo": bool(fim and 0 <= (dias or 0) <= JANELA_VENCIMENTO_DIAS),
        "dias_para_vencer": dias,
        "capturado_em": datetime.now().astimezone().isoformat(),
    }


def _diff(antes: dict[str, Any], depois: dict[str, Any], campos: tuple[str, ...]) -> dict:
    return {
        campo: {"antes": antes.get(campo), "depois": depois.get(campo)}
        for campo in campos
        if antes.get(campo) != depois.get(campo)
    }


def _legivel_veredito(valor: Any) -> str:
    """`situacao|situacao_analise` é chave de comparação, não texto de tela."""
    partes = [p for p in str(valor or "").split("|") if p.strip()]
    return " · ".join(partes) or "—"


def _frase_publicacao(diff: dict[str, Any], depois: dict[str, Any]) -> str:
    """O que aconteceu com a PUBLICAÇÃO — sem prometer o que não aconteceu.

    O alerta saía rotulado "Proposta publicada" com o texto "publicação
    atualizado(s)" para uma proposta que NÃO tinha sido publicada (ponto 11 do
    feedback): o critério cobre três fatos diferentes e a frase genérica não
    distinguia nenhum deles. Agora cada fato tem a sua frase, e a mudança de
    ESTADO (que é a notícia) vem antes das outras duas.
    """
    if "publicada" in diff:
        return (
            "Proposta publicada na fonte"
            if diff["publicada"]["depois"]
            else "Proposta deixou de constar como publicada na fonte"
        )
    if "publicacao_situacao" in diff:
        antes = str(diff["publicacao_situacao"]["antes"] or "").strip()
        atual = str(diff["publicacao_situacao"]["depois"] or "").strip()
        estado = publicacao_service.ROTULOS[publicacao_service.estado(atual)]
        if not antes:
            return f"A fonte passou a informar a situação da publicação: {atual} ({estado})"
        if not atual:
            return "A fonte deixou de informar a situação da publicação"
        return f"Situação da publicação: {antes} → {atual}"
    if "publicacao_valor" in diff:
        antes = diff["publicacao_valor"]["antes"]
        atual = diff["publicacao_valor"]["depois"]
        if antes in (None, ""):
            return f"Valor publicado informado pela fonte: {atual}"
        return f"Valor publicado: {antes} → {atual}"
    return "Publicação atualizada na fonte"


def _frase(criterio: str, diff: dict[str, Any], depois: dict[str, Any], extra: dict) -> str:
    if criterio == "parecer_novo":
        novos = extra.get("pareceres_novos") or []
        return (
            f"{len(novos)} novo(s) parecer(es) no plano de trabalho"
            if novos
            else "Novo parecer no plano de trabalho"
        )
    if criterio == "parecer":
        vereditos = extra.get("vereditos") or []
        if vereditos:
            de = _legivel_veredito(vereditos[0]["antes"])
            para = _legivel_veredito(vereditos[0]["depois"])
            return f"Parecer atualizado: {de} → {para}"
        return "Parecer atualizado"
    if criterio == "emenda":
        autores = depois.get("emendas_autores") or []
        quem = f" ({', '.join(autores[:2])})" if autores else ""
        if extra.get("emendas_novas"):
            return f"Emenda aplicada à proposta{quem}"
        return f"Valores da emenda atualizados{quem}"
    if criterio == "publicacao":
        return _frase_publicacao(diff, depois)
    if criterio == "vencimento":
        dias = depois.get("dias_para_vencer")
        fim = depois.get("fim_vigencia")
        if "fim_vigencia" in diff:
            return f"Fim de vigência alterado para {fim or '—'}"
        if isinstance(dias, int):
            return f"Convênio vence em {dias} dia(s) ({fim})"
        return "Vigência do convênio atualizada"
    partes = []
    for campo, valores in diff.items():
        rotulo = _ROTULO_CAMPO.get(campo, campo)
        antes, atual = valores["antes"], valores["depois"]
        if isinstance(antes, list) or isinstance(atual, list) or antes in (None, ""):
            partes.append(f"{rotulo} atualizado(s)")
        else:
            partes.append(f"{rotulo}: {antes} → {atual}")
    return "; ".join(partes[:3]) or "Atualização na proposta"


def avaliar(
    antes: dict[str, Any] | None,
    depois: dict[str, Any],
    criterios: set[str],
) -> list[Mudanca]:
    """Uma mudança por critério LIGADO que teve fato novo desde `antes`.

    Sem linha de base (`antes` ausente, ou sem os campos do critério — caso de
    quem ligou o critério depois) nada é emitido: comparar contra o vazio
    marcaria a proposta inteira como "mudou" na primeira varredura. A exceção é
    `vencimento`, que é ESTADO e não diferença — convênio já dentro da janela
    precisa avisar hoje, não no próximo movimento da fonte.
    """
    mudancas: list[Mudanca] = []
    for criterio, campos in CAMPOS_POR_CRITERIO.items():
        if criterio not in criterios:
            continue
        sem_base = antes is None or any(campo not in antes for campo in campos)
        if sem_base:
            if criterio == "vencimento" and depois.get("vencimento_proximo"):
                mudancas.append(
                    Mudanca(
                        criterio,
                        {
                            "mudou": {},
                            "resumo": _frase(criterio, {}, depois, {}),
                            "fim_vigencia": depois.get("fim_vigencia"),
                            "dias_para_vencer": depois.get("dias_para_vencer"),
                        },
                    )
                )
            continue

        diff = _diff(antes or {}, depois, campos)
        if not diff:
            continue
        extra: dict[str, Any] = {}
        base = antes or {}

        if criterio == "vencimento":
            # sair da janela (venceu, ou a data foi empurrada) não é aviso de
            # vencimento; entrar nela e mudar a data são.
            entrou = depois.get("vencimento_proximo") and not base.get("vencimento_proximo")
            if "fim_vigencia" not in diff and not entrou:
                continue
            extra["fim_vigencia"] = depois.get("fim_vigencia")
            extra["dias_para_vencer"] = depois.get("dias_para_vencer")

        if criterio == "parecer_novo":
            # parecer que SUMIU da fonte não é "novo parecer" — só o que entrou
            conhecidos = set(base.get("pareceres_ids") or [])
            novos = [i for i in depois.get("pareceres_ids") or [] if i not in conhecidos]
            if not novos:
                continue
            extra["pareceres_novos"] = novos

        if criterio == "parecer":
            # veredito de parecer que JÁ existia; o que acabou de entrar é do
            # `parecer_novo` e sairia duplicado aqui
            de = base.get("pareceres_veredito") or {}
            para = depois.get("pareceres_veredito") or {}
            vereditos = [
                {"parecer": pid, "antes": de[pid], "depois": para[pid]}
                for pid in de
                if pid in para and de[pid] != para[pid]
            ]
            if not vereditos:
                continue
            extra["vereditos"] = vereditos

        if criterio == "emenda":
            ja_vinculadas = set(base.get("emendas_ids") or [])
            novas = [i for i in depois.get("emendas_ids") or [] if i not in ja_vinculadas]
            extra["emendas_novas"] = novas
            extra["emendas_autores"] = depois.get("emendas_autores") or []

        payload: dict[str, Any] = {
            "mudou": diff,
            "resumo": _frase(criterio, diff, depois, extra),
            **extra,
        }
        mudancas.append(Mudanca(criterio, payload))
    return mudancas


def podar(snap: dict[str, Any], criterios: set[str]) -> dict[str, Any]:
    """Remove do snapshot os campos dos critérios DESLIGADOS.

    Guardar o campo de um critério que não foi coletado (pareceres/empenhos só
    são lidos quando o critério pede) gravaria um zero como se fosse o estado
    real: ao ligar o critério depois, a primeira varredura acusaria "3 pareceres
    novos" que já estavam lá. Sem o campo, `avaliar` trata como linha de base.
    """
    descartar = {
        campo
        for criterio, campos in CAMPOS_POR_CRITERIO.items()
        if criterio not in criterios
        for campo in campos
    }
    descartar |= {campo for campo, donos in CAMPOS_DE_APOIO.items() if not donos & criterios}
    return {k: v for k, v in snap.items() if k not in descartar}
