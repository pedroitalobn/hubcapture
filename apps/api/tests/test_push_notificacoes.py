"""Notificações (§63): Web Push (cifra/VAPID) e canais de alerta da conta."""

from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select

from src.db.session import rls_session
from src.models.alerta import Alerta
from src.models.usuario import Usuario
from src.notifications import uniq, webpush
from src.services import canais_alerta, monitoramentos, oportunidades


def _ua() -> tuple[ec.EllipticCurvePrivateKey, str, str]:
    """Um 'navegador': par P-256 + auth secret, como o PushManager gera."""
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = priv.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return priv, webpush.b64url(pub), webpush.b64url(b"0123456789abcdef")


def _decifrar(corpo: bytes, ua_priv: ec.EllipticCurvePrivateKey, p256dh: str, auth: str) -> bytes:
    """O lado do NAVEGADOR da RFC 8291 — prova que a cifra é decifrável."""
    salt, idlen = corpo[:16], corpo[20]
    as_pub = corpo[21 : 21 + idlen]
    cifrado = corpo[21 + idlen :]
    segredo = ua_priv.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub)
    )
    ikm = webpush._hkdf(
        webpush.b64url_decode(auth),
        segredo,
        b"WebPush: info\x00" + webpush.b64url_decode(p256dh) + as_pub,
        32,
    )
    cek = webpush._hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = webpush._hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    claro = AESGCM(cek).decrypt(nonce, cifrado, None)
    assert claro.endswith(b"\x02")  # delimitador do último registro
    return claro[:-1]


def test_cifra_aes128gcm_ida_e_volta():
    ua_priv, p256dh, auth = _ua()
    corpo = webpush.cifrar(b'{"title":"oi"}', p256dh, auth)
    assert int.from_bytes(corpo[16:20], "big") == 4096  # record size
    assert corpo[20] == 65  # keyid = chave pública efêmera
    assert _decifrar(corpo, ua_priv, p256dh, auth) == b'{"title":"oi"}'


def test_cifra_vetor_da_rfc_8291():
    """Apêndice A da RFC 8291 — a mesma entrada tem de dar o mesmo corpo."""
    as_priv = ec.derive_private_key(
        int.from_bytes(webpush.b64url_decode("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
        ec.SECP256R1(),
    )
    corpo = webpush.cifrar(
        b"When I grow up, I want to be a watermelon",
        "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
        "BTBZMqHH6r4Tts7J_aSIgg",
        efemera=as_priv,
        salt=webpush.b64url_decode("DGv6ra1nlYgDCS1FRnbzlw"),
    )
    assert webpush.b64url(corpo) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
    )


def test_vapid_assina_es256_verificavel():
    chaves = webpush.gerar_chaves()
    cab = webpush.cabecalho_vapid(
        "https://fcm.googleapis.com/fcm/send/abc", chaves, "mailto:a@b.com", agora=1_000
    )
    assert cab.startswith("vapid t=") and cab.endswith(f", k={chaves.publica}")
    jwt = cab[len("vapid t=") : cab.index(",")]
    cabecalho, claims, assinatura = jwt.split(".")
    dados = json.loads(base64.urlsafe_b64decode(claims + "=="))
    assert dados["aud"] == "https://fcm.googleapis.com"
    assert dados["exp"] == 1_000 + 12 * 3600
    bruto = webpush.b64url_decode(assinatura)
    pub = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), webpush.b64url_decode(chaves.publica)
    )
    pub.verify(
        encode_dss_signature(int.from_bytes(bruto[:32], "big"), int.from_bytes(bruto[32:], "big")),
        f"{cabecalho}.{claims}".encode(),
        ec.ECDSA(hashes.SHA256()),
    )


def test_endpoint_so_de_servico_de_push():
    assert webpush.endpoint_permitido("https://fcm.googleapis.com/fcm/send/x")
    assert webpush.endpoint_permitido("https://web.push.apple.com/abc")
    assert webpush.endpoint_permitido("https://updates.push.services.mozilla.com/wpush/v2/x")
    assert not webpush.endpoint_permitido("http://fcm.googleapis.com/x")  # sem TLS
    assert not webpush.endpoint_permitido("https://api:8000/admin")  # SSRF
    assert not webpush.endpoint_permitido("https://evilpush.apple.com.attacker.io/x")


async def test_garantir_chaves_gera_uma_vez_e_persiste():
    a = await webpush.garantir_chaves()
    b = await webpush.garantir_chaves()
    assert a == b and len(webpush.b64url_decode(a.publica)) == 65


# ------------------------------------------------------------- canais


async def test_optin_da_conta_vale_para_busca_criada_so_com_painel(
    seed_user, seed_municipio, seed_proposta, monkeypatch
):
    """O defeito relatado: WhatsApp ligado na conta e nenhum alerta saía por lá,
    porque o monitoramento nascia com canais=['painel']."""
    uid = await seed_user("c@c.com", telefone_wpp="+5585999990000", optin_wpp=True)
    await seed_municipio(uid, "2301307")
    async with rls_session(uid) as s:
        await monitoramentos.criar_busca(
            s, uid, municipio_ibge="2301307", area=None, fonte=None, canais=["painel"]
        )
    await seed_proposta("transferegov_disc", "P-NOVA", "2301307", "UBS nova")

    enviados: list[str] = []

    async def fake_uniq(telefone, mensagem):
        enviados.append(mensagem)
        return True

    monkeypatch.setattr(uniq, "enviar", fake_uniq)
    async with rls_session(uid) as s:
        usuario = (await s.execute(select(Usuario).where(Usuario.id == uid))).scalar_one()
        assert "wpp" in await canais_alerta.da_conta(s, usuario)
        criados = await oportunidades.varredura(s, usuario)

    assert criados == 1
    assert len(enviados) == 1 and "UBS nova" in enviados[0]


