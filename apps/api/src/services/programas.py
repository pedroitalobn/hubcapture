"""Oportunidades — programas em que os municípios do território PODEM e DEVEM
se inscrever (§63).

O catálogo (`programas`) é nacional; este serviço faz o recorte. Para cada
programa com janela aberta (ou abrindo em breve), responde:

- **PODE?** — o programa habilita a UF do município (`ufs`) e aceita ente
  municipal como proponente (`naturezas`: administração pública municipal ou
  consórcio público). Lista vazia = a fonte não restringiu.
- **DEVE?** — sinais de aderência, cada um com a frase que o explica:
  o município já propôs neste programa (`municipios_historico`), o tema casa
  com as ÁREAS do perfil (categorias da §32 sobre o nome do programa) ou o
  órgão concedente é um com quem o município já tem proposta no cache.

As três janelas do SIconv são portas diferentes e a tela precisa dizer qual:
proposta voluntária (qualquer proponente elegível), emenda parlamentar (exige
indicação de um parlamentar) e beneficiário específico (só quem o concedente
listou). As funções de decisão são PURAS — testáveis sem banco.
"""

from __future__ import annotations

import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai import categorias as categorias_ia
from ..models.municipio_interesse import MunicipioInteresse
from ..models.preferencias import PreferenciasUsuario
from ..models.programa import Programa
from ..models.proposta import Proposta
from . import _territorio
from .municipios import uf_do_ibge

#: A consulta oficial do TransfereGov — o gestor confere/inscreve por lá.
URL_CONSULTA = (
    "https://discricionarias.transferegov.sistema.gov.br/voluntarias/programa/"
    "ConsultarPrograma/ConsultarPrograma.do"
)

#: Janela que abre dentro disso entra como "abre em breve": o gestor prepara a
#: proposta antes, em vez de descobrir no dia.
DIAS_EM_BREVE = 30
#: Fecha dentro disso → "encerrando" (card de destaque e tom de urgência).
DIAS_ENCERRANDO = 15

JANELAS: dict[str, dict[str, str]] = {
    "voluntaria": {
        "rotulo": "Proposta voluntária",
        "como": "Aberta a qualquer proponente elegível — é a porta direta do município.",
    },
    "emenda": {
        "rotulo": "Emenda parlamentar",
        "como": "Precisa de indicação de um parlamentar (emenda) para o município.",
    },
    "beneficiario": {
        "rotulo": "Beneficiário específico",
        "como": "Só para os proponentes que o concedente indicou no programa.",
    },
}

_SITUACOES_FECHADAS = ("inativ", "cancel", "exclu", "encerr", "suspens")


def _sem_acento(texto: str | None) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if not unicodedata.combining(c)
    ).lower()


def aceita_municipio(naturezas: list[str] | None) -> bool:
    """O programa aceita PREFEITURA (ou consórcio de municípios) como proponente?

    Sem natureza informada a fonte não restringiu — esconder seria afirmar uma
    exclusão que ela não fez.
    """
    if not naturezas:
        return True
    return any("municip" in _sem_acento(n) or "consorcio" in _sem_acento(n) for n in naturezas)


def ufs_validas(ufs: list[str] | None) -> set[str]:
    """Só siglas de 2 letras. Valor fora disso ("TODAS", nome por extenso) não
    é recorte que se possa aplicar com segurança — vira "sem restrição"."""
    return {u.strip().upper() for u in (ufs or []) if len(u.strip()) == 2 and u.strip().isalpha()}


def habilita_uf(ufs: list[str] | None, uf: str | None) -> bool:
    validas = ufs_validas(ufs)
    if not validas:
        return True
    return bool(uf) and uf.upper() in validas


def situacao_aberta(situacao: str | None) -> bool:
    s = _sem_acento(situacao)
    return not any(m in s for m in _SITUACOES_FECHADAS)


@dataclass(frozen=True)
class Janela:
    tipo: str
    inicio: date | None
    fim: date
    status: str  # 'aberta' | 'em_breve'
    dias_restantes: int  # até o FIM (aberta) ou até o INÍCIO (em breve)


