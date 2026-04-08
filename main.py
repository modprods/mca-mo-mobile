
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
GRID_ROWS = 12
GRID_SIZE = GRID_COLS * GRID_ROWS

WAGTAIL_API_BASE = os.environ.get("WAGTAIL_API_BASE", "").strip()

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


app = FastHTML(
    hdrs=(mobile_shell_css, tlink, dlink, picolink),
    on_startup=_load_images_at_startup,
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
                style='display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 12px;',
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


@app.route("/press/{image_id}")
async def post(image_id: int):
    """HTMX target; TouchDesigner send is wired in Feature 4."""
    logger.debug("Thumbnail press: %s (websocket client not connected yet)", image_id)
    return ""


def main() -> None:
    _configure_logging()

if __name__ == '__main__':
    uvicorn.run("main:app", host='0.0.0.0', port=8001, reload=True)
