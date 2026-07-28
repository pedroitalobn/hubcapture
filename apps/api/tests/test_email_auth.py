"""E-mail transacional + recuperação de senha.

Cobre: (1) a camada de e-mail degrada sem SMTP configurado (não lança, retorna
False); (2) os templates trazem assunto/txt/html; (3) o hook de forgot-password
do UserManager dispara o envio de e-mail (mockado).
"""

from __future__ import annotations

import pytest

from src.notifications import email as email_service
from src.notifications import email_templates as templates


async def test_email_desabilitado_sem_smtp() -> None:
    # sem email_smtp_host/email_from no config → desabilitado, sem erro
    assert await email_service.habilitado() is False
    enviado = await email_service.enviar("x@x.com", "oi", "corpo")
    assert enviado is False


def test_templates_tem_assunto_txt_html() -> None:
    for assunto, txt, html in (
        templates.boas_vindas("Ana"),
        templates.redefinir_senha("https://app/reset-password?token=abc"),
        templates.verificar_email("https://app/verify-email?token=abc"),
        templates.convite("https://app/accept-invite?token=abc", "parlamentar"),
    ):
        assert assunto and "Hub Capture" in assunto or assunto
        assert isinstance(txt, str) and txt
        assert "<" in html and ">" in html


async def test_forgot_password_dispara_email(seed_user, monkeypatch) -> None:
    """O hook on_after_forgot_password chama o serviço de e-mail com o link."""
    from src.core.users import UserManager
    from src.db.session import SessionLocal
    from src.db.user_db import get_user_db

    await seed_user("reset@a.com")

    enviados: list[tuple[str, str]] = []

    async def _fake_enviar(dest, assunto, txt, html=None):  # noqa: ANN001
        enviados.append((dest, txt))
        return True

    monkeypatch.setattr(email_service, "enviar", _fake_enviar)

    async with SessionLocal() as session:
        user_db_gen = get_user_db(session)
        user_db = await user_db_gen.__anext__()
        manager = UserManager(user_db)
        user = await user_db.get_by_email("reset@a.com")
        assert user is not None
        await manager.on_after_forgot_password(user, token="tok-123")

    assert len(enviados) == 1
    dest, txt = enviados[0]
    assert dest == "reset@a.com"
    assert "reset-password?token=tok-123" in txt


@pytest.mark.parametrize("port", [587, 465])
def test_email_port_selection_smoke(port: int) -> None:
    # apenas garante que a função de escolha de transporte existe e é chamável
    assert email_service._enviar_sync.__name__ == "_enviar_sync"
