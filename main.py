
from fasthtml.common import *
import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv

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
GRID_ROWS = 18

WAGTAIL_API_BASE = os.environ.get("WAGTAIL_API_BASE", "").strip()
AUDIO_PING = os.environ.get("AUDIO_PING", "").strip()
TD_WS_URL = os.environ.get("WS_HOST", "").strip()

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


async def _load_images_at_startup() -> None:
    global images
    images = await fetch_all_images()


def _td_ws_script() -> Any:
    ws_url = TD_WS_URL.replace("\\", "\\\\").replace('"', '\\"')
    audio_url = AUDIO_PING.replace("\\", "\\\\").replace('"', '\\"')
    return Script(
        NotStr(
            f"""
const TD_WS_URL = "{ws_url}";
const AUDIO_PING_URL = "{audio_url}";
let ws = null;
let lastSend = 0;
const DEBOUNCE_MS = 100;
const pingAudio = AUDIO_PING_URL ? new Audio(AUDIO_PING_URL) : null;

function setWsBadge(connected) {{
  const el = document.getElementById("ws-status");
  if (!el) return;
  el.textContent = connected ? "Connected" : "Reconnect";
  el.style.background = connected ? "#1d9e75" : "#d85a30";
}}

function isWsConnected() {{
  return Boolean(ws && ws.readyState === WebSocket.OPEN);
}}

function pollWsStatus() {{
  setWsBadge(isWsConnected());
}}

function connectWS() {{
  if (!TD_WS_URL) {{
    console.warn("TD websocket URL is empty");
    pollWsStatus();
    return;
  }}
  ws = new WebSocket(TD_WS_URL);
  ws.onopen = () => {{
    console.debug("TD connected");
    pollWsStatus();
  }};
  ws.onclose = () => {{
    console.debug("TD disconnected, reconnecting...");
    pollWsStatus();
    setTimeout(connectWS, 3000);
  }};
  ws.onerror = (e) => {{
    console.error("TD websocket error:", e);
    pollWsStatus();
  }};
  ws.onmessage = (e) => console.debug("Server:", e.data);
}}

function extractImageId(buttonId) {{
  if (typeof buttonId !== "string" || !buttonId.startsWith("button_")) {{
    return null;
  }}
  const id = buttonId.slice("button_".length);
  return /^\\d+$/.test(id) ? id : null;
}}

function playPing() {{
  if (!pingAudio) return;
  try {{
    pingAudio.currentTime = 0;
    const playPromise = pingAudio.play();
    if (playPromise && typeof playPromise.catch === "function") {{
      playPromise.catch(() => {{}});
    }}
  }} catch (_e) {{
    // Ignore audio playback errors (autoplay policy, unsupported format, etc.)
  }}
}}

function sendId(buttonId) {{
  const id = extractImageId(buttonId);
  if (!id) {{
    console.warn("Invalid button id:", buttonId);
    return;
  }}
  playPing();

  const now = Date.now();
  if (now - lastSend < DEBOUNCE_MS) {{
    return;
  }}
  lastSend = now;
  if (isWsConnected()) {{
    ws.send(id);
    console.debug("Sent:", id);
  }} else {{
    console.warn("WS not connected");
    pollWsStatus();
  }}
}}

function manualReconnect() {{
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {{
    ws.close();
  }} else {{
    connectWS();
  }}
}}

window.sendId = sendId;
window.manualReconnect = manualReconnect;
connectWS();
pollWsStatus();
setInterval(pollWsStatus, 3000);
"""
        )
    )


app = FastHTML(
    hdrs=(mobile_shell_css, tlink, dlink, picolink),
    on_startup=_load_images_at_startup,
)


def _image_grid_cells() -> tuple[Any, ...]:
    """Build one thumbnail button per image."""
    cells: list[Any] = []
    btn_style = (
        "aspect-ratio: 1; width: 100%; min-width: 0; min-height: 44px; padding: 0; border: none; "
        "border-radius: 4px; cursor: pointer; background-size: cover; background-position: center; "
        "background-color: var(--color-background-secondary, #eee); "
        "-webkit-tap-highlight-color: transparent; touch-action: manipulation;"
    )
    for img in images:
        iid = img["id"]
        thumb = img["thumbnail_url"]
        cells.append(
            Button(
                id=f"button_{iid}",
                type="button",
                title=str(img["title"]),
                style=f'{btn_style} background-image: url("{thumb}");',
                onclick="sendId(this.id)",
            )
        )
    return tuple(cells)


def ws_status_badge() -> Any:
    return Span(
        "Reconnect",
        id="ws-status",
        title="Tap to reconnect websocket",
        onclick="manualReconnect()",
        style=(
            "display: inline-flex; align-items: center; justify-content: center; "
            "padding: 0.2rem 0.55rem; border-radius: 999px; font-size: 11px; "
            "font-weight: 600; letter-spacing: 0.02em; color: white; background: #d85a30; "
            "cursor: pointer; user-select: none; -webkit-tap-highlight-color: transparent; "
            "width: fit-content; justify-self: end;"
        ),
    )


def layout():
    n_show = len(images)
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
                    f'',
                    style='font-size: clamp(11px, 3vw, 13px); color: var(--color-text-tertiary);',
                ),
                Span(
                    f'{n_show} artefacts shown',
                    style='font-size: clamp(11px, 3vw, 13px); color: var(--color-text-tertiary);',
                ),
                ws_status_badge(),
                style='display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 8px; margin-bottom: 12px;',
            ),
            Div(
                *_image_grid_cells(),
                style=(
                    f'display: grid; grid-template-columns: repeat({GRID_COLS}, minmax(0, 1fr)); '
                    f'gap: {grid_gap}; width: 100%; min-width: 0; margin: {grid_gap};'
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
        _td_ws_script(),
        style=(
            'margin: 0; min-height: 100dvh; min-height: -webkit-fill-available; '
            'background: var(--pico-background-color, Canvas); color: var(--pico-color, CanvasText);'
        ),
    )
    return Title('More Optimism'), page



def main() -> None:
    _configure_logging()

if __name__ == '__main__':
    uvicorn.run("main:app", host='0.0.0.0', port=8001, reload=True)
