from email import policy
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from starlette.testclient import TestClient

import main
from main import build_snapshot_email, build_snapshot_email_html, fetch_snapshot, is_valid_email, parse_sender, send_snapshot_email, send_email_message


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("visitor@example.com", True),
        ("name+tag@museum.org.au", True),
        ("not-an-email", False),
        ("missing@domain", False),
        ("", False),
        ("  ", False),
    ],
)
def test_is_valid_email(email: str, expected: bool) -> None:
    assert is_valid_email(email) is expected


def test_parse_sender_handles_at_in_display_name() -> None:
    header, addr = parse_sender("Pop-timism @ MCA <admin@rackandpin.com>")
    assert addr == "admin@rackandpin.com"
    assert header == '"Pop-timism @ MCA" <admin@rackandpin.com>'


def test_build_snapshot_email_uses_email_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "EMAIL_SENDER",
        "Pop-timism @ MCA <admin@rackandpin.com>",
    )
    message = build_snapshot_email(
        to_email="visitor@example.com",
        image_bytes=b"\x89PNG\r\n\x1a\n",
    )
    assert message["From"] == '"Pop-timism @ MCA" <admin@rackandpin.com>'


def test_send_email_message_sets_smtp_envelope_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    message = build_snapshot_email(
        to_email="visitor@example.com",
        image_bytes=b"\x89PNG\r\n\x1a\n",
        from_email='"Pop-timism @ MCA" <admin@rackandpin.com>',
    )
    smtp = MagicMock()
    smtp.__enter__ = MagicMock(return_value=smtp)
    smtp.__exit__ = MagicMock(return_value=False)

    monkeypatch.setattr(main, "EMAIL_HOST", "smtp.example.com")
    monkeypatch.setattr(main.smtplib, "SMTP", MagicMock(return_value=smtp))

    send_email_message(message)

    smtp.send_message.assert_called_once_with(
        message,
        from_addr="admin@rackandpin.com",
        to_addrs=["visitor@example.com"],
    )


def test_build_snapshot_email_embeds_cid_image() -> None:
    image_bytes = b"\x89PNG\r\n\x1a\n"
    message = build_snapshot_email(
        to_email="visitor@example.com",
        image_bytes=image_bytes,
        content_type="image/png",
        from_email="noreply@example.com",
    )
    raw = message.as_bytes(policy=policy.SMTP)

    assert message["To"] == "visitor@example.com"
    assert message["From"] == "noreply@example.com"
    assert b"cid:screenshot" in raw
    assert b"Content-ID: <screenshot>" in raw
    assert b"filename=\"pop-timism.png\"" in raw


def test_build_snapshot_email_html_styles_image_to_fit_container() -> None:
    html = build_snapshot_email_html()
    assert 'src="cid:screenshot"' in html
    assert "max-width: 100%" in html
    assert "width: 100%" in html
    assert "height: auto" in html
    assert "<div style=" in html


@pytest.mark.asyncio
async def test_fetch_snapshot_follows_redirects() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = b"fake-image"
    mock_response.headers = {"content-type": "image/png"}

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)

    image_bytes, content_type = await fetch_snapshot(
        url="http://example.test/screencapture",
        client=mock_client,
    )

    mock_client.get.assert_awaited_once_with(
        "http://example.test/screencapture",
        follow_redirects=True,
    )
    assert image_bytes == b"fake-image"
    assert content_type == "image/png"


@pytest.mark.asyncio
async def test_send_snapshot_email_fetches_and_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    image_bytes = b"fake-image"
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = image_bytes
    mock_response.headers = {"content-type": "image/png"}

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.aclose = AsyncMock()

    sent: list[object] = []

    def _capture_send(message: object) -> None:
        sent.append(message)

    monkeypatch.setattr(main, "SCREENSHOT_URL", "https://example.test/snapshot")
    monkeypatch.setattr(main, "send_email_message", _capture_send)

    await send_snapshot_email("visitor@example.com", client=mock_client)

    mock_client.get.assert_awaited_once_with(
        "https://example.test/snapshot",
        follow_redirects=True,
    )
    assert len(sent) == 1
    assert sent[0]["To"] == "visitor@example.com"


def test_start_rejects_invalid_email() -> None:
    client = TestClient(main.app)
    response = client.post("/start", data={"age": "25_34", "email": "not-valid"})
    assert response.status_code == 200
    assert "Please enter a valid email address." in response.text
    assert response.headers.get("hx-trigger") is None


def test_start_reveals_app_without_email() -> None:
    client = TestClient(main.app)
    response = client.post("/start", data={"age": "25_34"})
    assert response.status_code == 200
    trigger = response.headers.get("hx-trigger", "")
    assert "reveal-app" in trigger
    assert "process-submission" in trigger


def test_start_reveals_immediately_and_queues_background_processing() -> None:
    client = TestClient(main.app)
    response = client.post("/start", data={"age": "25_34", "email": "visitor@example.com"})

    assert response.status_code == 200
    trigger = response.headers.get("hx-trigger", "")
    assert "reveal-app" in trigger
    assert "process-submission" in trigger
    assert "visitor@example.com" in trigger
    assert "25_34" in trigger
