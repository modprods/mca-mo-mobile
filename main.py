
from fasthtml.common import *
import asyncio
import logging
import os
import re
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
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

AGE_OPTIONS: list[tuple[str, str]] = [
    ("under_16", "Under 16"),
    ("16_24", "16-24"),
    ("25_34", "25-34"),
    ("35_44", "35-44"),
    ("45_54", "45-54"),
    ("65_plus", "65+"),
    ("prefer_not_to_share", "Prefer not to share"),
]

WAGTAIL_API_BASE = os.environ.get("WAGTAIL_API_BASE", "").strip()
AUDIO_PING = os.environ.get("AUDIO_PING", "").strip()
TD_WS_URL = os.environ.get("WS_HOST", "").strip()
SCREENSHOT_URL = os.environ.get("SCREENSHOT_URL", "").strip()
EMAIL_HOST = os.environ.get("EMAIL_HOST", "").strip()
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25") or "25")
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "").strip()
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "").strip()
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "").strip().lower() in {"1", "true", "yes", "on"}
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "").strip().strip("'\"") or EMAIL_HOST_USER

SCREENSHOT_CID = "screenshot"
SNAPSHOT_EMAIL_SUBJECT = "Your Pop-timism screenshot"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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


def is_valid_email(email: str) -> bool:
    """Return True when email looks like a deliverable address."""
    return bool(EMAIL_RE.match(email.strip()))


def parse_sender(sender: str) -> tuple[str, str]:
    """Return RFC From header value and SMTP envelope address."""
    raw = sender.strip().strip("'\"")
    if not raw:
        raise ValueError("EMAIL_SENDER is empty")

    name, addr = parseaddr(raw)
    if addr:
        header = formataddr((name, addr)) if name else addr
        return header, addr

    bracket = re.search(r"<([^<>]+)>", raw)
    if bracket:
        addr = bracket.group(1).strip()
        if not is_valid_email(addr):
            raise ValueError(f"Invalid EMAIL_SENDER address: {addr!r}")
        display = raw[: bracket.start()].strip().strip("'\"")
        header = formataddr((display, addr)) if display else addr
        return header, addr

    if is_valid_email(raw):
        return raw, raw

    raise ValueError(f"Invalid EMAIL_SENDER: {raw!r}")


def _image_subtype(content_type: str) -> str:
    if "/" not in content_type:
        return "png"
    return content_type.split("/", 1)[1].split(";", 1)[0].strip() or "png"


def build_snapshot_email(
    *,
    to_email: str,
    image_bytes: bytes,
    content_type: str = "image/png",
    from_email: str | None = None,
) -> MIMEMultipart:
    """Build a related MIME message with inline screenshot referenced by CID."""
    from_header, _ = parse_sender(from_email or EMAIL_SENDER)
    html = (
        "<html><body>"
        "<p>Thank you for visiting Pop-timism.</p>"
        f'<p><img src="cid:{SCREENSHOT_CID}" alt="Pop-timism screenshot"></p>'
        '<p>Pop-timism was designed and created by <a href="https://mod.studio">Mod</a> and <a href="https://www.fridalasvegas.com/">Frida Las Vegas</a> in collaboration with the <a href="https://www.mca.com.au">MCA<a/></p>'
        "<p>Experience Design, Software Development and Operations - Mod<br />Visual Design - Frida Las Vegas</p>"
        "<p>This email was send in response to a web form submission on behalf of the <a href='https://www.mca.com.au'>Museum of Contemporary Art Australia</a>.</p>"
        "</body></html>"
    )
    msg = MIMEMultipart("related")
    msg["Subject"] = SNAPSHOT_EMAIL_SUBJECT
    msg["From"] = from_header
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))
    image = MIMEImage(image_bytes, _subtype=_image_subtype(content_type))
    image.add_header("Content-ID", f"<{SCREENSHOT_CID}>")
    image.add_header("Content-Disposition", "inline", filename="pop-timism.png")
    msg.attach(image)
    return msg


