"""Agenda de contatos: normalização/dedup, vCard, CRUD e RLS."""

from __future__ import annotations

import uuid

from src.db.session import rls_session
from src.ingestion.normalizer_contato import (
    calcular_chave_dedup,
    calcular_hash,
    canonizar,
    mesclar,
    normalizar_telefone,
)
from src.integrations.contatos import vcard
from src.schemas.contato import (
    ContatoCanonico,
    ContatoCreate,
    ContatoEmail,
    ContatoTelefone,
    ContatoUpdate,
)
from src.services import contatos as service


def _canon(**kwargs) -> ContatoCanonico:
    base = {"nome": "Ana", "sobrenome": "Souza"}
    return ContatoCanonico(**{**base, **kwargs})


# ── normalização / dedup ────────────────────────────────────────────────────


def test_normalizar_telefone_formatos_equivalentes() -> None:
    esperado = "+5511988887777"
    for bruto in ("(11) 98888-7777", "11988887777", "+55 11 98888-7777", "55 11 98888 7777"):
        assert normalizar_telefone(bruto) == esperado
    assert normalizar_telefone("") is None


def test_chave_dedup_prioriza_email_depois_telefone_depois_nome() -> None:
    com_email = _canon(
        emails=[ContatoEmail(valor="Ana@SP.gov.BR")],
        telefones=[ContatoTelefone(valor="11988887777")],
    )
    assert calcular_chave_dedup(com_email) == "email:ana@sp.gov.br"

    so_telefone = _canon(telefones=[ContatoTelefone(valor="(11) 98888-7777")])
    assert calcular_chave_dedup(so_telefone) == "tel:+5511988887777"

    so_nome = _canon(organizacao="Prefeitura de São Paulo")
    assert calcular_chave_dedup(so_nome) == "nome:ana-souza@prefeitura-de-sao-paulo"


def test_hash_ignora_formatacao_mas_pega_mudanca_real() -> None:
    a = canonizar(
        _canon(
            emails=[ContatoEmail(valor="ana@sp.gov.br")],
            telefones=[ContatoTelefone(valor="(11) 98888-7777")],
        )
    )
    b = canonizar(
        _canon(
            emails=[ContatoEmail(valor="ANA@sp.gov.br")],
            telefones=[ContatoTelefone(valor="+5511988887777")],
        )
    )
    assert a.hash_conteudo == b.hash_conteudo  # só mudou a escrita

    c = canonizar(_canon(emails=[ContatoEmail(valor="ana@sp.gov.br")], cargo="Secretária"))
    assert c.hash_conteudo != a.hash_conteudo


def test_canonizar_remove_duplicados_preservando_o_principal() -> None:
    dados = canonizar(
        _canon(
            emails=[
                ContatoEmail(tipo="trabalho", valor="ana@sp.gov.br"),
                ContatoEmail(tipo="pessoal", valor="ANA@SP.GOV.BR"),
            ]
        )
    )
    assert [e.valor for e in dados.emails] == ["ana@sp.gov.br"]
    assert dados.emails[0].tipo == "trabalho"


def test_mesclar_soma_sem_perder_dado_dos_dois_lados() -> None:
    local = canonizar(
        _canon(
            cargo="Secretária de Saúde",
            emails=[ContatoEmail(valor="ana@sp.gov.br")],
            tags=["saude"],
        )
    )
    remoto = canonizar(
        _canon(
            organizacao="Prefeitura",
            telefones=[ContatoTelefone(valor="11988887777")],
            tags=["gabinete"],
        )
    )
    junto = mesclar(local, remoto)
    assert junto.cargo == "Secretária de Saúde"  # só o local tinha
    assert junto.organizacao == "Prefeitura"  # só o remoto tinha
    assert [e.valor for e in junto.emails] == ["ana@sp.gov.br"]
    assert [t.valor for t in junto.telefones] == ["11988887777"]
    assert junto.tags == ["gabinete", "saude"]
    assert junto.hash_conteudo == calcular_hash(junto)


# ── vCard ───────────────────────────────────────────────────────────────────


