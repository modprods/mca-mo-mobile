import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_READ_EXCEL_PATH = Path(__file__).resolve().parents[1] / "read-excel.py"
_SPEC = importlib.util.spec_from_file_location("read_excel", _READ_EXCEL_PATH)
assert _SPEC and _SPEC.loader
read_excel = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(read_excel)


@pytest.mark.asyncio
async def test_read_excel_run_writes_csv(capsys: pytest.CaptureFixture[str]) -> None:
    rows = [["25-34", True, "visitor@example.com", False]]
    with patch.object(read_excel, "fetch_sharepoint_table_rows", AsyncMock(return_value=rows)):
        exit_code = await read_excel.run()

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "age,send_screenshot,email,send_further_emails" in out
    assert "25-34,True,visitor@example.com,False" in out


@pytest.mark.asyncio
async def test_read_excel_run_returns_error_on_failure() -> None:
    with patch.object(
        read_excel,
        "fetch_sharepoint_table_rows",
        AsyncMock(side_effect=ValueError("SITE_ID is empty")),
    ):
        exit_code = await read_excel.run()

    assert exit_code == 1
