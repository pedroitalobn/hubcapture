"""Central de ajuda (help desk interno): artigos, publicação, mídias e hints."""

from __future__ import annotations

from src.db.session import SessionLocal
from src.models.helpdesk import (
    HelpdeskArtigo,
    HelpdeskCategoria,
    HelpdeskHint,
    HelpdeskMidia,
)
from src.services import helpdesk as service
from src.services import modulos as modulos_service


def test_slugify_sem_acento_e_estavel() -> None:
    assert service.slugify("O que é um EMPENHO?") == "o-que-e-um-empenho"
    assert service.slugify("Execução — financeira (2026)") == "execucao-financeira-2026"
    assert service.slugify("???") == "artigo"  # nunca slug vazio


def test_catalogo_de_chaves_cobre_o_empenho() -> None:
    # a chave que motivou a feature precisa existir e ser válida
    assert service.chave_valida("proposta.empenhado")
    assert not service.chave_valida("chave.inventada")
    # catálogo sem chave duplicada (o unique do banco é por chave)
    chaves = [c["chave"] for c in service.HINT_CHAVES]
    assert len(chaves) == len(set(chaves))


async def test_modulo_ajuda_nasce_ligado() -> None:
    async with SessionLocal() as s:
        assert (await modulos_service.ativos(s))["ajuda"] is True


async def _seed_artigo(
    s, titulo: str, *, publicado: bool, categoria: HelpdeskCategoria | None = None
) -> HelpdeskArtigo:
    artigo = HelpdeskArtigo(
        titulo=titulo,
        slug=await service.slug_unico(s, HelpdeskArtigo, service.slugify(titulo)),
        corpo=f"Conteúdo de {titulo}",
        publicado=publicado,
        categoria_id=categoria.id if categoria else None,
    )
    s.add(artigo)
    await s.flush()
    return artigo


async def test_slug_unico_sufixa_titulos_repetidos() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            a1 = await _seed_artigo(s, "O que é empenho", publicado=True)
            a2 = await _seed_artigo(s, "O que é empenho", publicado=True)
    assert a1.slug == "o-que-e-empenho"
    assert a2.slug == "o-que-e-empenho-2"


async def test_listagem_publica_esconde_rascunho_e_busca_no_corpo() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            cat = HelpdeskCategoria(nome="Orçamento", slug="orcamento")
            s.add(cat)
            await s.flush()
            await _seed_artigo(s, "O que é empenho", publicado=True, categoria=cat)
            await _seed_artigo(s, "Rascunho interno", publicado=False, categoria=cat)

    async with SessionLocal() as s:
        publicos = await service.listar_artigos(s, somente_publicados=True)
        todos = await service.listar_artigos(s, somente_publicados=False)
        por_corpo = await service.listar_artigos(s, q="conteúdo de o que é empenho")
        por_categoria = await service.listar_artigos(s, categoria_slug="orcamento")
        categorias = await service.listar_categorias_publicas(s)

    assert [a.titulo for a in publicos] == ["O que é empenho"]
    assert len(todos) == 2  # a visão do admin vê o rascunho
    assert [a.titulo for a in por_corpo] == ["O que é empenho"]
    assert [a.titulo for a in por_categoria] == ["O que é empenho"]
    # contagem da categoria só conta o PUBLICADO
    assert categorias[0]["slug"] == "orcamento" and categorias[0]["artigos"] == 1


async def test_artigo_por_slug_respeita_publicacao() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            rascunho = await _seed_artigo(s, "Ainda escrevendo", publicado=False)

    async with SessionLocal() as s:
        assert await service.artigo_por_slug(s, rascunho.slug) is None  # público não vê
        admin_ve = await service.artigo_por_slug(s, rascunho.slug, somente_publicado=False)
        assert admin_ve is not None and admin_ve.titulo == "Ainda escrevendo"


async def test_hints_publicos_so_com_hint_ativo_e_artigo_publicado() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            publicado = await _seed_artigo(s, "O que é empenho", publicado=True)
            rascunho = await _seed_artigo(s, "Rascunho", publicado=False)
            s.add_all(
                [
                    HelpdeskHint(chave="proposta.empenhado", artigo_id=publicado.id),
                    # hint desativado não vira ícone…
                    HelpdeskHint(chave="proposta.valor_total", artigo_id=publicado.id, ativo=False),
                    # …nem hint apontando para rascunho
                    HelpdeskHint(chave="proposta.prazo", artigo_id=rascunho.id),
                ]
            )

    async with SessionLocal() as s:
        hints = await service.hints_publicos(s)
    assert [h["chave"] for h in hints] == ["proposta.empenhado"]
    assert hints[0]["artigo_slug"] == "o-que-e-empenho"
    assert hints[0]["titulo"] == "O que é empenho"


async def test_midia_upload_roundtrip_e_resumo_conta_tipos() -> None:
    conteudo = b"%PDF-1.4 exemplo"
    async with SessionLocal() as s:
        async with s.begin():
            artigo = await _seed_artigo(s, "Com anexos", publicado=True)
            doc = HelpdeskMidia(
                artigo_id=artigo.id,
                tipo="documento",
                nome_arquivo="guia.pdf",
                mime="application/pdf",
                tamanho=len(conteudo),
                conteudo=conteudo,
            )
            video = HelpdeskMidia(
                artigo_id=artigo.id,
                tipo="video",
                url="https://www.youtube.com/watch?v=abc123",
                orientacao="vertical",
            )
            s.add_all([doc, video])
            await s.flush()
            doc_id = doc.id

    async with SessionLocal() as s:
        baixada = await service.midia_com_conteudo(s, doc_id)
        assert baixada is not None and baixada.conteudo == conteudo
        artigos = await service.listar_artigos(s, somente_publicados=True)
        resumo = service.resumo_de_artigo(artigos[0])
    assert resumo["videos"] == 1 and resumo["documentos"] == 1