async def fetch_snapshot(
    *,
    url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[bytes, str]:
    """Download the latest TouchDesigner snapshot bytes and content type."""
    snapshot_url = (url or SCREENSHOT_URL).strip()
    if not snapshot_url:
        raise ValueError("SCREENSHOT_URL is empty")

    close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        response = await client.get(snapshot_url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/png").split(";", 1)[0].strip()
        if not content_type.startswith("image/"):
            logger.warning("Snapshot content-type is %s; treating as image/png", content_type)
            content_type = "image/png"
        return response.content, content_type
    except httpx.HTTPError:
        logger.exception("Snapshot request failed for %s", snapshot_url)
        raise
    finally:
        if close_client:
            await client.aclose()


def send_email_message(message: MIMEMultipart) -> None:
    """Send a MIME message through the configured SMTP gateway."""
    if not EMAIL_HOST:
        raise ValueError("EMAIL_HOST is empty")

    to_email = str(message["To"]).strip()
    from_header, from_addr = parse_sender(str(message["From"]))
    message.replace_header("From", from_header)

    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=30) as smtp:
        if EMAIL_USE_TLS:
            smtp.starttls()
        if EMAIL_HOST_USER:
            smtp.login(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)
        logger.debug("Sending email from %s to %s", from_addr, to_email)
        smtp.send_message(message, from_addr=from_addr, to_addrs=[to_email])


async def send_snapshot_email(
    to_email: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Fetch the latest snapshot and email it to the visitor."""
    image_bytes, content_type = await fetch_snapshot(client=client)
    message = build_snapshot_email(to_email=to_email, image_bytes=image_bytes, content_type=content_type)
    await asyncio.to_thread(send_email_message, message)
    logger.info("Snapshot email sent to %s", to_email)


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

function revealApp() {{
  const app = document.getElementById("app-content");
  if (app) app.removeAttribute("hidden");
}}

document.body.addEventListener("reveal-app", revealApp);
document.body.addEventListener("htmx:afterSwap", (evt) => {{
  if (!document.getElementById("landing-page")) revealApp();
}});

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
        "aspect-ratio: 1; width: 100%; min-width: 0; min-height: 44px; margin: 0; padding: 0; border: none; "
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


def _field_style() -> str:
    return (
        "width: 100%; min-width: 0; padding: 0.65rem 0.75rem; font-size: 1rem; "
        "border-radius: var(--border-radius, 6px); border: 1px solid var(--pico-muted-border-color, #ccc); "
        "background: var(--pico-background-color, #fff); color: var(--pico-color, inherit);"
    )


def _label_style() -> str:
    return "display: block; margin: 0 0 0.4rem; font-size: 0.95rem; font-weight: 500; line-height: 1.35;"


def landing_form(*, age_error: str = "", email_error: str = "") -> Any:
    """Pre-app landing form shown on first load."""
    card_pad = "clamp(16px, 4vw, 24px)"
    field_gap = "clamp(1rem, 3vw, 1.35rem)"
    age_options = [
        Option("Select your age…", value="", disabled=True, selected=True),
        *[Option(label, value=value) for value, label in AGE_OPTIONS],
    ]
    return Div(
        H1(
            "Pop-timism",
            style=(
                "margin: 0 0 1.25rem; font-size: clamp(1.35rem, 5.5vw, 1.85rem); "
                "font-weight: 600; line-height: 1.2; text-align: center;"
            ),
        ),
        Form(
            Div(
                Label("To begin, tell us your age:", _for="age", style=_label_style()),
                Select(
                    *age_options,
                    name="age",
                    id="age",
                    required=True,
                    aria_invalid="true" if age_error else None,
                    style=_field_style(),
                ),
                P(
                    age_error,
                    style="margin: 0.35rem 0 0; font-size: 0.85rem; color: #c0392b;",
                )
                if age_error
                else "",
                style=f"margin-bottom: {field_gap};",
            ),
            Div(
                Label(
                    "Would you like us to send you a screenshot of your pop-timism creation?",
                    _for="email",
                    style=_label_style(),
                ),
                Input(
                    type="email",
                    name="email",
                    id="email",
                    placeholder="Email (optional)",
                    autocomplete="email",
                    inputmode="email",
                    aria_invalid="true" if email_error else None,
                    style=_field_style(),
                ),
                P(
                    email_error,
                    style="margin: 0.35rem 0 0; font-size: 0.85rem; color: #c0392b;",
                )
                if email_error
                else "",
                style=f"margin-bottom: {field_gap};",
            ),
            Div(
                Label(
                    Input(
                        type="checkbox",
                        name="mca_updates",
                        id="mca_updates",
                        style="margin: 0 0.55rem 0 0; width: 1.1rem; height: 1.1rem; flex-shrink: 0;",
                    ),
                    Span(
                        "Yes, I'd like to receive updates and emails from the "
                        "Museum of Contemporary Art Australia.",
                        style="line-height: 1.35; font-size: 0.9rem;",
                    ),
                    style="display: flex; align-items: flex-start; gap: 0; cursor: pointer;",
                ),
                style=f"margin-bottom: {field_gap};",
            ),
            Button(
                "Start",
                type="submit",
                style=(
                    "width: 100%; margin-top: 0.25rem; padding: 0.75rem 1rem; font-size: 1rem; "
                    "font-weight: 600; border: none; border-radius: var(--border-radius, 6px); "
                    "background: #1d9e75; color: white; cursor: pointer; touch-action: manipulation;"
                ),
            ),
            method="post",
            action="/start",
            hx_post="/start",
            hx_target="#landing-page",
            hx_swap="outerHTML",
            style="display: flex; flex-direction: column; gap: 0;",
        ),
        id="landing-page",
        style=(
            f"background: var(--color-background-secondary, #f4f4f5); "
            f"border-radius: var(--border-radius-lg, 12px); padding: {card_pad}; "
            "width: 100%; max-width: 100%; min-width: 0;"
        ),
    )


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
                    'Tap an image to send',
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


def _shell_style() -> str:
    return (
        "display: flex; flex-direction: column; gap: clamp(1rem, 3vw, 2.5rem); "
        "width: 100%; max-width: 100%; min-width: 0; margin: 0 auto; "
        "padding: max(12px, env(safe-area-inset-top)) max(16px, env(safe-area-inset-right)) "
        "max(20px, env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left));"
    )


def _body_style() -> str:
    return (
        "margin: 0; min-height: 100dvh; min-height: -webkit-fill-available; "
        "background: var(--pico-background-color, Canvas); color: var(--pico-color, CanvasText);"
    )


def _app_heading() -> Any:
    return H1(
        "Pop-timism",
        style=(
            "margin: 0 0 0.25rem; font-size: clamp(1.35rem, 5.5vw, 1.85rem); "
            "font-weight: 600; line-height: 1.2; text-align: center;"
        ),
    )


def _app_content(*, hidden: bool = False) -> Any:
    return Div(
        _app_heading(),
        layout(),
        id="app-content",
        hidden=hidden,
    )


# The main screen
@app.route("/")
def get():
    page = Body(
        Div(
            landing_form(),
            _app_content(hidden=True),
            _td_ws_script(),
            cls="mo-shell",
            style=_shell_style(),
        ),
        style=_body_style(),
    )
    return Title("Pop-timism"), page


@app.route("/start", methods=["POST"])
async def start(req):
    form = await req.form()
    age = str(form.get("age", "")).strip()
    email = str(form.get("email", "")).strip()
    mca_updates = form.get("mca_updates") == "on"

    if not age:
        logger.info("Landing form rejected: missing age")
        return landing_form(age_error="Please select your age.")

    if email and not is_valid_email(email):
        logger.info("Landing form rejected: invalid email %s", email)
        return landing_form(email_error="Please enter a valid email address.")

    logger.info(
        "Landing form submitted: age=%s email=%s mca_updates=%s",
        age,
        email or "(none)",
        mca_updates,
    )

    if email:
        try:
            await send_snapshot_email(email)
        except (httpx.HTTPError, OSError, smtplib.SMTPException, ValueError):
            logger.exception("Failed to send snapshot email to %s", email)
            return landing_form(
                email_error="We could not send your screenshot. Please try again.",
            )

    return "", HtmxResponseHeaders(trigger="reveal-app")



def main() -> None:
    _configure_logging()

if __name__ == '__main__':
    uvicorn.run("main:app", host='0.0.0.0', port=8001, reload=True)
