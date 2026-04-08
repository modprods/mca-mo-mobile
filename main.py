
from fasthtml.common import *
import asyncio

# Set up the app, including daisyui and tailwind for the chat component
tlink = Script(src="https://cdn.tailwindcss.com")
dlink = Link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/daisyui@4.11.1/dist/full.min.css")
app = FastHTML(hdrs=(tlink, dlink, picolink), exts='ws')

images = []

def layout():
    return Div(
    Div(
        Div(
            Div(
                Span('All artifacts', style='font-size: 13px; color: var(--color-text-secondary);'),
                Span('48 available', style='font-size: 12px; color: var(--color-text-tertiary);'),
                style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;'
            ),
            Div(
                Div(
                    Div(style='position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: #534AB7; border-radius: 0 0 4px 4px;'),
                    style='aspect-ratio: 1; background: #7F77DD; border-radius: 4px; position: relative;'
                ),
                Div(style='aspect-ratio: 1; background: #5DCAA5; border-radius: 4px;'),
                Div(style='aspect-ratio: 1; background: #D85A30; border-radius: 4px;'),
                Div(style='aspect-ratio: 1; background: #378ADD; border-radius: 4px;'),
                Div(style='aspect-ratio: 1; background: #ED93B1; border-radius: 4px;'),
                Div(style='aspect-ratio: 1; background: #EF9F27; border-radius: 4px;'),
                Div(style='aspect-ratio: 1; background: #97C459; border-radius: 4px;'),
                Div(style='aspect-ratio: 1; background: #B4B2A9; border-radius: 4px;'),
                Div(style='aspect-ratio: 1; background: #85B7EB; border-radius: 4px;'),
                Div(style='aspect-ratio: 1; background: #AFA9EC; border-radius: 4px;'),
                Div(style='aspect-ratio: 1; background: #F0997B; border-radius: 4px;'),
                Div(style='aspect-ratio: 1; background: #1D9E75; border-radius: 4px;'),
                style='display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px;'
            ),
            Div(
                Span('tap any thumbnail to send', style='font-size: 11px; color: var(--color-text-tertiary);'),
                style='margin-top: 12px; text-align: center;'
            ),
            style='background: var(--color-background-secondary); border-radius: var(--border-radius-lg); padding: 16px; overflow: hidden;'
        )
    ),
    style='display: flex; flex-direction: column; gap: 2.5rem; max-width: 375px; margin: 0 auto; padding: 1rem 0;'
)

class Artifact:
    def __init__(self, name, id, download_url):
        self.name = name
        self.id = id
        self.download_url = download_url

# The main screen
@app.route("/")
def get():
    page = Body(H1('More Optimism'),
                layout())
    return Title('More Optimism'), page

def main():
    print("Hello from mca-mo-mobile!")

if __name__ == '__main__': uvicorn.run("main:app", host='0.0.0.0', port=8001, reload=True)