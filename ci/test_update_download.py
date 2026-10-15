"""A truncated installer must never be returned to the updater for execution."""
import io
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from core import updater


class Response(io.BytesIO):
    def __init__(self, content, headers):
        super().__init__(content)
        self.headers = headers


class DownloadTests(unittest.TestCase):
    def test_complete_download(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(updater.tempfile, 'tempdir', directory), patch.object(
                updater.urllib.request, 'urlopen',
                return_value=Response(b'installer', {'Content-Length': '9'}),
            ):
                path = updater.download_update('https://example.com/setup.exe')
                self.assertEqual(pathlib.Path(path).read_bytes(), b'installer')

    def test_truncated_download_is_deleted(self):
        for headers in ({'Content-Length': '100'}, {}):
            with self.subTest(headers=headers), tempfile.TemporaryDirectory() as directory:
                with patch.object(updater.tempfile, 'tempdir', directory), patch.object(
                    updater.urllib.request, 'urlopen',
                    return_value=Response(b'partial', headers),
                ):
                    with self.assertRaisesRegex(RuntimeError, 'Incomplete update'):
                        updater.download_update('https://example.com/setup.exe', expected_size=100)
                self.assertEqual(list(pathlib.Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
