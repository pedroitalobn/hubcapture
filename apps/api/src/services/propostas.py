"""Serviço de propostas — leitura cache-first e upsert.

`listar`/`obter` leem SEMPRE do cache (nosso Postgres); o RLS isola por município.
Nunca chamam connector. O fetch ao vivo mora no serviço de consulta-avulsa.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai import categorias as categorias_ai
from ..models.proposta import Proposta
from ..schemas.proposta import PropostaCanonica
from ._territorio import Municipios
from ._territorio import condicao as condicao_municipio
from ._territorio import filtrar as filtrar_municipio

# Valor de um filtro de dimensão: um valor, vários (multi-seleção) ou nenhum.
Filtro = str | Sequence[str] | None

# campos que o upsert atualiza em conflito (fonte,id_externo)
_UPSERT_FIELDS = (
    "numero_proposta",
    "numero_plano_trabalho",
    "data_proposta",
    "titulo",
    "objeto",
    "orgao_superior",
    "modalidade",
    "municipio_ibge",
    "municipio_nome",
    "uf",
    "valor_total",
    "contrapartida",
    "situacao",
    "emenda",
    "prazos",
    "pendencias",
    "movimentacao",
    "data_proposta",
    "data_atualizacao_fonte",
    "url_origem",
    "proveniencia",
    "execucao",
    "dados_fonte",
    "hash_conteudo",
)


# Eixo "QUE TIPO?" da jornada: uma proposta CADASTRADA já existe no sistema do
# governo (convênio/plano em andamento); DISPONÍVEL é oportunidade aberta
# (edital/programa recebendo propostas). Derivado da situação — de-para por
# palavra-chave, sem coluna nova (calibrável aqui).
_KW_DISPONIVEL = ("dispon", "divulga", "abert", "public", "recebendo", "edital")


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))


def classificar_tipo(situacao: str | None) -> str:
    """'disponivel' (oportunidade aberta) ou 'cadastrada' (proposta existente)."""
    if not situacao:
        return "cadastrada"
    norm = _sem_acento(situacao).lower()
    return "disponivel" if any(kw in norm for kw in _KW_DISPONIVEL) else "cadastrada"


# ── Natureza jurídica do proponente ─────────────────────────────────────────
# Os botões de natureza jurídica das plataformas de captação recortam quem PODE
# propor. A fonte entrega texto livre (`execucao.natureza_juridica`); aqui vira
# um slug estável. De-para calibrável — palavra-chave sem acento, minúscula.
NATUREZAS_JURIDICAS: tuple[tuple[str, str], ...] = (
    ("estadual_df", "Adm. Pública Estadual/DF"),
    ("municipal", "Adm. Pública Municipal"),
    ("consorcio", "Consórcio Público"),
    ("empresa_publica", "Empresa pública / economia mista"),
    ("osc", "Organização da Sociedade Civil"),
    ("outros", "Outros"),
)

_KW_NATUREZA: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("consorcio", ("consorcio",)),
    ("empresa_publica", ("empresa publica", "economia mista", "empresa estatal")),
    ("osc", ("sociedade civil", "osc", "sem fins lucrativos", "privada sem fins")),
    ("estadual_df", ("estadual", "distrito federal", "estado ou do df", "/df")),
    ("municipal", ("municipal", "municipio", "prefeitura")),
)


def classificar_natureza_juridica(valor: str | None) -> str | None:
    """Slug da natureza jurídica ('municipal', 'consorcio'…) ou None se ausente."""
    if not valor:
        return None
    norm = _sem_acento(str(valor)).lower()
    for slug, palavras in _KW_NATUREZA:
        if any(p in norm for p in palavras):
            return slug
    return "outros"


def _execucao(p: Proposta) -> dict:
    return p.execucao if isinstance(p.execucao, dict) else {}


# Sinais alternativos da natureza: quando a execução não traz o campo, o
# registro-fonte completo (`dados_fonte`) costuma trazer — texto, código
# CONCLA/RFB ou o nome do proponente. Ponto de calibração por fonte.
_CAMPOS_NATUREZA_FONTE = (
    "natureza_juridica",
    "natureza_juridica_proponente",
    "nome_natureza_juridica",
    "nat_jur",
)
_CAMPOS_CODIGO_NATUREZA = ("codigo_natureza_juridica", "cod_nat_jur", "id_natureza_juridica")
_CAMPOS_PROPONENTE = (
    "nm_proponente",
    "nome_proponente",
    "proponente",
    "nome_beneficiario",
    "razao_social",
)

# Códigos de esfera municipal da tabela de Natureza Jurídica (CONCLA/RFB):
# 103-1 Executivo · 106-6 Legislativo · 112-0 Autarquia · 115-5 e 127-9 Fundação
# · 118-0 Órgão Autônomo · 124-4 Município · 130-9 e 133-3 Fundo Público.
_CODIGOS_MUNICIPAIS = frozenset(
    {"1031", "1066", "1120", "1155", "1180", "1244", "1279", "1309", "1333"}
)
# 121-0 (associação pública) e 122-8 (direito privado) — consórcio público.
_CODIGOS_CONSORCIO = frozenset({"1210", "1228"})

# Fontes cujo beneficiário é, por desenho do programa, o próprio ente municipal
# (repasse fundo a fundo ao município). Último recurso, sem nenhum outro sinal.
_NATUREZA_PADRAO_FONTE = {"transferegov_ff": "municipal", "fns": "municipal"}


def _natureza_por_codigo(valor: str | None) -> str | None:
    """Slug a partir do código CONCLA/RFB (só o que ele decide com certeza)."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    if len(digitos) != 4:
        return None
    if digitos in _CODIGOS_MUNICIPAIS:
        return "municipal"
    return "consorcio" if digitos in _CODIGOS_CONSORCIO else None