def janelas_ativas(p: Programa, hoje: date) -> list[Janela]:
    """Janelas abertas hoje ou abrindo em até `DIAS_EM_BREVE` dias."""
    saida: list[Janela] = []
    for tipo, ini, fim in (
        ("voluntaria", p.inicio_proposta, p.fim_proposta),
        ("emenda", p.inicio_emenda, p.fim_emenda),
        ("beneficiario", p.inicio_beneficiario, p.fim_beneficiario),
    ):
        if fim is None or fim < hoje:
            continue
        if ini is None or ini <= hoje:
            saida.append(Janela(tipo, ini, fim, "aberta", (fim - hoje).days))
        elif (ini - hoje).days <= DIAS_EM_BREVE:
            saida.append(Janela(tipo, ini, fim, "em_breve", (ini - hoje).days))
    return saida


_MOTIVOS_FORTES = frozenset({"historico", "area"})


@dataclass
class Motivo:
    chave: str
    texto: str


@dataclass
class Avaliacao:
    """O veredito de UM programa para o recorte de municípios."""

    janelas: list[Janela]
    municipios: list[dict]
    categorias: list[str]
    motivos: list[Motivo] = field(default_factory=list)

    @property
    def recomendado(self) -> bool:
        # o órgão conhecido é contexto, não recomendação: quase todo município
        # já tratou com os grandes ministérios, e contar isso marcaria a lista
        # inteira como "recomendada" — que é o mesmo que não recomendar nada
        return any(m.chave in _MOTIVOS_FORTES for m in self.motivos)

    @property
    def prazo_final(self) -> date | None:
        abertas = [j.fim for j in self.janelas if j.status == "aberta"]
        return min(abertas) if abertas else None


def avaliar(
    p: Programa,
    municipios: list[dict],
    *,
    hoje: date,
    areas: set[str],
    orgaos_conhecidos: dict[str, set[str]],
) -> Avaliacao | None:
    """Pode o recorte se inscrever neste programa? Se sim, por que DEVERIA?

    `municipios` = [{ibge, nome, uf}] do recorte; `orgaos_conhecidos` = órgão
    superior (normalizado) → IBGEs que já têm proposta com ele no cache.
    Devolve None quando nenhum município do recorte pode se inscrever.
    """
    if not situacao_aberta(p.situacao):
        return None
    janelas = janelas_ativas(p, hoje)
    if not janelas:
        return None

    historico = set(p.municipios_historico or [])
    orgao_norm = _sem_acento(p.orgao_superior).strip()
    com_orgao = orgaos_conhecidos.get(orgao_norm, set()) if orgao_norm else set()

    elegiveis = [
        {**m, "historico": m["ibge"] in historico, "conhece_orgao": m["ibge"] in com_orgao}
        for m in municipios
        if habilita_uf(p.ufs, m.get("uf"))
    ]
    if not elegiveis:
        return None

    cats = categorias_ia.classificar(
        p.nome, p.acao_orcamentaria, (p.detalhe or {}).get("descricao")
    )
    av = Avaliacao(janelas=janelas, municipios=elegiveis, categorias=cats)

    ja_propos = [m for m in elegiveis if m["historico"]]
    if ja_propos:
        nomes = ", ".join(m.get("nome") or m["ibge"] for m in ja_propos[:3])
        av.motivos.append(
            Motivo("historico", f"{nomes} já apresentou proposta neste programa antes.")
        )
    casadas = [c for c in cats if c in areas]
    if casadas:
        rotulos = ", ".join(categorias_ia.ROTULOS[c] for c in casadas)
        av.motivos.append(Motivo("area", f"Tema alinhado às áreas do seu perfil: {rotulos}."))
    if com_orgao and not ja_propos:
        av.motivos.append(
            Motivo(
                "orgao",
                "O município já tem proposta com este órgão concedente — o caminho é conhecido.",
            )
        )
    return av


def _ordem(av: Avaliacao) -> tuple:
    """Recomendados primeiro; depois quem fecha antes; em breve por último."""
    aberta = av.prazo_final is not None
    return (
        0 if av.recomendado else 1,
        0 if aberta else 1,
        (av.prazo_final or date.max),
        -len(av.motivos),
    )


