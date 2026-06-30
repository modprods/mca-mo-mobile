"""Read SharePoint form submissions and write each row as CSV to STDOUT."""

import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from main import fetch_sharepoint_table_rows, write_form_rows_csv


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def run() -> int:
    try:
        rows = await fetch_sharepoint_table_rows()
    except Exception:
        logging.exception("Failed to read SharePoint workbook rows")
        return 1

    write_form_rows_csv(rows, sys.stdout)
    return 0


def main() -> None:
    _configure_logging()
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