def natureza_juridica_de(p: Proposta) -> str | None:
    """Natureza jurídica do proponente, do sinal mais forte ao mais fraco.

    Execução > texto no registro-fonte > código CONCLA/RFB > nome do proponente
    > padrão da fonte. Sem nenhum sinal continua None (a proposta fica fora dos
    filtros detalhados) — as duas LENTES (`grupo_natureza_de`) é que sempre
    classificam, para que a consulta cubra a base inteira.
    """
    slug = classificar_natureza_juridica(_execucao(p).get("natureza_juridica"))
    if slug:
        return slug
    for campo in _CAMPOS_NATUREZA_FONTE:
        slug = classificar_natureza_juridica(_campo_fonte(p.dados_fonte, campo))
        if slug:
            return slug
    for campo in _CAMPOS_CODIGO_NATUREZA:
        slug = _natureza_por_codigo(_campo_fonte(p.dados_fonte, campo))
        if slug:
            return slug
    for campo in _CAMPOS_PROPONENTE:
        # o NOME só vale quando reconhece um marcador ("Prefeitura de…"); texto
        # não reconhecido não vira "outros" aqui, senão o nome de qualquer
        # proponente encerraria a busca por sinal.
        slug = classificar_natureza_juridica(_campo_fonte(p.dados_fonte, campo))
        if slug and slug != "outros":
            return slug
    return _NATUREZA_PADRAO_FONTE.get(p.fonte)


# ── Lentes de natureza jurídica (o recorte de consulta do painel) ───────────
# A consulta parte de DUAS lentes, não da taxonomia inteira (decisão de
# produto): quem propõe é o MUNICÍPIO (prefeitura, secretaria, câmara,
# fundo/autarquia municipal) ou é OUTRO (OSC, entes estaduais/federais,
# empresas). Os slugs detalhados acima seguem valendo no filtro avançado.
GRUPOS_NATUREZA: tuple[tuple[str, str], ...] = (
    ("entes_municipais", "Entes municipais"),
    ("outros", "Outros"),
)
# Consórcio público entra como ente municipal: na prática é intermunicipal —
# formado pelos próprios municípios (calibrável).
_NATUREZAS_MUNICIPAIS = frozenset({"municipal", "consorcio"})


def grupo_natureza_de(p: Proposta) -> str:
    """A lente da proposta — SEMPRE uma das duas (sem sinal ⇒ 'outros').

    Por isso as duas lentes somadas cobrem sempre o recorte inteiro: nenhuma
    proposta fica invisível às duas.
    """
    return "entes_municipais" if natureza_juridica_de(p) in _NATUREZAS_MUNICIPAIS else "outros"


def qualificacao_de(p: Proposta) -> str | None:
    """'Qualificação' do instrumento — o tipo de transferência informado pela fonte."""
    v = _execucao(p).get("tipo_transferencia")
    return str(v) if v not in (None, "") else None


# ano embutido no nº da proposta ("043210/2025" → 2025)
_ANO_NO_NUMERO = re.compile(r"/((?:19|20)\d{2})\s*$")


def _ano_plausivel(ano: int) -> bool:
    return 1990 <= ano <= date.today().year + 1


def _campo_fonte(dados: object, chave: str, profundidade: int = 3) -> str | None:
    """Busca um campo no registro-fonte completo (`dados_fonte`), em qualquer
    nível e caixa — o ANO_PROP do CSV do SIconv vive em `plano_acao.csv`.

    Ler direto da fonte corrige o dado JÁ ingerido no cache (que pode ter a
    `data_proposta` montada por retaguarda errada) sem esperar re-sync.
    """
    if not isinstance(dados, dict) or profundidade < 0:
        return None
    for k, v in dados.items():
        if isinstance(k, str) and k.strip().lower() == chave and v not in (None, ""):
            return str(v).strip()
    for v in dados.values():
        achado = _campo_fonte(v, chave, profundidade - 1)
        if achado:
            return achado
    return None