def test_vcard_roundtrip_preserva_campos_e_escape() -> None:
    original = canonizar(
        ContatoCanonico(
            nome="João",
            sobrenome="Silva; Costa",
            organizacao="Prefeitura de Cuiabá",
            cargo="Chefe de Gabinete",
            emails=[ContatoEmail(tipo="trabalho", valor="joao@cuiaba.mt.gov.br")],
            telefones=[ContatoTelefone(tipo="celular", valor="(65) 99999-1111")],
            notas="linha 1\nlinha 2, com vírgula",
            tags=["gabinete", "saude"],
        )
    )
    volta = vcard.parsear(vcard.serializar(original))[0]
    assert volta.nome == "João"
    assert volta.sobrenome == "Silva; Costa"  # ';' escapado dentro do campo
    assert volta.organizacao == "Prefeitura de Cuiabá"
    assert volta.cargo == "Chefe de Gabinete"
    assert [(e.tipo, e.valor) for e in volta.emails] == [
        ("trabalho", "joao@cuiaba.mt.gov.br")
    ]
    assert [(t.tipo, t.valor) for t in volta.telefones] == [("celular", "(65) 99999-1111")]
    assert volta.notas == "linha 1\nlinha 2, com vírgula"
    assert volta.tags == ["gabinete", "saude"]
    assert canonizar(volta).hash_conteudo == original.hash_conteudo


def test_vcard_le_varios_cartoes_com_dobra_e_grupo_apple() -> None:
    bruto = (
        "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Maria Lima\r\n"
        "item1.EMAIL;type=INTERNET;type=WORK:maria@x.gov.br\r\n"
        "NOTE:um texto bem comprido que precisa ser dobrado porque passa de setenta\r\n"
        "  e cinco octetos no total\r\n"
        "END:VCARD\r\n"
        "BEGIN:VCARD\r\nVERSION:3.0\r\nN:Pereira;Carlos;;;\r\nTEL;TYPE=CELL:+5565999991111\r\nEND:VCARD\r\n"
    )
    cartoes = vcard.parsear(bruto)
    assert len(cartoes) == 2
    assert cartoes[0].nome == "Maria" and cartoes[0].sobrenome == "Lima"  # veio do FN
    assert cartoes[0].emails[0].valor == "maria@x.gov.br"
    assert "dobrado" in (cartoes[0].notas or "")
    assert cartoes[1].nome == "Carlos" and cartoes[1].sobrenome == "Pereira"


def test_vcard_serializa_com_dobra_de_75_octetos() -> None:
    texto = vcard.serializar(_canon(notas="x" * 200))
    assert all(
        len(linha.encode()) <= 75 for linha in texto.split("\r\n") if linha
    )


# ── serviço (RLS/CRUD/import) ───────────────────────────────────────────────


async def test_rls_isola_contatos_entre_usuarios(seed_user) -> None:
    a = await seed_user("ca@a.com")
    b = await seed_user("cb@b.com")

    async with rls_session(a) as s:
        await service.criar(s, usuario_id=a, dados=ContatoCreate(nome="Ana"))
    async with rls_session(b) as s:
        await service.criar(s, usuario_id=b, dados=ContatoCreate(nome="Bruno"))

    async with rls_session(a) as s:
        assert [c.nome for c in await service.listar(s)] == ["Ana"]
    async with rls_session(b) as s:
        assert [c.nome for c in await service.listar(s)] == ["Bruno"]


async def test_crud_busca_e_arquivamento(seed_user) -> None:
    uid = await seed_user("crud@a.com")
    async with rls_session(uid) as s:
        contato = await service.criar(
            s,
            usuario_id=uid,
            dados=ContatoCreate(
                nome="Ana",
                sobrenome="Souza",
                organizacao="Prefeitura de Cuiabá",
                emails=[ContatoEmail(tipo="trabalho", valor="ana@cuiaba.mt.gov.br")],
                tags=["saude"],
            ),
        )
        assert contato.chave_dedup == "email:ana@cuiaba.mt.gov.br"
        assert contato.hash_conteudo

        atualizado = await service.atualizar(
            s, contato, ContatoUpdate(cargo="Secretária", tags=["saude", "gabinete"])
        )
        assert atualizado.cargo == "Secretária"
        assert atualizado.emails[0]["valor"] == "ana@cuiaba.mt.gov.br"  # não perdeu

        assert len(await service.listar(s, busca="cuiabá")) == 1
        assert len(await service.listar(s, tag="gabinete")) == 1
        assert len(await service.listar(s, tag="educacao")) == 0

        await service.arquivar(s, atualizado)
        assert await service.listar(s) == []
        assert len(await service.listar(s, incluir_arquivados=True)) == 1


