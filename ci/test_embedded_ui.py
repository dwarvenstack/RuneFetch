import importlib.util
from pathlib import Path
import sys
import runpy
import runpy
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('embed_ui', ROOT / 'packaging/embed_ui.py')
embed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(embed)


class EmbeddedUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runpy.run_path(str(ROOT / "packaging/embed_ui.py"), run_name="__main__")

    @classmethod
    def setUpClass(cls):
        runpy.run_path(str(ROOT / "packaging/embed_ui.py"), run_name="__main__")

    def test_assets_are_self_contained(self):
        html = embed.bundle_html()
        self.assertNotIn('src="js/', html)
        self.assertNotIn('href="styles/', html)
        self.assertNotIn("import { ws }", html)
        self.assertIn('const ws = new WsClient', html)
        self.assertIn('async function checkForUpdate', html)
        self.assertEqual(html.count('<script type="module">'), 1)

    def test_packaged_window_uses_html(self):
        from core.ui_assets import window_content
        from core._embedded_ui import load_html
        with patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(window_content(), {'html': embed.bundle_html()})
        self.assertEqual(load_html(), embed.bundle_html())

    def test_development_window_keeps_source_reload(self):
        from core.ui_assets import window_content
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(window_content(), {'url': str(ROOT / 'webui/index.html')})