def ano_de(p: Proposta) -> str | None:
    """Ano de referência: o de CRIAÇÃO na fonte, nunca o da última movimentação.

    `ANO_PROP` do registro-fonte (a variável oficial do SIconv) > `data_proposta`
    > sufixo do nº da proposta > exercício da execução. Sem nenhum desses sinais
    o ano fica INDEFINIDO (None): cair na data de atualização classificaria uma
    proposta criada em 2022 e movimentada em 2026 como safra 2026 — exatamente o
    que este critério existe para evitar. Sem ano, a proposta continua na lista,
    só não entra em nenhuma safra.
    """
    ano_fonte = _campo_fonte(p.dados_fonte, "ano_prop")
    if ano_fonte and ano_fonte[:4].isdigit() and _ano_plausivel(int(ano_fonte[:4])):
        return ano_fonte[:4]
    if p.data_proposta and _ano_plausivel(p.data_proposta.year):
        return str(p.data_proposta.year)
    m = _ANO_NO_NUMERO.search(str(p.numero_proposta or ""))
    if m and _ano_plausivel(int(m.group(1))):
        return m.group(1)
    exercicio = str(_execucao(p).get("ano") or "")[:4]
    if exercicio.isdigit() and _ano_plausivel(int(exercicio)):
        return exercicio
    # Especiais: o módulo publica `ano_plano_acao` — é o ano do plano de ação,
    # a criação daquela captação. Fundo a fundo não publica ano nenhum; o
    # início de vigência do plano é o sinal que existe. Sem estes dois, TODA
    # proposta FF/ESP ficava "sem safra" e sumia das contagens filtradas por
    # ano do painel — com o dado à vista no registro-fonte.
    ano_pa = _campo_fonte(p.dados_fonte, "ano_plano_acao")
    if ano_pa and str(ano_pa)[:4].isdigit() and _ano_plausivel(int(str(ano_pa)[:4])):
        return str(ano_pa)[:4]
    vigencia = str(_campo_fonte(p.dados_fonte, "data_inicio_vigencia_plano_acao") or "")
    if vigencia[:4].isdigit() and _ano_plausivel(int(vigencia[:4])):
        return vigencia[:4]
    return None


# Valor global da proposta na fonte, por ordem de precisão: VL_GLOBAL_PROP é a
# variável oficial do SIconv para a PROPOSTA; VL_GLOBAL_CONV é a do convênio já
# celebrado; VL_GLOBAL cobre os arquivos que publicam a coluna sem sufixo.
_CAMPOS_VALOR_GLOBAL = ("vl_global_prop", "vl_global_conv", "vl_global")


def valor_global_de(p: Proposta) -> Decimal | None:
    """Valor global da proposta — o número que o card "Empenho" do detalhe exibe.

    `VL_GLOBAL_PROP` no registro-fonte vence: é o valor que a fonte publica para
    a proposta, e lê-lo direto de `dados_fonte` corrige o que já está no cache
    sem esperar re-sync (mesma disciplina de `ano_de`/`mes_de`). Sem ele, cai no
    agregado de execução e, por fim, no total já normalizado.
    """
    from ..ingestion.normalizer import _to_decimal

    for chave in _CAMPOS_VALOR_GLOBAL:
        valor = _to_decimal(_campo_fonte(p.dados_fonte, chave))
        if valor is not None:
            return valor
    return _to_decimal(_execucao(p).get("valor_global")) or _to_decimal(p.valor_total)


def prazo_final_de(p: Proposta) -> date | None:
    """Prazo mais próximo declarado na proposta (jsonb `prazos`)."""
    datas = []
    for prazo in p.prazos or []:
        try:
            datas.append(date.fromisoformat(str((prazo or {}).get("data_limite"))[:10]))
        except (TypeError, ValueError):
            continue
    return min(datas) if datas else None


# ── Mês de referência ───────────────────────────────────────────────────────
# Companheiro do filtro de ano e no MESMO referencial dele: o mês de CRIAÇÃO da
# proposta (MES_PROP do SIconv > data_proposta). Sem sinal de criação, cai no
# mês do prazo final e, por fim, no da atualização na fonte — proposta antiga
# sem data própria continua filtrável.
MESES: tuple[tuple[str, str], ...] = (
    ("01", "Janeiro"),
    ("02", "Fevereiro"),
    ("03", "Março"),
    ("04", "Abril"),
    ("05", "Maio"),
    ("06", "Junho"),
    ("07", "Julho"),
    ("08", "Agosto"),
    ("09", "Setembro"),
    ("10", "Outubro"),
    ("11", "Novembro"),
    ("12", "Dezembro"),
)


def mes_de(p: Proposta) -> str | None:
    """Mês de referência ('01'…'12'): MES_PROP > data_proposta > prazo > atualização."""
    mes_fonte = _campo_fonte(p.dados_fonte, "mes_prop")
    if mes_fonte and mes_fonte.isdigit() and 1 <= int(mes_fonte) <= 12:
        return f"{int(mes_fonte):02d}"
    if p.data_proposta:
        return f"{p.data_proposta.month:02d}"
    referencia = prazo_final_de(p) or p.data_atualizacao_fonte
    return f"{referencia.month:02d}" if referencia else None


def categorias_de(p: Proposta) -> list[str]:
    """Pílulas da proposta (slugs). Usa as curadas; classifica na hora se faltarem.

    O fallback importa: propostas que entraram antes da curadoria — ou logo agora,
    numa busca ao vivo — continuam filtráveis por categoria sem esperar o job.
    """
    if isinstance(p.categorias_ia, list) and p.categorias_ia:
        return [str(c) for c in p.categorias_ia]
    return categorias_ai.classificar(p.titulo, p.objeto, p.orgao_superior, p.modalidade)


# ── Ordenação (benchmark: mais recentes · prazo · nome A-Z · órgão A-Z) ──────
ORDENACOES = ("recentes", "prazo", "prazo_distante", "nome", "orgao", "valor")

