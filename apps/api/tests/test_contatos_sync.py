"""Motor de sync da agenda ↔ provedor: casamento, conflito, remoção e falha.

Usa um provedor FAKE registrado no mesmo registry dos reais — é o contrato do
Protocol que está sob teste, não o Google/Microsoft/Apple em si.
"""

from __future__ import annotations

import copy
import uuid

from sqlalchemy import select, text

from src.core.crypto import cifrar_json
from src.db.session import rls_session
from src.integrations.contatos._http import ProvedorClientError
from src.integrations.contatos.base import ContatoExterno, PaginaRemota, register
from src.models.contato import Contato
from src.models.integracao_contatos import ContatoVinculo, IntegracaoContatos
from src.models.sync_run import SyncRun
from src.schemas.contato import (
    ContatoCanonico,
    ContatoCreate,
    ContatoEmail,
    ContatoTelefone,
    ContatoUpdate,
)
from src.services import contatos as contatos_service
from src.services import contatos_sync
from tests.conftest import _owner_engine


class ProvedorFake:
    provedor_id = "fake"
    rotulo = "Fake"
    tipo_auth = "oauth"

    def __init__(self) -> None:
        self.itens: dict[str, ContatoExterno] = {}
        self.removidos: list[ContatoExterno] = []
        self.seq = 0
        self.completa = True
        self.falha: Exception | None = None

    def semear(self, canonico: ContatoCanonico) -> str:
        self.seq += 1
        ident = f"ext{self.seq}"
        self.itens[ident] = ContatoExterno(
            id_externo=ident, canonico=canonico, etag=f"etag{self.seq}"
        )
        return ident

    async def disponivel(self) -> bool:
        return True

    async def identidade(self, cred) -> str:
        return "fake@teste"

    async def listar(self, cred, sync_token):
        if self.falha:
            raise self.falha
        itens = [copy.deepcopy(i) for i in self.itens.values()] + self.removidos
        self.removidos = []
        return PaginaRemota(itens=itens, sync_token="tok", completa=self.completa)

    async def criar(self, cred, canonico):
        if self.falha:
            raise self.falha
        ident = self.semear(copy.deepcopy(canonico))
        return self.itens[ident]

    async def atualizar(self, cred, id_externo, etag, canonico):
        externo = ContatoExterno(
            id_externo=id_externo, canonico=copy.deepcopy(canonico), etag=f"{etag}+"
        )
        self.itens[id_externo] = externo
        return externo

    async def remover(self, cred, id_externo, etag):
        self.itens.pop(id_externo, None)


fake = register(ProvedorFake())


def _canon(nome: str = "Ana", **kwargs) -> ContatoCanonico:
    return ContatoCanonico(nome=nome, **kwargs)


async def _seed_integracao(usuario_id: uuid.UUID, direcao: str = "bidirecional") -> uuid.UUID:
    ident = uuid.uuid4()
    async with _owner_engine.begin() as conn:
        # FORCE RLS: até o owner precisa do tenant setado para o WITH CHECK
        await conn.execute(
            text("SELECT set_config('app.usuario_id', :uid, true)"),
            {"uid": str(usuario_id)},
        )
        await conn.execute(
            text(
                "INSERT INTO integracoes_contatos (id, usuario_id, provedor, conta, "
                "status, direcao, credenciais) VALUES "
                "(:id,:uid,'fake','fake@teste','conectada',:dir,:cred)"
            ),
            {
                "id": ident,
                "uid": usuario_id,
                "dir": direcao,
                "cred": cifrar_json({"access_token": "x", "expira_em": 4102444800}),
            },
        )
    return ident


async def _integracao(session, integracao_id: uuid.UUID) -> IntegracaoContatos:
    return (
        await session.execute(
            select(IntegracaoContatos).where(IntegracaoContatos.id == integracao_id)
        )
    ).scalar_one()


def _reset_fake() -> None:
    fake.itens.clear()
    fake.removidos.clear()
    fake.seq = 0
    fake.completa = True
    fake.falha = None


# ── exportação ──────────────────────────────────────────────────────────────


async def test_exporta_cria_no_provedor_e_nao_reescreve_sem_mudanca(seed_user) -> None:
    _reset_fake()
    uid = await seed_user("sync1@a.com")
    integracao_id = await _seed_integracao(uid)

    async with rls_session(uid) as s:
        await contatos_service.criar(s, usuario_id=uid, dados=ContatoCreate(nome="Ana"))
        await contatos_service.criar(s, usuario_id=uid, dados=ContatoCreate(nome="Bruno"))
        r = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
    assert (r.status, r.exportados) == ("ok", 2)
    assert len(fake.itens) == 2

    # 2ª rodada sem mudança: não escreve de novo (é o hash que impede o looping)
    async with rls_session(uid) as s:
        r2 = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
    assert (r2.exportados, r2.atualizados_remoto, r2.atualizados_local) == (0, 0, 0)

    # muda no Hub → sobe só o que mudou
    async with rls_session(uid) as s:
        ana = (await contatos_service.listar(s, busca="Ana"))[0]
        await contatos_service.atualizar(s, ana, ContatoUpdate(cargo="Secretária"))
        r3 = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
    assert (r3.atualizados_remoto, r3.exportados) == (1, 0)
    assert any(i.canonico.cargo == "Secretária" for i in fake.itens.values())


