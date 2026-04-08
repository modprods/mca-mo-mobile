# moreoptimism — Cursor Spec

## Context

FastHTML app managed by uv. Pulls image data from a Wagtail CMS API, renders a tile grid of thumbnail buttons. Pressing a button sends the image ID over a websocket connection to a TouchDesigner installation on the LAN.

Stack: python-fasthtml, httpx, websockets, pytest. Python >=3.12. Managed by uv.

Reference repos for style conventions:
- https://github.com/michela/fastsnake (project structure, pyproject.toml, main.py pattern)
- https://github.com/AnswerDotAI/fasthtml-example/blob/main/02_chatbot/ws.py (FastHTML ws syntax — NOTE: this example uses FastHTML's built-in ws *server*. Our app uses the `websockets` library as a *client* to connect outbound to TouchDesigner. Do NOT use FastHTML's `exts='ws'` for the TouchDesigner connection.)

## Files

```
moreoptimism/
├── main.py              # FastHTML app entry point (update)
├── pyproject.toml       # uv project config (update)
├── .python-version      # pin to 3.12 
├── .cursorrules         # project conventions 
├── README.md            # quickstart docs
└── tests/
    └── test_images.py   # pytest tests (update)
```

## pyproject.toml

```toml
[project]
name = "moreoptimism"
version = "0.1.0"
description = "FastHTML image grid controller for TouchDesigner installation"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "python-fasthtml>=0.12.50",
    "httpx>=0.27",
    "websockets>=13.0",
    "monsterui>=1.0.45",
    "python-dotenv>=1.2.2"
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]
```

## main.py

### Environment variables

Update .env if these do not exist.

WS_HOST = "ws://<IP>:<PORT>"  # TouchDesigner websocket (LAN, no TLS)
WAGTAIL_API_BASE = "https://<HOST>/api/v2/images/"

### Constants

```python

WAGTAIL_PARAMS = {"format": "json", "tags": "moreoptimism"}
WAGTAIL_PAGE_SIZE = 20  # API returns 20 items per page

WS_PING_INTERVAL = 15  # seconds

GRID_COLS = 4
GRID_ROWS = 12
```

### Feature 1: Populate image data

On app startup, fetch all images from the Wagtail API.

- Call `GET {WAGTAIL_API_BASE}?format=json&tags=moreoptimism&offset=0`
- Response contains `items` array and `meta.total_count`
- While `offset < total_count`, increment offset by `WAGTAIL_PAGE_SIZE` and fetch next page
- Store results in a module-level `list[dict]` called `images`
- Each dict should contain at minimum: `id` (int), `title` (str), `thumbnail_url` (str)

**URL transform rule** for `thumbnail_url`:

The API returns a `download_url` like:
`https://d1pxeqjdb63hyy.cloudfront.net/media/original_images/image0.png`

Transform to thumbnail by:
1. Replace `/original_images/` with `/images/`
2. Insert `.max-165x165` before the file extension

Result: `https://d1pxeqjdb63hyy.cloudfront.net/media/images/image0.max-165x165.png`

Implement as a pure function:
```python
def make_thumbnail_url(download_url: str, size: str = "165x165") -> str:
    """Convert Wagtail original_images URL to a resized variant."""
    url = download_url.replace("/original_images/", "/images/")
    stem, ext = url.rsplit(".", 1)
    return f"{stem}.max-{size}.{ext}"
```

### Feature 2: Tile layout

The `GET /` route returns a 4-column × 12-row grid of image buttons.

- Use CSS Grid: `display: grid; grid-template-columns: repeat(4, 1fr);`
- Each cell is a `<button>` with:
  - `id="button_{image_id}"` (e.g., `button_591`)
  - Background image set to the `thumbnail_url` via inline style
  - `onclick="sendId(this.id)"` to trigger the client-side websocket send
- If fewer than 48 images, leave remaining cells empty
- If more than 48 images, only display the first 48

### Feature 3: Client-side websocket (browser to TouchDesigner)

All websocket logic runs in the browser via a `<script>` block served by FastHTML. No server-side websocket code.

Include this JavaScript in the page via a `Script()` component:

```javascript
const TD_WS_URL = "{TD_WS_URL}";
let ws;

function connectWS() {
    ws = new WebSocket(TD_WS_URL);
    ws.onopen = () => console.debug("TD connected");
    ws.onclose = () => {
        console.debug("TD disconnected, reconnecting...");
        setTimeout(connectWS, 3000);
    };
    ws.onerror = (e) => console.error("TD websocket error:", e);
    ws.onmessage = (e) => console.debug("Server:", e.data);
}

function sendId(buttonId) {
    const id = buttonId.replace("button_", "");
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(id);
        console.debug("Sent:", id);
    } else {
        console.warn("WS not connected");
    }
}

connectWS();
```

Note: The `TD_WS_URL` value must be injected from the Python constant into the JS string. Use an f-string or `.replace()` when constructing the Script() component.

### Feature 4: Button handler

Handled entirely client-side. Each button's `onclick="sendId(this.id)"` calls the JS function above, which:

1. Strips `button_` prefix from the button ID
2. Sends the numeric ID as a plain text websocket message directly to TouchDesigner

No server-side route needed for button presses.

### Feature 5. Websocket connection status

Poll every 3s to check if the websocket connection is valid.

If so, show "Connected"

If not, change the button status to "Reconnect"

No server-side websocket code — all websocket communication is browser-to-TouchDesigner

### Feature 6. Message debounce

Debounce on the browser side. If someone taps rapidly, don't send every press. Add a cooldown to the JS so it drops messages within a window:

```
let lastSend = 0;
const DEBOUNCE_MS = 100;

function sendId(buttonId) {
    const now = Date.now();
    if (now - lastSend < DEBOUNCE_MS) return;
    lastSend = now;
    const id = buttonId.replace("button_", "");
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(id);
    }
}
```

### Feature 6. Audio on button press

Play AUDIO_PING URL sound when button pressed

## Tests (tests/test_images.py)

Mock the Wagtail API using `pytest` fixtures (do NOT hit the live API).

Create a fixture that returns a realistic multi-page API response totalling 50 images.

```python
def test_image_count(mock_api_response):
    """Total images fetched should be 50."""
    images = fetch_all_images()
    assert len(images) == 50

def test_last_image_id(mock_api_response):
    """Last image in the list should have id 638."""
    images = fetch_all_images()
    assert images[-1]["id"] == 638

def test_thumbnail_url_transform():
    """URL transform converts original_images path to sized variant."""
    original = "https://d1pxeqjdb63hyy.cloudfront.net/media/original_images/image0.png"
    expected = "https://d1pxeqjdb63hyy.cloudfront.net/media/images/image0.max-165x165.png"
    assert make_thumbnail_url(original) == expected
```

## Constraints

- Do NOT use FastHTML's `exts='ws'` or `ws_send` for the TouchDesigner connection
- Do NOT use `requests` library — use `httpx`
- Do NOT add authentication or CORS middleware
- Do NOT modify the Wagtail API response shape
- Keep everything in `main.py` for now (no separate modules beyond tests)