_LONGE = date(9999, 12, 31)


def _ordenar(rows: list[Proposta], ordenar: str | None) -> list[Proposta]:
    if ordenar == "nome":
        return sorted(rows, key=lambda p: (p.titulo or p.objeto or p.id_externo).lower())
    if ordenar == "orgao":
        return sorted(rows, key=lambda p: (p.orgao_superior or "￿").lower())
    if ordenar in ("prazo", "prazo_distante"):
        # sem prazo vai sempre para o fim, nas duas direções
        com = [p for p in rows if prazo_final_de(p) is not None]
        sem = [p for p in rows if prazo_final_de(p) is None]
        com.sort(key=lambda p: prazo_final_de(p) or _LONGE, reverse=ordenar == "prazo_distante")
        return com + sem
    if ordenar == "valor":
        return sorted(rows, key=lambda p: p.valor_total or Decimal(0), reverse=True)
    return rows  # 'recentes' já vem ordenado pelo SQL


def _busca_textual(termo: str):
    """Programa, órgão ou código — o campo de busca livre da tela de captação."""
    like = f"%{termo.strip()}%"
    return or_(
        Proposta.titulo.ilike(like),
        Proposta.objeto.ilike(like),
        Proposta.orgao_superior.ilike(like),
        Proposta.modalidade.ilike(like),
        Proposta.id_externo.ilike(like),
        Proposta.numero_proposta.ilike(like),
    )


# ── Paginação ───────────────────────────────────────────────────────────────
# Os filtros derivados de jsonb/situação e quase todas as ordenações rodam em
# Python DEPOIS do SELECT. Descer LIMIT/OFFSET ao banco quando ainda há etapa
# posterior pagina o conjunto ERRADO (a página sai do recorte pré-filtro, e o
# total seria o do SQL, não o da tela). Só usamos o caminho rápido quando nada
# acontece depois do SELECT — sem `tipo`/`natureza_juridica`/`qualificacao`/
# `ano`/`mes`/`categoria`; nos demais casos, filtra tudo e fatia em Python.
_ORDENACOES_SQL = (None, "recentes")  # `_ordenar` devolve a ordem do SQL nessas

# "Recentes" é a data da PROPOSTA, não a da nossa coleta: `data_proposta` vem
# de DIA_PROP+MES_PROP+ANO_PROP (as variáveis oficiais do SIconv, remontadas no
# normalizador). Ordenar por `cache_atualizado_em` embaralhava safras — uma
# proposta de 2019 recoletada hoje aparecia na frente de uma criada este mês.
#
# `cache_atualizado_em` entra só como desempate (proposta sem data de criação na
# fonte vai para o fim, nullslast) e `id` fecha: sem desempate estável o
# LIMIT/OFFSET repete e pula linhas entre páginas.
_ORDEM_SQL = (
    Proposta.data_proposta.desc().nullslast(),
    Proposta.cache_atualizado_em.desc().nullslast(),
    Proposta.id,
)


def _condicoes(
    *,
    municipio: Municipios,
    uf: str | None,
    fonte: str | None,
    situacao: str | None,
    area: str | None,
    valor_min: Decimal | None,
    valor_max: Decimal | None,
    q: str | None,
    modalidade: str | None,
    orgao: str | None,
) -> list:
    """Recorte que o SQL sabe fazer (o resto é pós-filtro em Python)."""
    # proposta zerada (soft delete) não aparece em lugar nenhum do painel. O
    # filtro mora na consulta, e não na policy de RLS, porque o upsert da coleta
    # precisa ENXERGAR a linha marcada para ressuscitá-la (ver a migration
    # f6a7b8c9d0e1).
    condicoes = [Proposta.excluido_em.is_(None)]
    # território: um município, vários (o painel recorta um subconjunto do
    # perfil) ou nenhum — aí o RLS já limita ao território do usuário.
    recorte = condicao_municipio(Proposta.municipio_ibge, municipio)
    if recorte is not None:
        condicoes.append(recorte)
    if uf:
        condicoes.append(Proposta.uf == uf.upper())
    if fonte:
        condicoes.append(Proposta.fonte == fonte)
    if situacao:
        condicoes.append(Proposta.situacao == situacao)
    if modalidade:
        condicoes.append(Proposta.modalidade == modalidade)
    if orgao:
        condicoes.append(Proposta.orgao_superior == orgao)
    if q and q.strip():
        condicoes.append(_busca_textual(q))
    if area:
        from .perfil import AREA_FONTES

        fontes_area = AREA_FONTES.get(area)
        if fontes_area:
            condicoes.append(Proposta.fonte.in_(fontes_area))
    if valor_min is not None:
        condicoes.append(Proposta.valor_total >= valor_min)
    if valor_max is not None:
        condicoes.append(Proposta.valor_total <= valor_max)
    return condicoes


