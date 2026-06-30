from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from starlette.testclient import TestClient

import main
from main import (
    append_sharepoint_row,
    fetch_graph_access_token,
    fetch_sharepoint_table_rows,
    form_submission_row_values,
    sharepoint_rows_from_response,
    sharepoint_rows_url,
    sharepoint_table_rows_url,
    write_form_rows_csv,
)


def test_form_submission_row_values() -> None:
    row = form_submission_row_values(
        age="25_34",
        email="visitor@example.com",
        mca_updates=True,
    )
    assert row == ["25-34", True, "visitor@example.com", True]


def test_sharepoint_rows_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "SITE_ID", "site-123")
    monkeypatch.setattr(main, "WORKBOOK_LOCATION", "Documents/PoptimismFormSubmissions.xlsx")
    monkeypatch.setattr(main, "TABLE_NAME", "FormSubmissions")
    assert sharepoint_rows_url().endswith("/workbook/tables/FormSubmissions/rows/add")
    assert sharepoint_table_rows_url().endswith("/workbook/tables/FormSubmissions/rows")


def test_sharepoint_rows_from_response() -> None:
    data = {
        "value": [
            {"index": 0, "values": [["25-34", True, "a@example.com", False]]},
            {"index": 1, "values": [["16-24", False, "", True]]},
        ]
    }
    assert sharepoint_rows_from_response(data) == [
        ["25-34", True, "a@example.com", False],
        ["16-24", False, "", True],
    ]


def test_write_form_rows_csv() -> None:
    import io

    buf = io.StringIO()
    write_form_rows_csv([["25-34", True, "a@example.com", False]], buf)
    assert buf.getvalue() == "age,send_screenshot,email,send_further_emails\r\n25-34,True,a@example.com,False\r\n"


@pytest.mark.asyncio
async def test_fetch_graph_access_token() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"access_token": "token-abc"})

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    token = await fetch_graph_access_token(
        mock_client,
        token_endpoint="https://login.example.test/token",
    )

    assert token == "token-abc"
    mock_client.post.assert_awaited_once()
    call = mock_client.post.await_args
    assert call.args[0] == "https://login.example.test/token"
    assert call.kwargs["data"]["grant_type"] == "client_credentials"


@pytest.mark.asyncio
async def test_append_sharepoint_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "SITE_ID", "site-123")
    monkeypatch.setattr(main, "WORKBOOK_LOCATION", "PoptimismFormSubmissions.xlsx")
    monkeypatch.setattr(main, "TABLE_NAME", "FormSubmissions")

    token_response = MagicMock()
    token_response.raise_for_status = MagicMock()
    token_response.json = MagicMock(return_value={"access_token": "token-abc"})

    row_response = MagicMock()
    row_response.raise_for_status = MagicMock()

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=[token_response, row_response])

    row = form_submission_row_values(age="16_24", email="", mca_updates=False)
    await append_sharepoint_row(row, client=mock_client)

    assert mock_client.post.await_count == 2
    row_call = mock_client.post.await_args_list[1]
    assert row_call.kwargs["json"] == {"values": [row]}
    assert row_call.kwargs["headers"]["Authorization"] == "Bearer token-abc"


@pytest.mark.asyncio
async def test_fetch_sharepoint_table_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "SITE_ID", "site-123")
    monkeypatch.setattr(main, "WORKBOOK_LOCATION", "PoptimismFormSubmissions.xlsx")
    monkeypatch.setattr(main, "TABLE_NAME", "FormSubmissions")

    token_response = MagicMock()
    token_response.raise_for_status = MagicMock()
    token_response.json = MagicMock(return_value={"access_token": "token-abc"})

    rows_response = MagicMock()
    rows_response.raise_for_status = MagicMock()
    rows_response.json = MagicMock(
        return_value={
            "value": [{"index": 0, "values": [["25-34", True, "a@example.com", False]]}],
        }
    )

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=token_response)
    mock_client.get = AsyncMock(return_value=rows_response)

    rows = await fetch_sharepoint_table_rows(client=mock_client)

    assert rows == [["25-34", True, "a@example.com", False]]
    mock_client.get.assert_awaited_once()
    get_call = mock_client.get.await_args
    assert get_call.args[0].endswith("/workbook/tables/FormSubmissions/rows")
    assert get_call.kwargs["headers"]["Authorization"] == "Bearer token-abc"


def test_process_submission_logs_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    form_log = tmp_path / "form.log"
    errors_log = tmp_path / "errors.log"
    monkeypatch.setattr(main, "FORM_LOG_PATH", str(form_log))
    monkeypatch.setattr(main, "ERRORS_LOG_PATH", str(errors_log))
    monkeypatch.setattr(main, "send_snapshot_email", AsyncMock())
    monkeypatch.setattr(main, "append_sharepoint_row", AsyncMock())

    client = TestClient(main.app)
    response = client.post(
        "/process-submission",
        data={"age": "25_34", "email": "visitor@example.com", "mca_updates": "on"},
    )

    assert response.status_code == 200
    assert response.text == ""
    assert form_log.read_text(encoding="utf-8")
    assert "25-34" in form_log.read_text(encoding="utf-8")
    assert not errors_log.exists()


def test_process_submission_email_failure_logs_error_and_toasts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    form_log = tmp_path / "form.log"
    errors_log = tmp_path / "errors.log"
    monkeypatch.setattr(main, "FORM_LOG_PATH", str(form_log))
    monkeypatch.setattr(main, "ERRORS_LOG_PATH", str(errors_log))
    monkeypatch.setattr(
        main,
        "send_snapshot_email",
        AsyncMock(side_effect=httpx.HTTPError("smtp down")),
    )
    monkeypatch.setattr(main, "append_sharepoint_row", AsyncMock())

    client = TestClient(main.app)
    response = client.post(
        "/process-submission",
        data={"age": "25_34", "email": "visitor@example.com"},
    )

    assert main.SNAPSHOT_ERROR_MESSAGE in response.text
    assert "email failed" in errors_log.read_text(encoding="utf-8")
    assert form_log.read_text(encoding="utf-8")


def test_process_submission_sharepoint_failure_logs_error_and_toasts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    errors_log = tmp_path / "errors.log"
    monkeypatch.setattr(main, "ERRORS_LOG_PATH", str(errors_log))
    monkeypatch.setattr(main, "append_sharepoint_row", AsyncMock(side_effect=ValueError("no site")))

    client = TestClient(main.app)
    response = client.post("/process-submission", data={"age": "25_34"})

    assert main.SUBMISSION_ERROR_MESSAGE in response.text
    assert "sharepoint failed" in errors_log.read_text(encoding="utf-8")


def test_start_always_queues_process_submission() -> None:
    client = TestClient(main.app)
    response = client.post("/start", data={"age": "25_34", "mca_updates": "on"})
    trigger = response.headers.get("hx-trigger", "")
    assert "reveal-app" in trigger
    assert "process-submission" in trigger
    assert "25_34" in trigger