# ---------------------------------------------------------------- leitura


async def _territorio_do_usuario(
    session: AsyncSession, usuario_id: uuid.UUID, municipio: _territorio.Municipios
) -> list[dict]:
    stmt = select(MunicipioInteresse).where(MunicipioInteresse.usuario_id == usuario_id)
    stmt = _territorio.filtrar(stmt, MunicipioInteresse.ibge, municipio)
    linhas = (await session.execute(stmt)).scalars().all()
    return [
        {"ibge": m.ibge, "nome": m.nome, "uf": (m.uf or uf_do_ibge(m.ibge) or None)}
        for m in sorted(linhas, key=lambda m: m.nome or m.ibge)
    ]


async def _areas(session: AsyncSession, usuario_id: uuid.UUID) -> set[str]:
    pref = (
        await session.execute(
            select(PreferenciasUsuario).where(PreferenciasUsuario.usuario_id == usuario_id)
        )
    ).scalar_one_or_none()
    return set(pref.areas or []) if pref else set()


async def _orgaos_conhecidos(session: AsyncSession, ibges: list[str]) -> dict[str, set[str]]:
    """Órgão superior → municípios do recorte com proposta dele no cache (RLS)."""
    if not ibges:
        return {}
    linhas = await session.execute(
        select(Proposta.orgao_superior, Proposta.municipio_ibge)
        .where(
            Proposta.municipio_ibge.in_(ibges),
            Proposta.excluido_em.is_(None),
            Proposta.orgao_superior.is_not(None),
        )
        .distinct()
    )
    mapa: dict[str, set[str]] = {}
    for orgao, ibge in linhas:
        mapa.setdefault(_sem_acento(orgao).strip(), set()).add(ibge)
    return mapa


async def _candidatos(session: AsyncSession, hoje: date) -> list[Programa]:
    """Programas com alguma janela aberta ou abrindo em breve — o resto nem sai
    do banco."""
    limite_inicio = date.fromordinal(hoje.toordinal() + DIAS_EM_BREVE)
    abertas = []
    for ini, fim in (
        (Programa.inicio_proposta, Programa.fim_proposta),
        (Programa.inicio_emenda, Programa.fim_emenda),
        (Programa.inicio_beneficiario, Programa.fim_beneficiario),
    ):
        abertas.append((fim >= hoje) & (or_(ini.is_(None), ini <= limite_inicio)))
    return list((await session.execute(select(Programa).where(or_(*abertas)))).scalars().all())


async def estado_catalogo(session: AsyncSession) -> dict:
    total, atualizado = (
        await session.execute(
            select(func.count(Programa.id), func.max(Programa.cache_atualizado_em))
        )
    ).one()
    return {"total": int(total or 0), "atualizado_em": atualizado}


def _casa_busca(p: Programa, q: str) -> bool:
    alvo = _sem_acento(" ".join(filter(None, [p.nome, p.codigo, p.orgao_superior, p.orgao])))
    return all(t in alvo for t in _sem_acento(q).split())


