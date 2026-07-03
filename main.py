
from fasthtml.common import *
import asyncio
import csv
import json
import logging
import os
import re
import smtplib
from datetime import UTC, datetime
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
    ("55_64", "55-64"),
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

TENANT_ID = os.environ.get("TENANT_ID", "").strip()
CLIENT_ID = os.environ.get("CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "").strip()
TOKEN_ENDPOINT = os.environ.get("TOKEN_ENDPOINT", "").strip()
GRANT_TYPE = os.environ.get("GRANT_TYPE", "client_credentials").strip()
SCOPE = os.environ.get("SCOPE", "https://graph.microsoft.com/.default").strip()
SHAREPOINT_URL = os.environ.get("SHAREPOINT_URL", "").strip()
SITE_ID = os.environ.get("SITE_ID", "").strip()
WORKBOOK_NAME = os.environ.get("WORKBOOK_NAME", "PoptimismFormSubmissions.xlsx").strip()
WORKBOOK_LOCATION = os.environ.get("LOCATION", "").strip() or WORKBOOK_NAME
TABLE_NAME = os.environ.get("TABLE_NAME", "FormSubmissions").strip()

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
FORM_LOG_PATH = "form.log"
ERRORS_LOG_PATH = "errors.log"
FORM_TABLE_HEADERS = ["age", "send_screenshot", "email", "send_further_emails"]
AGE_LABELS = dict(AGE_OPTIONS)

SCREENSHOT_CID = "screenshot"
SNAPSHOT_EMAIL_SUBJECT = "Your Pop-timism screenshot"
SNAPSHOT_ERROR_MESSAGE = "We could not send your screenshot. Refresh page to try again."
SUBMISSION_ERROR_MESSAGE = "Something went wrong saving your submission. Refresh page to try again."
MCA_LOGO_URL = "https://dhbvezz9j5025.cloudfront.net/productions/mca/img/footer_mca_logo.svg"
MCA_FONT_URL = "https://dhbvezz9j5025.cloudfront.net/productions/mca/fonts/MCASelecta-Regular.otf"
TOAST_DURATION_MS = 6000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MCA_FONT_FACE_CSS = f"""
@font-face {{
  font-family: "MCA Selecta";
  src: url("{MCA_FONT_URL}") format("opentype");
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}}
"""

mobile_shell_css = Style(NotStr(MCA_FONT_FACE_CSS + """
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
#mo-toast-host {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 2000;
  display: flex;
  justify-content: center;
  pointer-events: none;
  padding: max(12px, env(safe-area-inset-top)) 12px 0;
}
#mo-toast {
  pointer-events: auto;
  max-width: min(92vw, 28rem);
  padding: 0.75rem 1rem;
  background: #b42318;
  color: white;
  border-radius: 8px;
  font-size: 0.95rem;
  line-height: 1.35;
  text-align: center;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}
#landing-page {
  background: var(--color-background-secondary, #f4f4f5);
  color: var(--pico-color, CanvasText);
  font-family: "MCA Selecta", sans-serif;
}
#landing-page input,
#landing-page select,
#landing-page button {
  font-family: inherit;
}
#landing-page h1,
#landing-page label {
  color: inherit;
}
#landing-page .landing-field {
  border: 1px solid var(--pico-muted-border-color, #ccc);
  background: var(--pico-background-color, #fff);
  color: var(--pico-color, inherit);
}
#landing-page .landing-start-btn {
  background: #000;
  color: #fff;
}
@media (prefers-color-scheme: dark) {
  #landing-page {
    background: #1e2128;
    color: #e8eaed;
  }
  #landing-page .landing-field {
    background: #32363f;
    color: #e8eaed;
    border-color: #4a515c;
  }
  #landing-page .landing-field::placeholder {
    color: #9aa3ad;
  }
  #landing-page .landing-logo {
    filter: invert(1);
  }
  #landing-page .landing-start-btn {
    background: #fff;
    color: #000;
  }
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


def build_snapshot_email_html() -> str:
    """HTML body for the snapshot email with a responsive inline image."""
    container_style = "max-width: 100%; width: 100%; margin: 0; padding: 0;"
    image_style = (
        "display: block; max-width: 100%; width: 100%; height: auto; "
        "border: 0; outline: none; text-decoration: none; "
        "-ms-interpolation-mode: bicubic;"
    )
    return (
        "<html><body style=\"margin: 0; padding: 0;\">"
        "<p>Thank you for visiting Pop-timism.</p>"
        f'<div style="{container_style}">'
        f'<img src="cid:{SCREENSHOT_CID}" alt="Pop-timism screenshot" style="{image_style}">'
        "</div>"
        '<p>Pop-timism was designed and created by <a href="https://mod.studio">Mod</a> and '
        '<a href="https://www.fridalasvegas.com/">Frida Las Vegas</a> in collaboration with the '
        '<a href="https://www.mca.com.au">MCA<a/></p>'
        "<p>Experience Design, Software Development and Operations by Mod<br />Visual Design by Frida Las Vegas</p>"
        "<p>This email was sent in response to a web form submission on behalf of the "
        "<a href='https://www.mca.com.au'>Museum of Contemporary Art Australia</a>.</p>"
        "</body></html>"
    )


def build_snapshot_email(
    *,
    to_email: str,
    image_bytes: bytes,
    content_type: str = "image/png",
    from_email: str | None = None,
) -> MIMEMultipart:
    """Build a related MIME message with inline screenshot referenced by CID."""
    from_header, _ = parse_sender(from_email or EMAIL_SENDER)
    html = build_snapshot_email_html()
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
        client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    try:
        response = await client.get(snapshot_url, follow_redirects=True)
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


def error_toast(message: str) -> Any:
    """Top-of-screen error toast returned to #mo-toast-host."""
    return Div(message, id="mo-toast")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def log_form_transaction(message: str) -> None:
    with open(FORM_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(f"{_utc_now()} {message}\n")


def log_form_error(message: str) -> None:
    with open(ERRORS_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(f"{_utc_now()} {message}\n")


def form_submission_row_values(*, age: str, email: str, mca_updates: bool) -> list:
    """Build one Excel row: age, send_screenshot, email, send_further_emails."""
    return [
        AGE_LABELS.get(age, age),
        bool(email),
        email,
        mca_updates,
    ]


def _sharepoint_table_base_url() -> str:
    return (
        f"{GRAPH_API_BASE}/sites/{SITE_ID}/drive/root:/{WORKBOOK_LOCATION}:"
        f"/workbook/tables/{TABLE_NAME}"
    )


def sharepoint_rows_url() -> str:
    return f"{_sharepoint_table_base_url()}/rows/add"


def sharepoint_table_rows_url() -> str:
    return f"{_sharepoint_table_base_url()}/rows"


def sharepoint_rows_from_response(data: dict[str, Any]) -> list[list[Any]]:
    """Extract table row value lists from a Graph workbook rows response."""
    rows: list[list[Any]] = []
    for item in data.get("value", []):
        for row in item.get("values", []):
            rows.append(list(row))
    return rows


def write_form_rows_csv(rows: list[list[Any]], out: Any) -> None:
    """Write header and data rows as CSV."""
    writer = csv.writer(out)
    writer.writerow(FORM_TABLE_HEADERS)
    writer.writerows(rows)


async def fetch_graph_access_token(
    client: httpx.AsyncClient,
    *,
    token_endpoint: str | None = None,
) -> str:
    endpoint = (token_endpoint or TOKEN_ENDPOINT).strip()
    if not endpoint and TENANT_ID:
        endpoint = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    if not endpoint:
        raise ValueError("TOKEN_ENDPOINT is empty")
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("SharePoint credentials are not configured")

    response = await client.post(
        endpoint,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": GRANT_TYPE,
            "scope": SCOPE,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.is_error:
        detail = response.text
        try:
            payload = response.json()
            detail = str(payload.get("error_description") or payload.get("error") or detail)
        except ValueError:
            pass
        logger.error("Graph token request failed (%s): %s", response.status_code, detail)
        response.raise_for_status()

    token = response.json().get("access_token")
    if not token:
        raise ValueError("Graph token response missing access_token")
    return str(token)


async def append_sharepoint_row(
    row_values: list,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    if not SITE_ID:
        raise ValueError("SITE_ID is empty")

    close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        token = await fetch_graph_access_token(client)
        response = await client.post(
            sharepoint_rows_url(),
            json={"values": [row_values]},
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        logger.info("SharePoint row appended for age=%s", row_values[0])
    except httpx.HTTPError:
        logger.exception("SharePoint row append failed")
        raise
    finally:
        if close_client:
            await client.aclose()


async def fetch_sharepoint_table_rows(
    *,
    client: httpx.AsyncClient | None = None,
) -> list[list[Any]]:
    """Fetch all rows from the SharePoint FormSubmissions Excel table."""
    if not SITE_ID:
        raise ValueError("SITE_ID is empty")

    close_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        token = await fetch_graph_access_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        url: str | None = sharepoint_table_rows_url()
        rows: list[list[Any]] = []

        while url:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            rows.extend(sharepoint_rows_from_response(data))
            url = data.get("@odata.nextLink")

        logger.debug("Fetched %s SharePoint table rows", len(rows))
        return rows
    except httpx.HTTPError:
        logger.exception("SharePoint table read failed")
        raise
    finally:
        if close_client:
            await client.aclose()


def _start_response_headers(*, age: str, email: str, mca_updates: bool) -> HtmxResponseHeaders:
    """Reveal the app immediately; queue background email and SharePoint logging."""
    trigger = json.dumps(
        {
            "reveal-app": None,
            "process-submission": {
                "age": age,
                "email": email,
                "mca_updates": mca_updates,
            },
        }
    )
    return HtmxResponseHeaders(trigger=trigger)


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

function dismissToastLater() {{
  setTimeout(() => {{
    const host = document.getElementById("mo-toast-host");
    if (host) host.innerHTML = "";
  }}, {TOAST_DURATION_MS});
}}

document.body.addEventListener("reveal-app", revealApp);
document.body.addEventListener("process-submission", (evt) => {{
  const detail = evt.detail || {{}};
  if (!detail.age || !window.htmx) return;
  htmx.ajax("POST", "/process-submission", {{
    target: "#mo-toast-host",
    swap: "innerHTML",
    values: {{
      age: detail.age,
      email: detail.email || "",
      mca_updates: detail.mca_updates ? "on" : "",
    }},
  }});
}});
document.body.addEventListener("htmx:afterSwap", (evt) => {{
  if (!document.getElementById("landing-page")) revealApp();
  if (evt.detail.target?.id === "mo-toast-host" && document.getElementById("mo-toast")) {{
    dismissToastLater();
  }}
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
        "border-radius: var(--border-radius, 6px);"
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
        Img(
            src=MCA_LOGO_URL,
            alt="Museum of Contemporary Art Australia",
            cls="landing-logo",
            style=(
                "display: block; margin: 0 0 1.25rem; "
                "max-width: min(180px, 27.5vw); height: auto;"
            ),
        ),
        H1(
            "Pop-timism",
            style=(
                "margin: 0 0 1.25rem; font-size: clamp(1.35rem, 5.5vw, 1.85rem); "
                "font-weight: 600; line-height: 1.2; text-align: center;"
            ),
        ),
        Form(
            Div(
                P(
                    " The future isn't decided yet, and the best futures aren't predicted – they're imagined.",
                    style=f"margin: 0 0 {field_gap}; line-height: 1.45;",
                ),
                Label("To begin, please tell us your age:", _for="age", style=_label_style()),
                Select(
                    *age_options,
                    name="age",
                    id="age",
                    required=True,
                    cls="landing-field",
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
                    "Would you like us to send you a screenshot of your Pop-timism creation?",
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
                    cls="landing-field",
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
                cls="landing-start-btn",
                style=(
                    "width: 100%; margin-top: 0.25rem; padding: 0.75rem 1rem; font-size: 1rem; "
                    "font-weight: 600; border: none; border-radius: var(--border-radius, 6px); "
                    "cursor: pointer; touch-action: manipulation;"
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


def _toast_host() -> Any:
    return Div(id="mo-toast-host")


# The main screen
@app.route("/")
def get():
    page = Body(
        _toast_host(),
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

    return "", _start_response_headers(age=age, email=email, mca_updates=mca_updates)


@app.route("/process-submission", methods=["POST"])
async def process_submission(req):
    form = await req.form()
    age = str(form.get("age", "")).strip()
    email = str(form.get("email", "")).strip()
    mca_updates = form.get("mca_updates") == "on"

    if not age:
        log_form_error("process-submission rejected: missing age")
        return error_toast(SUBMISSION_ERROR_MESSAGE)

    if email and not is_valid_email(email):
        log_form_error(f"process-submission rejected: invalid email {email}")
        return error_toast(SNAPSHOT_ERROR_MESSAGE)

    email_error = False

    if email:
        try:
            await send_snapshot_email(email)
        except (httpx.HTTPError, OSError, smtplib.SMTPException, ValueError) as exc:
            logger.exception("Failed to send snapshot email to %s", email)
            log_form_error(f"email failed to {email}: {exc}")
            email_error = True

    row_values = form_submission_row_values(age=age, email=email, mca_updates=mca_updates)
    try:
        await append_sharepoint_row(row_values)
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("Failed to append SharePoint row for age=%s", age)
        log_form_error(
            f"sharepoint failed age={row_values[0]!r} email={email or '(none)'}: {exc}"
        )
        return error_toast(SUBMISSION_ERROR_MESSAGE)

    log_form_transaction(
        f"age={row_values[0]!r} send_screenshot={row_values[1]} email={email or '(none)'!r} "
        f"send_further_emails={row_values[3]}"
    )

    if email_error:
        return error_toast(SNAPSHOT_ERROR_MESSAGE)

    return ""



def main() -> None:
    _configure_logging()

if __name__ == '__main__':
    uvicorn.run("main:app", host='0.0.0.0', port=8001, reload=True)