async def test_atualizar_troca_emails_e_telefones(seed_user) -> None:
    uid = await seed_user("patch@a.com")
    async with rls_session(uid) as s:
        contato = await service.criar(
            s,
            usuario_id=uid,
            dados=ContatoCreate(nome="Ana", emails=[ContatoEmail(valor="antigo@x.gov.br")]),
        )
        atualizado = await service.atualizar(
            s,
            contato,
            ContatoUpdate(
                emails=[ContatoEmail(tipo="trabalho", valor="novo@x.gov.br")],
                telefones=[ContatoTelefone(tipo="celular", valor="(65) 99999-1111")],
            ),
        )
    assert [e["valor"] for e in atualizado.emails] == ["novo@x.gov.br"]
    assert atualizado.telefones[0]["tipo"] == "celular"
    assert atualizado.chave_dedup == "email:novo@x.gov.br"  # a chave acompanha


async def test_contato_read_aceita_colunas_nulas(seed_user) -> None:
    """Linha com jsonb/array nulos (ex.: carga direta) não quebra a serialização."""
    from sqlalchemy import text

    from src.schemas.contato import ContatoRead
    from tests.conftest import _owner_engine

    uid = await seed_user("nulo@a.com")
    async with _owner_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.usuario_id', :uid, true)"), {"uid": str(uid)}
        )
        await conn.execute(
            text(
                "INSERT INTO contatos (id, usuario_id, nome, origem) "
                "VALUES (:id,:uid,'Ana','manual')"
            ),
            {"id": uuid.uuid4(), "uid": uid},
        )

    async with rls_session(uid) as s:
        lido = ContatoRead.model_validate((await service.listar(s))[0])
    assert (lido.emails, lido.telefones, lido.enderecos, lido.tags) == ([], [], [], [])


async def test_importar_vcf_cria_e_depois_mescla(seed_user) -> None:
    uid = await seed_user("vcf@a.com")
    cartao = vcard.serializar(
        _canon(emails=[ContatoEmail(valor="ana@sp.gov.br")], organizacao="Prefeitura")
    )
    async with rls_session(uid) as s:
        primeiro = await service.importar_vcf(s, usuario_id=uid, conteudo=cartao)
        assert (primeiro.importados, primeiro.atualizados) == (1, 0)

        # mesmo e-mail, agora com telefone: casa pela chave e SOMA (não duplica)
        outro = vcard.serializar(
            _canon(
                emails=[ContatoEmail(valor="ana@sp.gov.br")],
                telefones=[ContatoTelefone(valor="11988887777")],
            )
        )
        segundo = await service.importar_vcf(s, usuario_id=uid, conteudo=outro)
        assert (segundo.importados, segundo.atualizados) == (0, 1)

        contatos = await service.listar(s)
        assert len(contatos) == 1
        assert contatos[0].organizacao == "Prefeitura"
        assert contatos[0].telefones[0]["valor"] == "11988887777"


async def test_exportar_vcf_traz_a_agenda_inteira(seed_user) -> None:
    uid = await seed_user("exp@a.com")
    async with rls_session(uid) as s:
        await service.criar(s, usuario_id=uid, dados=ContatoCreate(nome="Ana"))
        await service.criar(s, usuario_id=uid, dados=ContatoCreate(nome="Bruno"))
        conteudo = service.exportar_vcf(await service.listar(s))
    assert conteudo.count("BEGIN:VCARD") == 2
    assert len(vcard.parsear(conteudo)) == 2