# ── importação e casamento ──────────────────────────────────────────────────


async def test_importa_contatos_novos_do_provedor(seed_user) -> None:
    _reset_fake()
    uid = await seed_user("sync2@a.com")
    integracao_id = await _seed_integracao(uid)
    fake.semear(_canon("Carla", emails=[ContatoEmail(valor="carla@x.gov.br")]))

    async with rls_session(uid) as s:
        r = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
        contatos = await contatos_service.listar(s)
    assert (r.importados, r.status) == (1, "ok")
    assert contatos[0].nome == "Carla" and contatos[0].origem == "fake"


async def test_importacao_casa_por_email_e_devolve_o_mesclado(seed_user) -> None:
    _reset_fake()
    uid = await seed_user("sync3@a.com")
    integracao_id = await _seed_integracao(uid)
    fake.semear(
        _canon(
            "Ana",
            emails=[ContatoEmail(valor="ana@sp.gov.br")],
            telefones=[ContatoTelefone(valor="11988887777")],
        )
    )

    async with rls_session(uid) as s:
        await contatos_service.criar(
            s,
            usuario_id=uid,
            dados=ContatoCreate(
                nome="Ana",
                cargo="Secretária",
                emails=[ContatoEmail(valor="ana@sp.gov.br")],
            ),
        )
        r = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
        contatos = await contatos_service.listar(s)

    assert len(contatos) == 1  # casou pelo e-mail: não duplicou
    assert (r.importados, r.atualizados_local) == (0, 1)
    assert contatos[0].cargo == "Secretária"  # dado que só o Hub tinha
    assert contatos[0].telefones[0]["valor"] == "11988887777"  # veio do provedor
    # e o resultado mesclado volta para o provedor na mesma rodada
    assert r.atualizados_remoto == 1
    remoto = next(iter(fake.itens.values())).canonico
    assert remoto.cargo == "Secretária" and remoto.telefones


async def test_dois_remotos_com_o_mesmo_email_nao_duplicam_vinculo(seed_user) -> None:
    """Gabinete com e-mail compartilhado: o 2º remoto casa no mesmo contato local
    e não pode estourar a PK de `contato_vinculos`."""
    _reset_fake()
    uid = await seed_user("sync12@a.com")
    integracao_id = await _seed_integracao(uid)
    fake.semear(_canon("Ana", emails=[ContatoEmail(valor="gabinete@sp.gov.br")]))
    fake.semear(
        _canon(
            "Ana Maria",
            emails=[ContatoEmail(valor="gabinete@sp.gov.br")],
            telefones=[ContatoTelefone(valor="11988887777")],
        )
    )

    async with rls_session(uid) as s:
        r = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
        assert r.status == "ok"
        assert len(await contatos_service.listar(s)) == 1
        assert len((await s.execute(select(ContatoVinculo))).scalars().all()) == 1


async def test_conflito_dos_dois_lados_resolve_por_merge(seed_user) -> None:
    _reset_fake()
    uid = await seed_user("sync4@a.com")
    integracao_id = await _seed_integracao(uid)

    async with rls_session(uid) as s:
        await contatos_service.criar(
            s,
            usuario_id=uid,
            dados=ContatoCreate(nome="Ana", emails=[ContatoEmail(valor="ana@sp.gov.br")]),
        )
        await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )

    # muda dos DOIS lados desde a última sync
    ident = next(iter(fake.itens))
    fake.itens[ident].canonico.organizacao = "Prefeitura"
    fake.itens[ident].etag = "etag-novo"
    async with rls_session(uid) as s:
        ana = (await contatos_service.listar(s))[0]
        await contatos_service.atualizar(s, ana, ContatoUpdate(cargo="Secretária"))
        r = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
        ana = (await contatos_service.listar(s))[0]

    assert r.conflitos == 1
    assert ana.cargo == "Secretária" and ana.organizacao == "Prefeitura"
    assert r.atualizados_remoto == 1  # o merge sobe para o provedor
    assert fake.itens[ident].canonico.cargo == "Secretária"


# ── remoções ────────────────────────────────────────────────────────────────


