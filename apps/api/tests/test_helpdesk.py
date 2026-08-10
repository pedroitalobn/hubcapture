"""Class (help desk interno): artigos, módulos/aulas, publicação, mídias e hints."""

from __future__ import annotations

from src.db.session import SessionLocal
from src.models.helpdesk import (
    HelpdeskArtigo,
    HelpdeskCategoria,
    HelpdeskHint,
    HelpdeskMidia,
    HelpdeskModulo,
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
    s,
    titulo: str,
    *,
    publicado: bool,
    categoria: HelpdeskCategoria | None = None,
    modulo: HelpdeskModulo | None = None,
    ordem: int = 0,
) -> HelpdeskArtigo:
    artigo = HelpdeskArtigo(
        titulo=titulo,
        slug=await service.slug_unico(s, HelpdeskArtigo, service.slugify(titulo)),
        corpo=f"Conteúdo de {titulo}",
        publicado=publicado,
        categoria_id=categoria.id if categoria else None,
        modulo_id=modulo.id if modulo else None,
        ordem=ordem,
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


async def _seed_modulo(s, titulo: str, *, publicado: bool) -> HelpdeskModulo:
    modulo = HelpdeskModulo(
        titulo=titulo,
        slug=await service.slug_unico(s, HelpdeskModulo, service.slugify(titulo)),
        publicado=publicado,
    )
    s.add(modulo)
    await s.flush()
    return modulo


async def test_modulo_lista_aulas_em_ordem_e_so_publicadas() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            mod = await _seed_modulo(s, "Captação 101", publicado=True)
            # semeadas fora de ordem de propósito — a sequência vem de `ordem`
            await _seed_artigo(s, "Aula 2 — Empenho", publicado=True, modulo=mod, ordem=2)
            await _seed_artigo(s, "Aula 1 — Proposta", publicado=True, modulo=mod, ordem=1)
            await _seed_artigo(s, "Aula 3 — rascunho", publicado=False, modulo=mod, ordem=3)

    async with SessionLocal() as s:
        publico = await service.modulo_por_slug(s, "captacao-101")
        admin = await service.modulo_por_slug(s, "captacao-101", somente_publicado=False)
        lista = await service.listar_modulos(s, somente_publicados=True)

    assert publico is not None
    assert [a["titulo"] for a in publico["aulas"]] == [
        "Aula 1 — Proposta",
        "Aula 2 — Empenho",
    ]
    # o editor vê o rascunho na sequência; o aluno não
    assert len(admin["aulas"]) == 3
    # a contagem pública do módulo também só conta aula publicada
    assert lista[0]["aulas"] == 2


async def test_modulo_rascunho_nao_aparece_ao_publico() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            await _seed_modulo(s, "Ainda montando", publicado=False)

    async with SessionLocal() as s:
        assert await service.listar_modulos(s, somente_publicados=True) == []
        assert await service.modulo_por_slug(s, "ainda-montando") is None
        # a visão do admin enxerga
        todos = await service.listar_modulos(s, somente_publicados=False)
        assert [m["titulo"] for m in todos] == ["Ainda montando"]


async def test_aula_fica_fora_da_prateleira_mas_entra_na_busca() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            mod = await _seed_modulo(s, "Captação 101", publicado=True)
            await _seed_artigo(s, "Artigo avulso", publicado=True)
            await _seed_artigo(s, "Aula sobre empenho", publicado=True, modulo=mod)

    async with SessionLocal() as s:
        # prateleira do Class: aula não aparece solta (vive dentro do módulo)
        prateleira = await service.listar_artigos(s, sem_modulo=True)
        # busca: aula ENTRA no resultado (achar "empenho" numa aula é desejável)
        busca = await service.listar_artigos(s, q="aula sobre empenho")

    assert [a.titulo for a in prateleira] == ["Artigo avulso"]
    assert [a.titulo for a in busca] == ["Aula sobre empenho"]
    assert busca[0].modulo is not None and busca[0].modulo.slug == "captacao-101"


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
