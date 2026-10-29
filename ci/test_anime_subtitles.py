"""Subtitle language selection, extraction fallback and real MP4 embedding."""
from pathlib import Path
import functools
import http.server
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from yt_dlp import YoutubeDL
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError
from downloaders.hianime import HiAnimeIE
from downloaders.ytdlp_downloader import download_ytdlp, _build_postprocessors
from core.queue_manager import DownloadItem

URL='https://hianime.at/watch/fullmetal-alchemist-brotherhood-1140?ep=19026'
PLAYER='https://player.example.com/embed/1'
TRACK='https://media.example.com/en.vtt'

class SubtitleSelectionTests(unittest.TestCase):
    def tracks(self,raw):
        with patch('downloaders.hianime.assert_url_allowed'):return HiAnimeIE.subtitle_tracks(raw)
    def test_uses_label_instead_of_incorrect_en_codes(self):
        result=self.tracks([{'lang':'en','label':'Arabic','src':TRACK.replace('en.','ar.')},{'lang':'en','label':'English','src':TRACK}])
        self.assertEqual(list(result),['ar','en']);self.assertEqual(result['en'][0]['name'],'English')
    def test_signs_only_track_is_not_full_english_dialogue(self):
        result=self.tracks([{'label':'English Signs & Songs','src':TRACK}]);self.assertNotIn('en',result)
    def test_thumbnail_tracks_are_ignored(self):
        self.assertEqual(self.tracks([{'kind':'thumbnails','label':'English','src':TRACK}]),{})
    def test_invalid_tracks_are_ignored(self):
        self.assertEqual(self.tracks([None,{'src':'file:///private.vtt'},{'src':TRACK.replace('.vtt','.jpg')}]),{})
    def test_private_track_is_not_exposed(self):
        from utils.net_guard import BlockedAddressError
        with patch('downloaders.hianime.assert_url_allowed',side_effect=BlockedAddressError('blocked')):
            self.assertEqual(HiAnimeIE.subtitle_tracks([{'label':'English','src':'https://127.0.0.1/private.vtt'}]),{})
    def test_server_without_english_is_skipped(self):
        ie=HiAnimeIE(YoutubeDL({'quiet':True,'writesubtitles':True}))
        subtitle={'en':[{'url':TRACK,'ext':'vtt','name':'English'}]}
        with patch('downloaders.hianime.assert_url_allowed'),patch.object(ie,'_download_webpage',return_value='<title>Episode | HiAnime</title>hianime_ep_ajax ani_detail'),patch.object(ie,'_download_json',return_value={'html':'servers'}),patch.object(ie,'player_urls',return_value=[PLAYER,PLAYER+'2']),patch.object(ie,'_player_formats',side_effect=[([{'url':'media'}],{},{}),([{'url':'media'}],{},subtitle)]) as probe:
            result=ie._real_extract(URL)
        self.assertEqual(probe.call_count,2);self.assertEqual(result['subtitles'],subtitle)
    def test_missing_english_fails_instead_of_returning_unsubtitled_video(self):
        ie=HiAnimeIE(YoutubeDL({'quiet':True,'writesubtitles':True}))
        with patch('downloaders.hianime.assert_url_allowed'),patch.object(ie,'_download_webpage',return_value='<title>Episode</title>hianime_ep_ajax ani_detail'),patch.object(ie,'_download_json',return_value={'html':'servers'}),patch.object(ie,'player_urls',return_value=[PLAYER]),patch.object(ie,'_player_formats',return_value=([{'url':'media'}],{},{})):
            with self.assertRaises(ExtractorError):ie._real_extract(URL)
    def test_embedding_only_enabled_for_anime_video(self):
        item=DownloadItem('id',URL,'','','','best','1080p','.','ytdlp')
        self.assertTrue(any(p['key']=='FFmpegEmbedSubtitle' and p['already_have_subtitle'] for p in _build_postprocessors(item)))
        item.quality='Audio only';item.fmt='bestaudio/best'
        self.assertFalse(any(p['key']=='FFmpegEmbedSubtitle' for p in _build_postprocessors(item)))
        item.quality='1080p';item.fmt='best';item.url='https://youtube.com/watch?v=test'
        self.assertFalse(any(p['key']=='FFmpegEmbedSubtitle' for p in _build_postprocessors(item)))

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg and ffprobe required')
class SubtitleEmbeddingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=160x90:r=10','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(cls.root/'sample.mp4')],check=True,capture_output=True,timeout=30)
        (cls.root/'english.vtt').write_text('WEBVTT\n\n00:00:00.000 --> 00:00:01.800\nEnglish subtitle test\n',encoding='utf-8')
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*a):pass
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(cls.root)))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()
    def run_transfer(self,missing=False):
        base=f'http://127.0.0.1:{self.server.server_port}'
        class FixtureIE(InfoExtractor):
            _VALID_URL=r'https://hianime\.at/watch/[^?]+\?ep=(?P<id>\d+)'
            def _real_extract(self,url):
                return {'id':self._match_id(url),'title':'Subtitle fixture','url':base+'/sample.mp4','ext':'mp4','subtitles':{'en':[{'url':base+('/missing.vtt' if missing else '/english.vtt'),'ext':'vtt','name':'English'}]}}
        def factory(opts,url):
            opts={**opts,'quiet':True,'noprogress':True,'no_warnings':True,'retries':0}
            y=YoutubeDL(opts,auto_init=False);y.add_info_extractor(FixtureIE());return y
        output=self.root/('missing' if missing else 'output');output.mkdir(exist_ok=True)
        item=DownloadItem('fixture',URL,'','','','best','1080p',str(output),'ytdlp')
        with patch('downloaders.hianime.create_ytdlp',side_effect=factory):download_ytdlp(item,lambda *a,**k:None)
        return output
    def test_real_pipeline_retains_vtt_and_embeds_english_in_mp4(self):
        output=self.run_transfer();mp4=output/'Subtitle fixture.mp4'
        self.assertTrue((output/'Subtitle fixture.en.vtt').exists())
        probe=subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',str(mp4)],capture_output=True,text=True,check=True)
        subtitles=[s for s in json.loads(probe.stdout)['streams'] if s['codec_type']=='subtitle']
        self.assertEqual(len(subtitles),1);self.assertEqual(subtitles[0]['codec_name'],'mov_text')
        self.assertEqual(subtitles[0]['tags']['language'],'eng')
        extracted=subprocess.run(['ffmpeg','-v','error','-i',str(mp4),'-map','0:s:0','-f','webvtt','-'],capture_output=True,text=True,check=True)
        self.assertIn('English subtitle test',extracted.stdout)
    def test_subtitle_http_error_fails_the_download(self):
        with self.assertRaises(Exception):self.run_transfer(missing=True)