async def test_canal_que_falha_nao_derruba_o_alerta(
    seed_user, seed_municipio, seed_proposta, monkeypatch
):
    """Um 4xx do Uniq estourava a varredura e a transação levava o alerta junto."""
    uid = await seed_user("f@f.com", telefone_wpp="+5585999991111", optin_wpp=True)
    await seed_municipio(uid, "2301307")
    async with rls_session(uid) as s:
        await monitoramentos.criar_busca(
            s, uid, municipio_ibge="2301307", area=None, fonte=None, canais=["painel"]
        )
    await seed_proposta("transferegov_disc", "P-X", "2301307", "Quadra")

    async def uniq_quebrado(telefone, mensagem):
        raise RuntimeError("HTTP 401")

    monkeypatch.setattr(uniq, "enviar", uniq_quebrado)
    async with rls_session(uid) as s:
        usuario = (await s.execute(select(Usuario).where(Usuario.id == uid))).scalar_one()
        assert await oportunidades.varredura(s, usuario) == 1

    async with rls_session(uid) as s:
        assert len((await s.execute(select(Alerta))).scalars().all()) == 1


async def test_push_entrega_e_apaga_inscricao_expirada(seed_user, monkeypatch):
    uid = await seed_user("p@p.com")
    _, p256dh, auth = _ua()
    async with rls_session(uid) as s:
        for endpoint in ("https://fcm.googleapis.com/ok", "https://fcm.googleapis.com/velha"):
            await canais_alerta.inscrever(
                s, uid, endpoint=endpoint, p256dh=p256dh, auth=auth, user_agent="teste"
            )

    recebidos: list[dict] = []

    async def fake_enviar(endpoint, p256dh, auth, mensagem):
        if endpoint.endswith("velha"):
            raise webpush.InscricaoExpirada("HTTP 410")
        recebidos.append(mensagem)
        return True

    monkeypatch.setattr(webpush, "enviar", fake_enviar)
    async with rls_session(uid) as s:
        r = await canais_alerta.enviar_push(s, uid, {"title": "t", "body": "b"})
    assert r == {"enviados": 1, "falhas": 0, "removidas": 1}
    async with rls_session(uid) as s:
        restantes = await canais_alerta.inscricoes(s, uid)
    assert [i.endpoint for i in restantes] == ["https://fcm.googleapis.com/ok"]


def test_mensagem_push_agrupa_o_lote():
    alertas = [
        Alerta(tipo="nova_proposta", payload={"titulo": f"P{i}", "municipio_nome": "Apuiarés"})
        for i in range(5)
    ]
    msg = oportunidades.mensagem_push(alertas)
    assert msg["title"] == "Hub Capture · 5 atualizações"
    assert msg["url"] == "/panel/alerts" and "+2 outras" in msg["body"]


async def test_rotas_de_notificacao_e_oportunidades(seed_user, seed_municipio):
    """Exercita os ROUTERS (§52): preferências, inscrição de push e a lista."""
    import httpx

    from src.api.deps import get_rls_db
    from src.core.users import current_active_user
    from src.main import app

    uid = await seed_user("rotas@n.com")
    await seed_municipio(uid, "2301307")
    usuario = Usuario(id=uid, email="rotas@n.com", is_active=True, is_superuser=False)

    async def _sessao():
        async with rls_session(uid) as s:
            yield s

    app.dependency_overrides[current_active_user] = lambda: usuario
    app.dependency_overrides[get_rls_db] = _sessao
    _, p256dh, auth = _ua()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.put("/api/v1/notifications/preferences", json={"email": True})
            assert r.status_code == 200, r.text
            assert r.json()["email"] is True and r.json()["push_inscricoes"] == 0

            r = await c.get("/api/v1/notifications/push/key")
            assert r.status_code == 200 and len(r.json()["chave_publica"]) > 80

            corpo = {
                "endpoint": "https://api:8000/interno",
                "keys": {"p256dh": p256dh, "auth": auth},
            }
            r = await c.post("/api/v1/notifications/push/subscriptions", json=corpo)
            assert r.status_code == 422  # SSRF barrado

            corpo["endpoint"] = "https://fcm.googleapis.com/fcm/send/abc"
            r = await c.post("/api/v1/notifications/push/subscriptions", json=corpo)
            assert r.status_code == 204, r.text
            r = await c.get("/api/v1/notifications/preferences")
            assert r.json()["push_inscricoes"] == 1

            r = await c.get("/api/v1/opportunities", params={"municipio": "2301307"})
            assert r.status_code == 200, r.text
            assert r.json()["municipios"][0]["ibge"] == "2301307"
    finally:
        app.dependency_overrides.clear()

    async with rls_session(uid) as s:
        usuario_db = (await s.execute(select(Usuario).where(Usuario.id == uid))).scalar_one()
        assert await canais_alerta.da_conta(s, usuario_db) == {"email", "push"}
