
from fasthtml.common import *
import asyncio
import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv
import websockets

load_dotenv()


def _configure_logging() -> None:
    """Uvicorn installs handlers before app import; tune root level so DEBUG is visible when requested."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    root.setLevel(level)


_configure_logging()
logger = logging.getLogger(__name__)

WAGTAIL_PARAMS: dict[str, str] = {"format": "json", "tags": "moreoptimism"}
WAGTAIL_PAGE_SIZE = 20

WS_PING_INTERVAL = 15
GRID_COLS = 4
GRID_ROWS = 12
GRID_SIZE = GRID_COLS * GRID_ROWS
WS_RECONNECT_BASE = 5
WS_RECONNECT_MAX = 60

WAGTAIL_API_BASE = os.environ.get("WAGTAIL_API_BASE", "").strip()
WS_HOST = os.environ.get("WS_HOST", "").strip()

mobile_shell_css = Style(NotStr("""
html { -webkit-text-size-adjust: 100%; }
*, *::before, *::after { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100dvh;
  min-height: -webkit-fill-available;
}
.mo-shell {
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
"""))

tlink = Script(src="https://cdn.tailwindcss.com")
dlink = Link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/daisyui@4.11.1/dist/full.min.css")


def make_thumbnail_url(download_url: str, size: str = "165x165") -> str:
    """Convert Wagtail original_images URL to a resized variant."""
    url = download_url.replace("/original_images/", "/images/")
    stem, ext = url.rsplit(".", 1)
    return f"{stem}.max-{size}.{ext}"


def _item_download_url(item: dict[str, Any]) -> str:
    if "download_url" in item:
        return str(item["download_url"])
    meta = item.get("meta") or {}
    return str(meta["download_url"])


async def fetch_all_images(
    *,
    base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """Fetch every Wagtail image page into module-shaped dicts."""
    api_base = (base_url or WAGTAIL_API_BASE).strip()
    if not api_base:
        logger.warning("WAGTAIL_API_BASE is empty; skipping image fetch")
        return []

    close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)

    out: list[dict] = []
    offset = 0

    try:
        while True:
            try:
                params = {**WAGTAIL_PARAMS, "offset": offset}
                response = await client.get(api_base, params=params)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError:
                logger.exception("Wagtail image request failed for offset %s", offset)
                raise

            total_count = int(data["meta"]["total_count"])
            for item in data["items"]:
                download_url = _item_download_url(item)
                out.append(
                    {
                        "id": int(item["id"]),
                        "title": str(item["title"]),
                        "thumbnail_url": make_thumbnail_url(download_url),
                    }
                )

            offset += WAGTAIL_PAGE_SIZE
            if offset >= total_count:
                break

        logger.debug("Fetched %s images", len(out))
        return out
    finally:
        if close_client:
            await client.aclose()


images: list[dict] = []
ws_connection: Any | None = None
ws_manager_task: asyncio.Task | None = None
ws_should_stop = False


def _ws_is_connected() -> bool:
    if ws_connection is None:
        return False
    closed = getattr(ws_connection, "closed", False)
    return not bool(closed)


async def _load_images_at_startup() -> None:
    global images
    images = await fetch_all_images()


async def _ws_ping_loop(conn: Any) -> None:
    while True:
        await asyncio.sleep(WS_PING_INTERVAL)
        pong_waiter = await conn.ping()
        await pong_waiter
        logger.debug("WS pong received")


async def _ws_receive_loop(conn: Any) -> None:
    async for message in conn:
        logger.debug("Server: %s", message)


async def _run_ws_connection_once() -> None:
    global ws_connection
    async with websockets.connect(WS_HOST) as conn:
        ws_connection = conn
        logger.info("Connected to TouchDesigner websocket at %s", WS_HOST)

        ping_task = asyncio.create_task(_ws_ping_loop(conn))
        recv_task = asyncio.create_task(_ws_receive_loop(conn))
        done, pending = await asyncio.wait(
            {ping_task, recv_task},
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        for task in done:
            exc = task.exception()
            if exc:
                raise exc


async def _ws_manager_loop() -> None:
    global ws_connection
    backoff = WS_RECONNECT_BASE

    while not ws_should_stop:
        try:
            await _run_ws_connection_once()
            backoff = WS_RECONNECT_BASE
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            ws_connection = None
            if ws_should_stop:
                break
            logger.warning(
                "Websocket disconnected (%s). Reconnecting in %ss",
                exc.__class__.__name__,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, WS_RECONNECT_MAX)


async def _start_ws_client() -> None:
    global ws_manager_task, ws_should_stop
    ws_should_stop = False
    if not WS_HOST:
        logger.warning("WS_HOST is empty; websocket client not started")
        return
    ws_manager_task = asyncio.create_task(_ws_manager_loop())


async def _stop_ws_client() -> None:
    global ws_manager_task, ws_connection, ws_should_stop
    ws_should_stop = True

    if ws_manager_task:
        ws_manager_task.cancel()
        await asyncio.gather(ws_manager_task, return_exceptions=True)
        ws_manager_task = None

    if ws_connection:
        await ws_connection.close()
        ws_connection = None


app = FastHTML(
    hdrs=(mobile_shell_css, tlink, dlink, picolink),
    on_startup=(_load_images_at_startup, _start_ws_client),
    on_shutdown=_stop_ws_client,
)


def _image_grid_cells() -> tuple[Any, ...]:
    """Build GRID_SIZE slot widgets: thumbnail buttons plus empty placeholders."""
    displayed = images[:GRID_SIZE]
    cells: list[Any] = []
    btn_style = (
        "aspect-ratio: 1; width: 100%; min-width: 0; min-height: 44px; padding: 0; border: none; "
        "border-radius: 4px; cursor: pointer; background-size: cover; background-position: center; "
        "background-color: var(--color-background-secondary, #eee); "
        "-webkit-tap-highlight-color: transparent; touch-action: manipulation;"
    )
    for img in displayed:
        iid = img["id"]
        thumb = img["thumbnail_url"]
        cells.append(
            Button(
                id=f"button_{iid}",
                type="button",
                title=str(img["title"]),
                style=f'{btn_style} background-image: url("{thumb}");',
                hx_post=f"/press/{iid}",
                hx_swap="none",
            )
        )
    while len(cells) < GRID_SIZE:
        cells.append(Div(style="aspect-ratio: 1; min-width: 0; min-height: 0;"))
    return tuple(cells)


def ws_status_badge() -> Any:
    connected = _ws_is_connected()
    label = "WS connected" if connected else "WS disconnected"
    color = "#1d9e75" if connected else "#d85a30"
    return Span(
        label,
        id="ws-status",
        title="Tap to reconnect websocket",
        hx_get="/status",
        hx_post="/reconnect",
        hx_trigger="load, every 3s",
        hx_target="#ws-status",
        hx_swap="outerHTML",
        style=(
            "display: inline-flex; align-items: center; justify-content: center; "
            "padding: 0.2rem 0.55rem; border-radius: 999px; font-size: 11px; "
            f"font-weight: 600; letter-spacing: 0.02em; color: white; background: {color}; "
            "cursor: pointer; user-select: none; -webkit-tap-highlight-color: transparent;"
        ),
    )


def layout():
    n_show = min(len(images), GRID_SIZE)
    shell_style = (
        "display: flex; flex-direction: column; gap: clamp(1rem, 3vw, 2.5rem); "
        "width: 100%; max-width: 100%; min-width: 0; margin: 0 auto; "
        "padding: max(12px, env(safe-area-inset-top)) max(16px, env(safe-area-inset-right)) "
        "max(20px, env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left));"
    )
    card_pad = "clamp(12px, 3vw, 16px)"
    grid_gap = "clamp(3px, 1.5vw, 8px)"
    return Div(
    Div(
        Div(
            Div(
                Span(
                    'All images',
                    style='font-size: clamp(12px, 3.5vw, 14px); color: var(--color-text-secondary);',
                ),
                Span(
                    f'{n_show} shown (max {GRID_SIZE})',
                    style='font-size: clamp(11px, 3vw, 13px); color: var(--color-text-tertiary);',
                ),
                ws_status_badge(),
                style='display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;',
            ),
            Div(
                *_image_grid_cells(),
                style=(
                    f'display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); '
                    f'gap: {grid_gap}; width: 100%; min-width: 0;'
                ),
            ),
            Div(
                Span(
                    'tap any thumbnail to send',
                    style='font-size: clamp(10px, 2.8vw, 12px); color: var(--color-text-tertiary);',
                ),
                style='margin-top: 12px; text-align: center;',
            ),
            style=(
                f'background: var(--color-background-secondary); border-radius: var(--border-radius-lg); '
                f'padding: {card_pad}; overflow: hidden; width: 100%; max-width: 100%; min-width: 0;'
            ),
        )
    ),
    cls='mo-shell',
    style=shell_style,
)


# The main screen
@app.route("/")
def get():
    page = Body(
        H1(
            'More Optimism',
            style=(
                'margin: 0 0 0.25rem; font-size: clamp(1.35rem, 5.5vw, 1.85rem); '
                'font-weight: 600; line-height: 1.2; text-align: center;'
            ),
        ),
        layout(),
        style=(
            'margin: 0; min-height: 100dvh; min-height: -webkit-fill-available; '
            'background: var(--pico-background-color, Canvas); color: var(--pico-color, CanvasText);'
        ),
    )
    return Title('More Optimism'), page


@app.route("/status")
def status():
    return ws_status_badge()


@app.route("/reconnect")
async def reconnect():
    if not WS_HOST:
        logger.warning("Reconnect requested but WS_HOST is empty")
        return ws_status_badge()
    logger.info("Manual websocket reconnect requested")
    await _stop_ws_client()
    await _start_ws_client()
    return ws_status_badge()


@app.route("/press/{image_id}")
async def post(image_id: int):
    """Send pressed image id to TouchDesigner over outbound websocket."""
    global ws_connection
    if ws_connection is None:
        logger.warning("Cannot send image %s: websocket not connected", image_id)
        return ""
    try:
        await ws_connection.send(str(image_id))
        logger.debug("Sent to TouchDesigner: %s", image_id)
    except Exception:
        ws_connection = None
        logger.exception("Failed sending image %s over websocket", image_id)
        return ""
    return ""


def main() -> None:
    _configure_logging()

if __name__ == '__main__':
    uvicorn.run("main:app", host='0.0.0.0', port=8001, reload=True)