async def listar_pagina(
    session: AsyncSession,
    *,
    municipio: Municipios = None,
    uf: str | None = None,
    fonte: str | None = None,
    situacao: str | None = None,
    area: str | None = None,
    valor_min: Decimal | None = None,
    valor_max: Decimal | None = None,
    tipo: str | None = None,
    q: str | None = None,
    modalidade: str | None = None,
    orgao: str | None = None,
    natureza_juridica: str | None = None,
    natureza_grupo: str | None = None,
    qualificacao: str | None = None,
    ano: Filtro = None,
    mes: str | None = None,
    categoria: str | None = None,
    ordenar: str | None = None,
    limite: int | None = None,
    offset: int = 0,
) -> tuple[list[Proposta], int]:
    """Uma página do recorte e o total dele (o total ignora limite/offset).

    Sem `limite`/`offset` devolve o recorte inteiro — é assim que facetas,
    resumo e relatório continuam enxergando tudo.
    """
    condicoes = _condicoes(
        municipio=municipio,
        uf=uf,
        fonte=fonte,
        situacao=situacao,
        area=area,
        valor_min=valor_min,
        valor_max=valor_max,
        q=q,
        modalidade=modalidade,
        orgao=orgao,
    )
    stmt = select(Proposta).where(*condicoes).order_by(*_ORDEM_SQL)

    pos_filtros = (
        tipo in ("cadastrada", "disponivel"),
        natureza_juridica,
        natureza_grupo,
        qualificacao,
        ano,
        mes,
        categoria,
    )
    paginando = limite is not None or offset
    if paginando and not any(pos_filtros) and ordenar in _ORDENACOES_SQL:
        # caminho rápido: o banco pagina e conta
        total = int(
            (
                await session.execute(select(func.count()).select_from(Proposta).where(*condicoes))
            ).scalar_one()
        )
        if offset:
            stmt = stmt.offset(offset)
        if limite is not None:
            stmt = stmt.limit(limite)
        return list((await session.execute(stmt)).scalars().all()), total

    rows = list((await session.execute(stmt)).scalars().all())
    # filtros derivados de jsonb/situação ficam em Python (o recorte já é do
    # território pelo RLS, então o conjunto é pequeno)
    if tipo in ("cadastrada", "disponivel"):
        rows = [p for p in rows if classificar_tipo(p.situacao) == tipo]
    if natureza_juridica:
        rows = [p for p in rows if natureza_juridica_de(p) == natureza_juridica]
    if natureza_grupo:
        rows = [p for p in rows if grupo_natureza_de(p) == natureza_grupo]
    if qualificacao:
        rows = [p for p in rows if qualificacao_de(p) == qualificacao]
    if ano:
        # multi-seleção: a proposta entra se a safra dela é QUALQUER das escolhidas
        safras = set(_escolhidos(ano))
        rows = [p for p in rows if ano_de(p) in safras]
    if mes:
        rows = [p for p in rows if mes_de(p) == str(mes).zfill(2)]
    if categoria:
        rows = [p for p in rows if categoria in categorias_de(p)]
    rows = _ordenar(rows, ordenar)
    total = len(rows)
    if paginando:
        fim = offset + limite if limite is not None else None
        rows = rows[offset:fim]
    return rows, total


async def atualizado_em(session: AsyncSession, **filtros) -> datetime | None:
    """Coleta mais recente que tocou este recorte (max `cache_atualizado_em`).

    É o carimbo de idade que o painel mostra. A lista é servida do banco — quem
    alimenta é o sweep diário —, então sem dizer DE QUANDO é o dado o gestor não
    tem como distinguir "a fonte não tem mais nada" de "ninguém coletou ainda".
    """
    condicoes = _condicoes(
        municipio=filtros.get("municipio"),
        uf=filtros.get("uf"),
        fonte=filtros.get("fonte"),
        situacao=filtros.get("situacao"),
        area=filtros.get("area"),
        valor_min=filtros.get("valor_min"),
        valor_max=filtros.get("valor_max"),
        q=filtros.get("q"),
        modalidade=filtros.get("modalidade"),
        orgao=filtros.get("orgao"),
    )
    stmt = select(func.max(Proposta.cache_atualizado_em)).where(*condicoes)
    return (await session.execute(stmt)).scalar_one_or_none()


async def listar(session: AsyncSession, **filtros) -> list[Proposta]:
    """O recorte inteiro (sem total). Ver `listar_pagina` para os filtros."""
    rows, _ = await listar_pagina(session, **filtros)
    return rows


def _prazos_na_janela(p: Proposta, inicio: date, fim: date) -> list[dict]:
    """Prazos da proposta (jsonb [{tipo, data_limite}]) dentro da janela."""
    dentro = []
    for prazo in p.prazos or []:
        bruto = (prazo or {}).get("data_limite")
        try:
            data_limite = date.fromisoformat(str(bruto)[:10])
        except (TypeError, ValueError):
            continue
        if inicio <= data_limite <= fim:
            dentro.append({**prazo, "data_limite": data_limite.isoformat()})
    return dentro


