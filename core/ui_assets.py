"""Load the frontend without extracting web source files in packaged builds."""
import sys
from pathlib import Path


def window_content():
    if getattr(sys, 'frozen', False):
        from core._embedded_ui import load_html
        return {'html': load_html()}
    return {'url': str(Path(__file__).resolve().parents[1] / 'webui/index.html')}
