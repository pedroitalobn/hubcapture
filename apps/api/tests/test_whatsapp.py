"""WhatsApp (Uniq): cliente desabilitado, mapa telefone→usuário e dispatch."""

from __future__ import annotations

from sqlalchemy import select

from src.db.session import SessionLocal, rls_session
from src.models.alerta import Alerta
from src.models.usuario import Usuario
from src.notifications import uniq
from src.services import dispatch_alerts


async def test_uniq_desabilitado_sem_key() -> None:
    assert await uniq.enviar("+5511999999999", "oi") is False
    # sem token configurado, o webhook não valida (dev)
    assert await uniq.validar_webhook(None) is True


async def test_usuario_por_telefone(seed_user) -> None:
    await seed_user("z@z.com", telefone_wpp="+5511988887777", optin_wpp=True)
    async with SessionLocal() as s:
        u = await dispatch_alerts.usuario_por_telefone(s, "+5511988887777")
        assert u is not None and u.email == "z@z.com"
        assert await dispatch_alerts.usuario_por_telefone(s, "+000") is None


async def test_despachar_wpp_respeita_optin_e_alertas(
    seed_user, seed_municipio, seed_proposta, monkeypatch
) -> None:
    uid = await seed_user(
        "w@w.com", telefone_wpp="+5511900001111", optin_wpp=True
    )
    await seed_municipio(uid, "3550308")
    await seed_proposta("fns", "P1", "3550308", "UBS")

    enviados: list[tuple[str, str]] = []

    async def fake_enviar(telefone, mensagem):
        enviados.append((telefone, mensagem))
        return True

    monkeypatch.setattr(uniq, "enviar", fake_enviar)

    async with rls_session(uid) as s:
        from src.models.proposta import Proposta

        proposta_id = (await s.execute(select(Proposta.id))).scalar_one()
        s.add(Alerta(usuario_id=uid, proposta_id=proposta_id, tipo="status"))
        await s.flush()
        usuario = (
            await s.execute(select(Usuario).where(Usuario.id == uid))
        ).scalar_one()
        n = await dispatch_alerts.despachar_wpp(s, usuario)

    assert n == 1
    assert len(enviados) == 1
    assert enviados[0][0] == "+5511900001111"


async def test_despachar_wpp_sem_optin_nao_envia(seed_user) -> None:
    uid = await seed_user("no@no.com", telefone_wpp="+55110002222", optin_wpp=False)
    async with rls_session(uid) as s:
        usuario = (
            await s.execute(select(Usuario).where(Usuario.id == uid))
        ).scalar_one()
        assert await dispatch_alerts.despachar_wpp(s, usuario) == 0