async def listar(
    session: AsyncSession,
    usuario_id: uuid.UUID,
    *,
    municipio: _territorio.Municipios = None,
    q: str | None = None,
    orgao: str | None = None,
    categoria: str | None = None,
    janela: str | None = None,
    apenas_recomendados: bool = False,
    incluir_outras_naturezas: bool = False,
    hoje: date | None = None,
) -> dict:
    """As oportunidades do recorte, com facetas e o estado do catálogo."""
    hoje = hoje or datetime.now().date()
    recorte = await _territorio_do_usuario(session, usuario_id, municipio)
    catalogo = await estado_catalogo(session)
    vazio = {
        "programas": [],
        "total": 0,
        "recomendados": 0,
        "encerrando": 0,
        "municipios": recorte,
        "catalogo": catalogo,
        "facetas": {"orgao": [], "categoria": [], "janela": []},
        "hoje": hoje,
    }
    if not recorte:
        return vazio

    areas = await _areas(session, usuario_id)
    orgaos = await _orgaos_conhecidos(session, [m["ibge"] for m in recorte])

    avaliados: list[tuple[Programa, Avaliacao]] = []
    for p in await _candidatos(session, hoje):
        if not incluir_outras_naturezas and not aceita_municipio(p.naturezas):
            continue
        av = avaliar(p, recorte, hoje=hoje, areas=areas, orgaos_conhecidos=orgaos)
        if av is not None:
            avaliados.append((p, av))

    # facetas sobre o universo avaliado, cada uma ignorando o próprio filtro
    # (mesma disciplina da §26b — senão o dropdown prende na opção escolhida)
    def passa(p: Programa, av: Avaliacao, *, ignorar: str | None = None) -> bool:
        if q and not _casa_busca(p, q):
            return False
        if ignorar != "orgao" and orgao and (p.orgao_superior or "") != orgao:
            return False
        if ignorar != "categoria" and categoria and categoria not in av.categorias:
            return False
        if ignorar != "janela" and janela and not any(j.tipo == janela for j in av.janelas):
            return False
        return not (apenas_recomendados and not av.recomendado)

    def contar(chave: str, valores) -> list[dict]:
        cont: dict[str, int] = {}
        for p, av in avaliados:
            if passa(p, av, ignorar=chave):
                for v in valores(p, av):
                    cont[v] = cont.get(v, 0) + 1
        return [{"valor": v, "total": n} for v, n in sorted(cont.items(), key=lambda x: -x[1])]

    facetas = {
        "orgao": [
            {**f, "rotulo": f["valor"]}
            for f in contar("orgao", lambda p, av: [p.orgao_superior] if p.orgao_superior else [])
        ],
        "categoria": [
            {**f, "rotulo": categorias_ia.ROTULOS.get(f["valor"], f["valor"])}
            for f in contar("categoria", lambda p, av: av.categorias)
        ],
        "janela": [
            {**f, "rotulo": JANELAS[f["valor"]]["rotulo"]}
            for f in contar("janela", lambda p, av: sorted({j.tipo for j in av.janelas}))
        ],
    }

    filtrados = sorted(
        ((p, av) for p, av in avaliados if passa(p, av)), key=lambda par: _ordem(par[1])
    )
    return {
        **vazio,
        "programas": [serializar(p, av) for p, av in filtrados],
        "total": len(filtrados),
        "recomendados": sum(1 for _, av in filtrados if av.recomendado),
        "encerrando": sum(
            1
            for _, av in filtrados
            if av.prazo_final is not None and (av.prazo_final - hoje).days <= DIAS_ENCERRANDO
        ),
        "facetas": facetas,
    }


def serializar(p: Programa, av: Avaliacao) -> dict:
    prazo = av.prazo_final
    abertas = [j for j in av.janelas if j.status == "aberta"]
    dias = min(abertas, key=lambda j: j.fim).dias_restantes if abertas else None
    return {
        "id": p.id,
        "codigo": p.codigo,
        "nome": p.nome,
        "orgao_superior": p.orgao_superior,
        "orgao": p.orgao,
        "situacao": p.situacao,
        "ano": p.ano,
        "modalidades": p.modalidades or [],
        "naturezas": p.naturezas or [],
        "aceita_municipio": aceita_municipio(p.naturezas),
        "ufs": sorted(ufs_validas(p.ufs)),
        "janelas": [
            {
                "tipo": j.tipo,
                "rotulo": JANELAS[j.tipo]["rotulo"],
                "como": JANELAS[j.tipo]["como"],
                "inicio": j.inicio,
                "fim": j.fim,
                "status": j.status,
                "dias_restantes": j.dias_restantes,
            }
            for j in av.janelas
        ],
        "prazo_final": prazo,
        "dias_restantes": dias,
        "municipios": av.municipios,
        "categorias": categorias_ia.rotular(av.categorias),
        "motivos": [{"chave": m.chave, "texto": m.texto} for m in av.motivos],
        "recomendado": av.recomendado,
        "url_consulta": URL_CONSULTA,
    }