async def listar_por_prazo(
    session: AsyncSession, *, dias: int = 30, municipio: Municipios = None
) -> list[tuple[Proposta, list[dict]]]:
    """Propostas com prazo vencendo na janela [hoje, hoje+dias] — consulta
    estruturada (não-RAG) que alimenta o painel e a resposta do chat."""
    hoje = date.today()
    fim = hoje + timedelta(days=dias)
    stmt = select(Proposta).where(Proposta.prazos.isnot(None), Proposta.excluido_em.is_(None))
    stmt = filtrar_municipio(stmt, Proposta.municipio_ibge, municipio)
    rows = (await session.execute(stmt)).scalars().all()
    com_prazo = []
    for p in rows:
        na_janela = _prazos_na_janela(p, hoje, fim)
        if na_janela:
            com_prazo.append((p, na_janela))
    com_prazo.sort(key=lambda item: min(pr["data_limite"] for pr in item[1]))
    return com_prazo


# ── Facetas (as opções dos dropdowns, com contagem) ─────────────────────────
# Cada dropdown mostra só o que EXISTE no recorte atual, e a contagem por opção
# é calculada ignorando o filtro da própria dimensão (senão o dropdown ficaria
# preso na opção escolhida).

_DIMENSOES: dict[str, object] = {
    "municipio": lambda p: p.municipio_ibge,
    "uf": lambda p: p.uf,
    "fonte": lambda p: p.fonte,
    "modalidade": lambda p: p.modalidade,
    "orgao": lambda p: p.orgao_superior,
    "situacao": lambda p: p.situacao,
    "natureza_juridica": natureza_juridica_de,
    "natureza_grupo": grupo_natureza_de,
    "qualificacao": qualificacao_de,
    "categoria": categorias_de,  # multivalorada: uma proposta tem até 3 pílulas
    "ano": ano_de,
    "mes": mes_de,
    "tipo": lambda p: classificar_tipo(p.situacao),
}

_ROTULOS: dict[str, dict[str, str]] = {
    "natureza_juridica": dict(NATUREZAS_JURIDICAS),
    "natureza_grupo": dict(GRUPOS_NATUREZA),
    "tipo": {"cadastrada": "Cadastradas", "disponivel": "Disponíveis"},
    "categoria": categorias_ai.ROTULOS,
    "mes": dict(MESES),
}

# Dimensões cronológicas ordenam pelo VALOR, não pela contagem: um dropdown de
# meses fora de ordem é ilegível. Ano do mais recente para o mais antigo.
_ORDEM_CRONOLOGICA: dict[str, bool] = {"ano": True, "mes": False}  # dim -> decrescente


def _valores(dim: str, p: Proposta) -> list[str]:
    """Valores de uma proposta na dimensão (lista: cobre as multivaloradas)."""
    bruto = _DIMENSOES[dim](p)  # type: ignore[operator]
    itens = bruto if isinstance(bruto, list) else [bruto]
    return [str(v) for v in itens if v not in (None, "")]


def _escolhidos(valor: Filtro) -> list[str]:
    """Filtro de uma dimensão: um valor, vários (multi-seleção) ou nenhum.

    Município e ano chegam como lista quando o painel soma recortes; as demais
    dimensões chegam como string — os dois casos viram a mesma lista aqui.
    Escalar fora do contrato (`ano=2024` como int) vale como valor único, como
    o `str(ano)` de antes do multi tolerava.
    """
    if valor is None:
        return []
    escalar = isinstance(valor, str) or not isinstance(valor, Sequence)
    brutos = [valor] if escalar else list(valor)
    return [str(v) for v in brutos if str(v)]


def _casa(p: Proposta, filtros: dict[str, Filtro], ignorar: str | None = None) -> bool:
    for dim, valor in filtros.items():
        escolhidos = _escolhidos(valor)
        if not escolhidos or dim == ignorar:
            continue
        # multi-seleção casa por interseção: a proposta entra se bate com QUALQUER
        # valor escolhido (é um OU dentro da dimensão, E entre dimensões).
        if not set(escolhidos) & set(_valores(dim, p)):
            return False
    return True


async def facetas(
    session: AsyncSession,
    *,
    area: str | None = None,
    q: str | None = None,
    valor_min: Decimal | None = None,
    valor_max: Decimal | None = None,
    **filtros: Filtro,
) -> dict[str, list[dict]]:
    """Opções disponíveis por dimensão (valor, rótulo, total) para os dropdowns.

    Nenhum filtro de dimensão entra no SQL aqui: o recorte base é só território
    (RLS) + área/busca/faixa de valor, e cada dimensão é contada IGNORANDO o
    próprio filtro — senão o dropdown de município (ou de mês, ou de órgão)
    passaria a listar apenas a opção já escolhida.
    """
    dimensoes = {dim: filtros.get(dim) for dim in _DIMENSOES}
    rows = await listar(session, area=area, q=q, valor_min=valor_min, valor_max=valor_max)
    # município não tem rótulo fixo — sai do próprio recorte (nome/UF)
    nomes_municipio = {
        p.municipio_ibge: f"{p.municipio_nome or p.municipio_ibge}{f'/{p.uf}' if p.uf else ''}"
        for p in rows
        if p.municipio_ibge
    }
    resultado: dict[str, list[dict]] = {}
    for dim in _DIMENSOES:
        contagem: dict[str, int] = {}
        for p in rows:
            if not _casa(p, dimensoes, ignorar=dim):
                continue
            for valor in _valores(dim, p):
                contagem[valor] = contagem.get(valor, 0) + 1
        rotulos = nomes_municipio if dim == "municipio" else _ROTULOS.get(dim, {})
        if dim in _ORDEM_CRONOLOGICA:
            itens = sorted(contagem.items(), reverse=_ORDEM_CRONOLOGICA[dim])
        else:
            itens = sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))
        resultado[dim] = [{"valor": v, "rotulo": rotulos.get(v, v), "total": n} for v, n in itens]
    return resultado