async def test_arquivar_no_hub_remove_no_provedor_e_limpa_tombstone(seed_user) -> None:
    _reset_fake()
    uid = await seed_user("sync5@a.com")
    integracao_id = await _seed_integracao(uid)

    async with rls_session(uid) as s:
        await contatos_service.criar(s, usuario_id=uid, dados=ContatoCreate(nome="Ana"))
        await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
    assert len(fake.itens) == 1

    async with rls_session(uid) as s:
        ana = (await contatos_service.listar(s))[0]
        await contatos_service.arquivar(s, ana)
        r = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
        assert r.removidos_remoto == 1
        assert fake.itens == {}
        # sem vínculo pendente, o tombstone pode sair de vez
        assert await contatos_sync.limpar_arquivados(s) == 1
        assert (await s.execute(select(Contato))).scalars().all() == []


async def test_remocao_no_provedor_arquiva_no_hub(seed_user) -> None:
    _reset_fake()
    uid = await seed_user("sync6@a.com")
    integracao_id = await _seed_integracao(uid)
    fake.semear(_canon("Carla", emails=[ContatoEmail(valor="carla@x.gov.br")]))

    async with rls_session(uid) as s:
        await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
        assert len(await contatos_service.listar(s)) == 1

    fake.itens.clear()  # sumiu do provedor; a leitura é completa → foi removido
    async with rls_session(uid) as s:
        r = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
        assert r.removidos_local == 1
        assert await contatos_service.listar(s) == []
        assert len(await contatos_service.listar(s, incluir_arquivados=True)) == 1


async def test_delta_incompleto_nao_infere_remocao(seed_user) -> None:
    _reset_fake()
    uid = await seed_user("sync7@a.com")
    integracao_id = await _seed_integracao(uid)
    fake.semear(_canon("Carla", emails=[ContatoEmail(valor="carla@x.gov.br")]))

    async with rls_session(uid) as s:
        await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )

    fake.completa = False  # delta: ausência não quer dizer remoção
    fake.itens.clear()
    async with rls_session(uid) as s:
        r = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
        assert r.removidos_local == 0
        assert len(await contatos_service.listar(s)) == 1


# ── direção, falhas e isolamento ────────────────────────────────────────────


async def test_direcao_importar_nao_exporta(seed_user) -> None:
    _reset_fake()
    uid = await seed_user("sync8@a.com")
    integracao_id = await _seed_integracao(uid, direcao="importar")
    fake.semear(_canon("Carla", emails=[ContatoEmail(valor="carla@x.gov.br")]))

    async with rls_session(uid) as s:
        await contatos_service.criar(s, usuario_id=uid, dados=ContatoCreate(nome="Local"))
        r = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
    assert (r.importados, r.exportados) == (1, 0)
    assert len(fake.itens) == 1  # o contato local não subiu


async def test_falha_do_provedor_marca_status_e_registra_sync_run(seed_user) -> None:
    _reset_fake()
    uid = await seed_user("sync9@a.com")
    integracao_id = await _seed_integracao(uid)
    fake.falha = ProvedorClientError("token inválido", 401)

    async with rls_session(uid) as s:
        r = await contatos_sync.sincronizar(
            s, usuario_id=uid, integracao=await _integracao(s, integracao_id)
        )
        integracao = await _integracao(s, integracao_id)
        assert r.status == "erro" and "token inválido" in (r.erro or "")
        assert integracao.status == "expirada"  # 401/403 → pede reconexão
        assert integracao.ultimo_erro

    async with _owner_engine.begin() as conn:
        linhas = (await conn.execute(text("SELECT fonte, status FROM sync_runs"))).fetchall()
    assert ("contatos_fake", "erro") in [(f, s) for f, s in linhas]


async def test_rls_isola_integracoes_e_vinculos(seed_user) -> None:
    _reset_fake()
    a = await seed_user("sync10@a.com")
    b = await seed_user("sync10@b.com")
    integracao_a = await _seed_integracao(a)
    await _seed_integracao(b)

    async with rls_session(a) as s:
        await contatos_service.criar(s, usuario_id=a, dados=ContatoCreate(nome="Ana"))
        await contatos_sync.sincronizar(
            s, usuario_id=a, integracao=await _integracao(s, integracao_a)
        )

    async with rls_session(b) as s:
        assert len((await s.execute(select(IntegracaoContatos))).scalars().all()) == 1
        assert (await s.execute(select(ContatoVinculo))).scalars().all() == []
        assert (await s.execute(select(Contato))).scalars().all() == []

    async with rls_session(a) as s:
        assert len((await s.execute(select(ContatoVinculo))).scalars().all()) == 1


async def test_sincronizar_todas_roda_integracoes_ativas(seed_user) -> None:
    _reset_fake()
    uid = await seed_user("sync11@a.com")
    await _seed_integracao(uid)
    fake.semear(_canon("Carla", emails=[ContatoEmail(valor="carla@x.gov.br")]))

    async with rls_session(uid) as s:
        resultados = await contatos_sync.sincronizar_todas(s, usuario_id=uid)
        assert [r.status for r in resultados] == ["ok"]
        assert len(await contatos_service.listar(s)) == 1
        runs = (await s.execute(select(SyncRun))).scalars().all()
        assert [r.tipo for r in runs] == ["avulso"]
