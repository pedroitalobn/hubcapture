"""Double-check da publicação — a NE no Diário Oficial da União, Seção 3.

A regra do cliente: **proposta publicada sempre tem nota de empenho** (nunca se
publica sem NE). Então dá para responder "saiu ou não saiu?" por um caminho
INDEPENDENTE do campo da ficha do TransfereGov — procurar no DOU Seção 3 o
extrato que traz aquela NE naquele município. Achou, foi publicado; e aí a
resposta não é mais a declaração de um sistema, é o ato.

Três disciplinas que este módulo não abre mão:

- **Só confirma.** Não achar no DOU nunca vira "não publicado": a busca é
  textual, o termo pode sair grafado de outro jeito, o portal pode estar fora do
  ar. Trocar isso produziria um falso NEGATIVO — o gestor achando que perdeu uma
  publicação que saiu, que é o mesmo defeito ao contrário.
- **Casamento com DUAS âncoras.** Um número de NE isolado se repete entre
  órgãos, e "999293" é um número como outro qualquer no meio do jornal. Toda
  matéria candidata precisa citar TAMBÉM o município — é o que o cliente pediu
  ("aquela NE para aquele município") e é o que impede publicação alheia virar
  prova da nossa.
- **A evidência fica guardada com a URL.** Confirmação sem o link do extrato é
  outra afirmação a acreditar; com o link, o gestor abre e confere.

O termo do instrumento é o **Código do Instrumento** (999293), não o número da
proposta (023950/2026): é o código que sai no extrato do DOU e o que nomeia o
PDF na lista de documentos digitalizados ("Publicação 999293.pdf").
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors import dou as dou_connector
from ..models.proposta import Proposta
from . import empenhos_proposta as empenhos_service
from . import municipios as municipios_service
from . import publicacao as publicacao_service

log = logging.getLogger(__name__)

#: quantos termos vão à busca por proposta. Cada termo é uma ida ao portal; a
#: resposta que interessa costuma vir na primeira NE.
MAX_TERMOS = 4

#: tamanho mínimo do nome do município para servir de âncora. "Ipê"/"Luz" são
#: nomes curtos demais para provar coisa alguma dentro de um jornal inteiro —
#: nesses casos vale o par NE + UF, e a conferência fica sem confirmar em vez
#: de confirmar por acidente.
MIN_NOME_MUNICIPIO = 5


@dataclass(frozen=True)
class Evidencia:
    """Uma matéria do DOU que prova a publicação desta proposta."""

    termo: str
    titulo: str
    data: str | None = None
    edicao: str | None = None
    secao: str | None = None
    pagina: str | None = None
    url: str | None = None
    #: PDF certificado da página do jornal — o documento que se anexa ao processo
    pdf_url: str | None = None
    trecho: str | None = None


@dataclass
class Conferencia:
    """O que a conferência no DOU respondeu — e o que ela NÃO respondeu."""

    #: ok = perguntamos e a fonte respondeu · erro = não deu para perguntar
    #: sem_termo = a proposta não tem NE nem código de instrumento p/ procurar
    status: str = "ok"
    confirmado: bool = False
    termos: list[str] = field(default_factory=list)
    evidencias: list[Evidencia] = field(default_factory=list)
    erro: str | None = None


async def _notas_de_empenho(session: AsyncSession, proposta: Proposta) -> list[str]:
    """Os números de NE da proposta, mais recentes primeiro.

    O elo empenho↔proposta é por número da proposta / plano de ação, não por FK
    — e a regra mora em `empenhos_proposta.listar`. Reescrevê-la aqui abriria a
    porta para a conferência procurar a NE de outra proposta no DOU.
    """
    vistos: list[str] = []
    for empenho in await empenhos_service.listar(session, proposta):
        m = dou_connector.RE_NOTA_EMPENHO.search(str(empenho.numero_empenho or ""))
        if m and m.group(1).upper() not in vistos:
            vistos.append(m.group(1).upper())
    return vistos


def codigo_instrumento(proposta: Proposta) -> str | None:
    """O Código do Instrumento — é ele que o extrato do DOU nomeia.

    Não confundir com o número da proposta: na ficha eles são campos diferentes
    (proposta 023950/2026, instrumento 999293) e quem sai no jornal é o segundo.
    """
    ex = proposta.execucao if isinstance(proposta.execucao, dict) else {}
    webapp = ex.get("webapp") if isinstance(ex.get("webapp"), dict) else {}
    convenio = ex.get("convenio") if isinstance(ex.get("convenio"), dict) else {}
    for bruto in (
        webapp.get("instrumento"),
        ex.get("instrumento"),
        convenio.get("numero"),
    ):
        digitos = dou_connector.so_digitos(bruto)
        if len(digitos) >= 5:
            return digitos
    return None


async def _ancora_municipio(session: AsyncSession, proposta: Proposta) -> str | None:
    """O nome do município normalizado — a 2ª âncora do casamento."""
    nome = proposta.municipio_nome
    if not nome and proposta.municipio_ibge:
        achado = await municipios_service.nome_uf_por_ibge(proposta.municipio_ibge)
        nome = achado[0] if achado else None
    plano = dou_connector.normalizar(nome)
    return plano if len(plano) >= MIN_NOME_MUNICIPIO else None


def casa(materia: dou_connector.Publicacao, termo: str, municipio: str) -> bool:
    """A matéria prova ESTA proposta?

    Exige as duas âncoras no mesmo texto. O DOU sai em coluna estreita e o
    extrato chega com espaço no meio das palavras ("MUNIC ÍPIO DE APUIAR ÉS"),
    então a comparação é feita também sem espaço nenhum — senão o casamento
    falharia justamente nas matérias reais.
    """
    texto = dou_connector.normalizar(f"{materia.titulo} {materia.texto}")
    compacto = texto.replace(" ", "")
    alvo_termo = dou_connector.normalizar(termo)
    tem_termo = alvo_termo in texto or alvo_termo.replace(" ", "") in compacto
    tem_municipio = municipio in texto or municipio.replace(" ", "") in compacto
    return tem_termo and tem_municipio


async def conferir(session: AsyncSession, proposta: Proposta) -> Conferencia:
    """Procura no DOU Seção 3 a prova da publicação desta proposta."""
    termos = await _notas_de_empenho(session, proposta)
    codigo = codigo_instrumento(proposta)
    if codigo and codigo not in termos:
        termos.append(codigo)
    termos = termos[:MAX_TERMOS]
    municipio = await _ancora_municipio(session, proposta)
    if not termos or not municipio:
        return Conferencia(
            status="sem_termo",
            termos=termos,
            erro=(
                "sem nota de empenho nem código de instrumento para procurar"
                if not termos
                else "município sem nome resolvido para ancorar a busca"
            ),
        )

    conferencia = Conferencia(termos=termos)
    for termo in termos:
        try:
            materias = await dou_connector.buscar(termo)
        except Exception as exc:  # noqa: BLE001 — fonte fora do ar não é veredito
            conferencia.status = "erro"
            conferencia.erro = str(exc)
            log.warning("DOU: conferência de %s falhou: %s", termo, exc)
            continue
        for materia in materias:
            if not casa(materia, termo, municipio):
                continue
            conferencia.status = "ok"
            conferencia.erro = None
            conferencia.confirmado = True
            conferencia.evidencias.append(
                Evidencia(
                    termo=termo,
                    titulo=materia.titulo or "Extrato publicado no DOU",
                    data=materia.data.isoformat() if materia.data else None,
                    edicao=materia.edicao,
                    secao=materia.secao,
                    pagina=materia.pagina,
                    url=materia.url,
                    pdf_url=materia.pdf_url,
                    trecho=(materia.texto or "")[:400] or None,
                )
            )
            break
        if conferencia.confirmado:
            break
    return conferencia


def carimbo(conferencia: Conferencia) -> dict | None:
    """O bloco `execucao.dou` — gravado SÓ quando há prova.

    Confirmação não encontrada não carimba nada: guardar "não achei" como se
    fosse resposta faria a leitura tri-estado herdar um negativo que o DOU não
    deu (§56c). O que fica registrado é a tentativa mal-sucedida, no log e no
    status da resposta.
    """
    if not conferencia.confirmado or not conferencia.evidencias:
        return None
    prova = conferencia.evidencias[0]
    return {
        "situacao_publicacao": "Publicado",
        "nota_empenho": prova.termo,
        "publicado_em": prova.data,
        "edicao": prova.edicao,
        "secao": prova.secao,
        "pagina": prova.pagina,
        "url": prova.url,
        # O PDF certificado é o que o gestor anexa ao processo — a página web
        # não serve de comprovante. Guardamos a REFERÊNCIA, nunca os bytes
        # (§56): o documento é público na origem e cachear binário de terceiro
        # cria um acervo que ninguém pediu para manter.
        "pdf_url": prova.pdf_url,
        "titulo": prova.titulo,
        "verificado_em": datetime.now(UTC).isoformat(),
    }


async def conferir_e_carimbar(
    session: AsyncSession, proposta_id: uuid.UUID
) -> tuple[Proposta, Conferencia] | None:
    """Confere no DOU e grava a prova em `propostas.execucao.dou`.

    O carimbo entra na MESMA chave que `publicacao.resolver` lê no topo da
    precedência: a partir daí a tela, o alerta e o PDF passam a dizer
    "publicado" com o link do extrato — sem nenhum deles saber do DOU.
    """
    proposta = (
        await session.execute(
            select(Proposta).where(
                Proposta.id == proposta_id, Proposta.excluido_em.is_(None)
            )
        )
    ).scalar_one_or_none()
    if proposta is None:
        return None
    conferencia = await conferir(session, proposta)
    marca = carimbo(conferencia)
    if marca:
        execucao = dict(proposta.execucao or {})
        execucao["dou"] = marca
        proposta.execucao = execucao
        await session.flush()
    return proposta, conferencia


def leitura_com_dou(proposta: Proposta) -> publicacao_service.Leitura:
    """Atalho de leitura já com a prova do DOU (quando ela existe)."""
    return publicacao_service.resolver(proposta.execucao)