# ── Resumo (dashboard consolidado da captação) ──────────────────────────────


def _dec(v) -> Decimal:
    if v in (None, ""):
        return Decimal(0)
    try:
        return Decimal(str(v))
    except (ArithmeticError, ValueError):
        return Decimal(0)


def _valor_global(p: Proposta) -> Decimal:
    ex = _execucao(p)
    return _dec(ex.get("valor_global")) or _dec(p.valor_total)


def _desembolsado(p: Proposta) -> Decimal:
    """O que efetivamente saiu para o ente: liberado; sem ele, o pago."""
    ex = _execucao(p)
    return _dec(ex.get("valor_liberado")) or _dec(ex.get("valor_pago"))


# "Publicado" na fonte vem ora como VALOR, ora como SITUAÇÃO (§ pontos 08/13
# do feedback). Estas duas funções leem os dois sentidos sem escolher por conta
# própria: o valor manda quando existe; senão vale o estado da publicação.
_NAO_PUBLICADO = ("nao", "não", "n", "false", "0", "sem publicacao", "nao publicado")


def _valor_publicado(p: Proposta) -> Decimal:
    return _dec(_execucao(p).get("valor_publicado"))


def esta_publicada(p: Proposta) -> bool:
    """A proposta/convênio foi publicado? (valor > 0 ou situação afirmativa)."""
    if _valor_publicado(p) > 0:
        return True
    bruto = str(_execucao(p).get("situacao_publicacao") or "").strip().lower()
    if not bruto:
        return False
    return not any(bruto.startswith(n) for n in _NAO_PUBLICADO)


def _fim_vigencia(p: Proposta) -> date | None:
    bruto = _execucao(p).get("data_fim_vigencia")
    try:
        return date.fromisoformat(str(bruto)[:10])
    except (TypeError, ValueError):
        return prazo_final_de(p)


async def resumo(session: AsyncSession, **filtros) -> dict:
    """Cards financeiros, série aprovado × desembolsado por ano, pipeline por
    situação e a lista de convênios vigentes com % de desembolso.

    Com UMA safra no filtro, a resposta traz também `por_mes` — a mesma série
    aberta mês a mês daquele ano (mês de criação da proposta, `mes_de`, o mesmo
    referencial do filtro de mês). Com zero ou várias safras a lista vem vazia:
    misturar janeiros de anos diferentes numa barra só não é uma série.
    """
    rows = await listar(session, **filtros)
    hoje = date.today()
    # `rows` já vem recortado pela(s) safra(s) — aqui só decidimos a abertura
    safra_unica = len(set(_escolhidos(filtros.get("ano")))) == 1

    empenhado = sum((_dec(_execucao(p).get("valor_empenhado")) for p in rows), Decimal(0))
    pago = sum((_dec(_execucao(p).get("valor_pago")) for p in rows), Decimal(0))
    publicado = sum((_valor_publicado(p) for p in rows), Decimal(0))
    publicadas = sum(1 for p in rows if esta_publicada(p))
    conveniado = sum((_valor_global(p) for p in rows), Decimal(0))
    desembolsado = sum((_desembolsado(p) for p in rows), Decimal(0))

    por_ano: dict[str, list[Decimal]] = {}
    por_mes: dict[str, list[Decimal]] = {}
    pipeline: dict[str, list] = {}
    vigentes: list[dict] = []
    iniciados = 0

    for p in rows:
        ano = ano_de(p)
        if ano:
            acc = por_ano.setdefault(ano, [Decimal(0), Decimal(0)])
            acc[0] += _valor_global(p)
            acc[1] += _desembolsado(p)
        if safra_unica:
            mes = mes_de(p)
            if mes:
                acc_m = por_mes.setdefault(mes, [Decimal(0), Decimal(0)])
                acc_m[0] += _valor_global(p)
                acc_m[1] += _desembolsado(p)

        chave = p.situacao or "Sem situação"
        item = pipeline.setdefault(chave, [0, Decimal(0)])
        item[0] += 1
        item[1] += _valor_global(p)

        ex = _execucao(p)
        if ex.get("data_inicio_vigencia") or ex.get("data_assinatura"):
            iniciados += 1
        fim = _fim_vigencia(p)
        if fim and fim >= hoje and classificar_tipo(p.situacao) == "cadastrada":
            glob = _valor_global(p)
            desem = _desembolsado(p)
            vigentes.append(
                {
                    "id": p.id,
                    "titulo": p.titulo or p.objeto or p.id_externo,
                    "orgao_superior": p.orgao_superior,
                    "modalidade": p.modalidade,
                    "valor_global": glob,
                    "desembolsado": desem,
                    "percentual_desembolso": float(desem / glob * 100) if glob else 0.0,
                    "fim_vigencia": fim,
                    "dias_restantes": (fim - hoje).days,
                }
            )

    vigentes.sort(key=lambda c: c["dias_restantes"])
    return {
        "cards": {
            "valor_conveniado": conveniado,
            "valor_desembolsado": desembolsado,
            "valor_empenhado": empenhado,
            # Pago sai do somatório que já existia para o "a utilizar" — o
            # Panorama financeiro do painel mostra o par empenhado × pago.
            "valor_pago": pago,
            # Publicado: o valor quando a fonte publica valor; a CONTAGEM de
            # publicadas quando ela só publica o estado. O painel mostra um ou
            # outro — zero em R$ leria como "nada publicado", que é diferente
            # de "esta fonte não informa valor de publicação".
            "valor_publicado": publicado,
            "propostas_publicadas": publicadas,
            "valor_a_utilizar": max(Decimal(0), empenhado - pago),
            "transferencias": len(rows),
            "convenios_iniciados": iniciados,
            "convenios_em_execucao": len(vigentes),
            "oportunidades_abertas": sum(
                1 for p in rows if classificar_tipo(p.situacao) == "disponivel"
            ),
        },
        "por_ano": [
            {"ano": ano, "aprovado": v[0], "desembolsado": v[1]}
            for ano, v in sorted(por_ano.items())
        ],
        "por_mes": [
            {
                "mes": mes,
                "rotulo": dict(MESES).get(mes, mes),
                "aprovado": v[0],
                "desembolsado": v[1],
            }
            for mes, v in sorted(por_mes.items())
        ],
        "pipeline": [
            {"situacao": s, "quantidade": v[0], "valor": v[1]}
            for s, v in sorted(pipeline.items(), key=lambda kv: -kv[1][0])
        ],
        "convenios_vigentes": vigentes,
    }


