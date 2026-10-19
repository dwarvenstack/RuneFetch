"""Isolated preferences/queue recovery and media selector tests."""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from utils import settings
from core import queue_persistence as persistence
from core.queue_manager import DownloadItem
from core.detector import detect
from downloaders.ytdlp_downloader import _build_format, _is_audio_only, _build_postprocessors


def item(fmt='bestvideo+bestaudio/best', quality='1080p'):
    return DownloadItem('test','https://www.youtube.com/shorts/HysJ32YP0x0','Test','','',fmt,quality,'.','youtube')


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.patches = [patch.object(settings,'CONFIG_DIR',str(self.root)),patch.object(settings,'CONFIG_PATH',str(self.root/'config.json')),patch.object(persistence,'_STATE_FILE',self.root/'queue.json')]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def test_missing_settings_use_independent_defaults(self):
        cfg=settings.load(); cfg['save_path']='changed'
        self.assertNotEqual(settings.DEFAULTS['save_path'],'changed')

    def test_corrupt_settings_recovered(self):
        pathlib.Path(settings.CONFIG_PATH).write_text('{')
        self.assertEqual(settings.load(),settings.DEFAULTS)

    def test_settings_round_trip(self):
        cfg=dict(settings.DEFAULTS,theme='light',save_path='日本語',max_concurrent=3)
        settings.save(cfg)
        self.assertEqual(settings.load(),cfg)

    def test_existing_token_preserved(self):
        cfg={'bridge_token':'existing'}
        self.assertEqual(settings.get_or_create_bridge_token(cfg),'existing')

    def test_new_token_saved_and_distinct(self):
        cfg=dict(settings.DEFAULTS,bridge_token='')
        token=settings.get_or_create_bridge_token(cfg)
        self.assertEqual(len(token),64)
        self.assertEqual(settings.load()['bridge_token'],token)

    def test_active_queue_saved_paused_and_completed_excluded(self):
        running=item(); running.state='Downloading'
        complete=item(); complete.id='complete'; complete.state='Complete'
        persistence.save_queue([running,complete])
        saved=persistence.load_queue()
        self.assertEqual(len(saved),1)
        self.assertEqual(saved[0]['status'],'PAUSED')
        self.assertEqual(saved[0]['fmt'],running.fmt)

    def test_corrupt_and_wrong_shape_queue_recovered(self):
        for body in ('{','{}','null'):
            with self.subTest(body=body):
                persistence._STATE_FILE.write_text(body)
                self.assertEqual(persistence.load_queue(),[])

    def test_clear_saved_queue(self):
        persistence.save_queue([item()]); persistence.clear_queue_state()
        self.assertEqual(persistence.load_queue(),[])


class FormatTests(unittest.TestCase):
    def test_video_with_audio_is_not_audio_only(self):
        self.assertFalse(_is_audio_only(item()))
        self.assertEqual(_build_postprocessors(item())[0]['key'],'FFmpegVideoConvertor')

    def test_audio_selector_extracts_mp3(self):
        audio=item('bestaudio/best','Audio only')
        self.assertTrue(_is_audio_only(audio))
        self.assertEqual(_build_postprocessors(audio)[0]['preferredcodec'],'mp3')

    def test_explicit_selector_preserved(self):
        fmt='bestvideo[height<=720]+bestaudio/best'
        self.assertEqual(_build_format(item(fmt)),fmt)

    def test_quality_limits_in_generated_selector(self):
        for quality in ('2160p','1080p','720p','480p','360p','240p'):
            with self.subTest(quality=quality):
                self.assertIn('height<='+quality[:-1],_build_format(item('Video (MP4)',quality)))

    def test_source_detection(self):
        cases=[('https://www.youtube.com/shorts/HysJ32YP0x0','youtube'),('https://youtu.be/test','youtube'),('https://open.spotify.com/track/test','spotify'),('https://example.com/manual.pdf','direct'),('https://www.netflix.com/watch/1','drm')]
        for url,expected in cases:
            with self.subTest(url=url): self.assertEqual(detect(url)['type'],expected)


if __name__ == '__main__':
    unittest.main()
