"""History must describe the output and honor the user's history preference."""
import pathlib
import queue
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from core.engine import EngineFacade, item_to_dict
from core.queue_manager import DownloadItem


class HistoryTests(unittest.TestCase):
    def engine(self, enabled=True):
        engine = EngineFacade.__new__(EngineFacade)
        engine._cfg = {'keep_history': enabled}
        engine._history = []
        engine._lock = threading.Lock()
        engine._events = queue.Queue()
        return engine

    def test_output_labels(self):
        for fmt, kind, title, expected in (
            ('bestvideo+bestaudio/best', 'youtube', 'A video', 'MP4'),
            ('bestaudio/best', 'youtube', 'Audio', 'MP3'),
            ('best', 'direct', 'manual.pdf', 'PDF'),
        ):
            with self.subTest(fmt=fmt), patch('core.engine._save_history_file'):
                engine = self.engine()
                engine._record_history({'fmt': fmt, 'dl_type': kind, 'title': title})
                self.assertEqual(engine.get_history()[0]['fmt_display'], expected)

    def test_disabled_history_is_not_recorded(self):
        with patch('core.engine._save_history_file') as save:
            engine = self.engine(False)
            engine._record_history({'title': 'A video', 'fmt': 'bestvideo+bestaudio'})
            self.assertEqual(engine.get_history(), [])
            save.assert_not_called()

    def test_serialized_download_retains_backend(self):
        item = DownloadItem('id', 'https://example.com/file.pdf', 'file.pdf', '', '', 'best', '', '.', 'direct')
        self.assertEqual(item_to_dict(item)['dl_type'], 'direct')


if __name__ == '__main__':
    unittest.main()
