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
├── main.py              # FastHTML app entry point (create)
├── pyproject.toml       # uv project config (create)
├── .python-version      # pin to 3.12 (create)
├── .cursorrules         # project conventions (create)
├── README.md            # quickstart docs (create)
└── tests/
    └── test_images.py   # pytest tests (create)
```

## .cursorrules

Create `.cursorrules` at project root with these constraints:
- Use `from fasthtml.common import *` as the single FastHTML import
- Use `httpx` for HTTP requests, never `requests`
- Use `websockets` library for outbound websocket client, not FastHTML ws extension
- Use `logging` module, not print statements
- All config values (API base URL, websocket host, grid dimensions) as module-level constants
- Python 3.12+, no type: ignore comments

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
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]
```

## main.py

### Constants

```python
WAGTAIL_API_BASE = "https://mod.studio/api/v2/images/"
WAGTAIL_PARAMS = {"format": "json", "tags": "moreoptimism"}
WAGTAIL_PAGE_SIZE = 20  # API returns 20 items per page

WS_HOST = "ws://10.20.15.92:9980"  # TouchDesigner websocket (LAN, no TLS)
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
  - Background image set to the `thumbnail_url`
  - `onclick` triggers an HTMX POST or JS call to send the image ID (see Button handler below)
- If fewer than 48 images, leave remaining cells empty
- If more than 48 images, only display the first 48

### Feature 3: Websocket client (outbound to TouchDesigner)

This is a **client** connection using the `websockets` Python library. NOT FastHTML's built-in ws support.

#### Lifecycle
- On app startup (use Starlette lifespan or `@app.on_event("startup")`), open a persistent websocket connection to `WS_HOST`
- Store the connection in a module-level variable
- On shutdown, close the connection gracefully

#### Ping/pong
- Send a websocket ping every `WS_PING_INTERVAL` seconds (use `websockets` built-in ping, or `asyncio.create_task` with a loop)
- Log pong receipt at DEBUG level: `"WS pong received"`

#### Incoming messages
- Log all incoming server messages at DEBUG level: `f"Server: {message}"`

#### Reconnection
- If the connection drops, retry every 5 seconds with exponential backoff (max 60s)
- Log reconnection attempts at WARNING level

### Feature 4: Button handler

When a user presses a thumbnail button:

1. Extract the numeric image ID from the button's `id` attribute (strip `button_` prefix)
2. Send the ID as a plain text websocket message to TouchDesigner

Implementation options (pick one):
- **Option A (server-side):** HTMX POST to `/press/{image_id}`, handler sends via the stored websocket connection
- **Option B (client-side):** Not applicable here since the websocket client runs server-side

Use Option A. Create route:
```python
@rt("/press/{image_id}")
async def post(image_id: int):
    await ws_connection.send(str(image_id))
    logger.debug(f"Sent to TouchDesigner: {image_id}")
    return ""  # empty 200 response
```

Each button should use: `hx-post="/press/{image_id}" hx-swap="none"`

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