# ── Relatório (CSV) — o "Baixar relatório" da tela de captação ──────────────

_COLUNAS_RELATORIO = (
    "fonte",
    "codigo",
    "numero_proposta",
    "data_proposta",
    "titulo",
    "objeto",
    "orgao_superior",
    "modalidade",
    "natureza_juridica",
    "qualificacao",
    "categorias",
    "municipio",
    "uf",
    "situacao",
    "tipo",
    "ano",
    "mes",
    "valor_total",
    "valor_global",
    "valor_empenhado",
    "valor_liberado",
    "valor_pago",
    "saldo_conta",
    "prazo_final",
    "url_origem",
)


def gerar_csv(rows: list[Proposta]) -> str:
    """CSV (delimitador ';', BR-friendly) com o recorte filtrado na tela."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_COLUNAS_RELATORIO, delimiter=";")
    writer.writeheader()
    for p in rows:
        ex = _execucao(p)
        prazo = prazo_final_de(p)
        writer.writerow(
            {
                "fonte": p.fonte,
                "codigo": p.id_externo,
                "numero_proposta": p.numero_proposta or "",
                "data_proposta": p.data_proposta.isoformat() if p.data_proposta else "",
                "titulo": p.titulo or "",
                "objeto": p.objeto or "",
                "orgao_superior": p.orgao_superior or "",
                "modalidade": p.modalidade or "",
                "natureza_juridica": natureza_juridica_de(p) or "",
                "qualificacao": qualificacao_de(p) or "",
                "categorias": ", ".join(categorias_ai.ROTULOS.get(c, c) for c in categorias_de(p)),
                "municipio": p.municipio_nome or p.municipio_ibge or "",
                "uf": p.uf or "",
                "situacao": p.situacao or "",
                "tipo": classificar_tipo(p.situacao),
                "ano": ano_de(p) or "",
                "mes": dict(MESES).get(mes_de(p) or "", ""),
                "valor_total": p.valor_total or "",
                "valor_global": ex.get("valor_global", ""),
                "valor_empenhado": ex.get("valor_empenhado", ""),
                "valor_liberado": ex.get("valor_liberado", ""),
                "valor_pago": ex.get("valor_pago", ""),
                "saldo_conta": ex.get("saldo_conta", ""),
                "prazo_final": prazo.isoformat() if prazo else "",
                "url_origem": p.url_origem or "",
            }
        )
    return buffer.getvalue()


async def obter(session: AsyncSession, proposta_id: uuid.UUID) -> Proposta | None:
    result = await session.execute(
        select(Proposta).where(Proposta.id == proposta_id, Proposta.excluido_em.is_(None))
    )
    return result.scalar_one_or_none()


async def upsert(session: AsyncSession, canonica: PropostaCanonica) -> None:
    """Insere/atualiza uma proposta pelo par único (fonte, id_externo)."""
    now = datetime.now(UTC)
    values = canonica.model_dump()
    values["cache_atualizado_em"] = now

    stmt = pg_insert(Proposta).values(**values)
    update_set = {k: getattr(stmt.excluded, k) for k in _UPSERT_FIELDS}
    update_set["cache_atualizado_em"] = now
    update_set["updated_at"] = now
    # RESSUSCITA o que foi zerado: a fonte ainda publica esta proposta, então
    # ela volta ao painel em vez de ficar escondida para sempre pela policy.
    update_set["excluido_em"] = None
    stmt = stmt.on_conflict_do_update(
        constraint="uq_propostas_fonte_id_externo",
        set_=update_set,
    )
    await session.execute(stmt)
