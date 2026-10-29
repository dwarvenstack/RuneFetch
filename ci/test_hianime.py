import base64
import json
import unittest
from unittest.mock import patch
from yt_dlp.utils import ExtractorError
from yt_dlp import YoutubeDL
from downloaders.hianime import HiAnimeIE, create_ytdlp

URL='https://hianime.at/watch/mob-psycho-100-926?ep=15519'
PLAYER='https://zokoanime.video/stream/mal/32182/2/sub'
STREAM='https://media.example.com/episode.m3u8'
def encode_config(value):
    raw=json.dumps(value).encode();key=b'otaku-embed-v1'
    return 'window.__P="'+base64.b64encode(bytes(v^key[i%len(key)] for i,v in enumerate(raw))).decode()+'"'
def server(url=PLAYER,track='sub'):
    return '<div class="server-item" data-type="'+track+'" data-hash="'+base64.b64encode(url.encode()).decode()+'">'

class HiAnimeTests(unittest.TestCase):
    def test_matches_only_supported_episode_pages(self):
        for u in [URL,'https://hianime.at/watch/black-clover-season-2-1-10492?ep=150266']:
            self.assertTrue(HiAnimeIE.suitable(u))
        for u in ['https://hianime.at.evil.test/watch/x?ep=1','https://hianime.at/watch/x','https://example.com/?ep=1']:
            self.assertFalse(HiAnimeIE.suitable(u))
    def test_decode_matches_public_player(self):
        self.assertEqual(HiAnimeIE.decode_config(encode_config({'src':STREAM})),{'src':STREAM})
    def test_missing_config_fails_clearly(self):
        with self.assertRaisesRegex(ExtractorError,'changed its player'): HiAnimeIE.decode_config('<html/>')
    def test_rejects_invalid_config(self):
        for value in [{},[],{'src':'file:///private'},{'src':123}]:
            with self.subTest(value=value),self.assertRaises(ExtractorError):
                HiAnimeIE.decode_config(encode_config(value))
    def test_discovers_new_player_domains_deduplicates_and_preserves_sub_track(self):
        fragment=server()+server(track='dub')+server('https://zokoanime.video.evil.test/stream/x')+server('http://zokoanime.video/stream/x')+server('https://127.0.0.1/stream/x')
        self.assertEqual(HiAnimeIE.player_urls(fragment),[PLAYER,'https://zokoanime.video.evil.test/stream/x','https://127.0.0.1/stream/x'])
    def test_missing_supported_server_is_explicit(self):
        ie=HiAnimeIE(YoutubeDL({"quiet":True}))
        with patch('downloaders.hianime.assert_url_allowed'),patch.object(ie,'_download_webpage',return_value='<title>Episode</title>hianime_ep_ajax ani_detail'),patch.object(ie,'_download_json',return_value={'status':True,'html':server(track='dub')}):
            with self.assertRaisesRegex(ExtractorError,'No supported subtitled server'):ie._real_extract(URL)
    def test_extraction_preserves_title_and_referer(self):
        ie=HiAnimeIE(YoutubeDL({"quiet":True}))
        with patch('downloaders.hianime.assert_url_allowed') as guard,patch.object(ie,'_download_webpage',side_effect=['<title>Mob Psycho 100 Episode 2 | HiAnime</title>hianime_ep_ajax ani_detail',encode_config({'src':STREAM})]),patch.object(ie,'_download_json',return_value={'status':True,'html':server()}),patch.object(ie,'_extract_m3u8_formats',return_value=[{'url':STREAM,'height':1080}]) as manifest:
            result=ie._real_extract(URL)
            self.assertEqual(result['title'],'Mob Psycho 100 Episode 2')
            self.assertEqual(result['http_headers'],{'Referer':PLAYER})
            self.assertEqual(result['formats'][0]['height'],1080)
            self.assertEqual(guard.call_count,4)
            manifest.assert_called_once()
    def test_other_sites_keep_standard_ytdlp(self):
        with patch('downloaders.hianime.yt_dlp.YoutubeDL') as ctor:
            create_ytdlp({'quiet':True},'https://youtube.com/watch?v=test')
            ctor.assert_called_once_with({'quiet':True})
    def test_custom_extractor_precedes_generic(self):
        with create_ytdlp({'quiet':True},URL) as ydl:
            self.assertEqual(next(iter(ydl._ies)),HiAnimeIE.ie_key())


class AutomaticServerTests(unittest.TestCase):
    def setUp(self):
        self.ie=HiAnimeIE(YoutubeDL({'quiet':True, 'no_warnings':True}))
        self.page='<title>Episode | HiAnime</title>hianime_ep_ajax ani_detail'

    def test_domain_change_with_same_page_structure_is_recognized(self):
        self.assertTrue(HiAnimeIE.suitable('https://hianime.nz/watch/show?ep=2'))

    def test_unrecognized_alias_page_does_not_call_episode_api(self):
        with patch('downloaders.hianime.assert_url_allowed'),patch.object(self.ie,'_download_webpage',return_value='<html>Different site</html>'),patch.object(self.ie,'_download_json') as api:
            with self.assertRaisesRegex(ExtractorError,'not a recognized'):self.ie._real_extract(URL)
            api.assert_not_called()

    def test_failed_first_server_uses_next_server(self):
        second='https://new-player.example.com/watch/2'
        with patch('downloaders.hianime.assert_url_allowed'),patch.object(self.ie,'_download_webpage',return_value=self.page),patch.object(self.ie,'_download_json',return_value={'html':server()+server(second)}),patch.object(self.ie,'_player_formats',side_effect=[ExtractorError('offline'),([{'url':STREAM}],{'Referer':second},{})]) as probe:
            result=self.ie._real_extract(URL)
            self.assertEqual(probe.call_count,2)
            self.assertEqual(result['http_headers']['Referer'],second)

    def test_all_servers_fail_clearly(self):
        with patch('downloaders.hianime.assert_url_allowed'),patch.object(self.ie,'_download_webpage',return_value=self.page),patch.object(self.ie,'_download_json',return_value={'html':server()}),patch.object(self.ie,'_player_formats',side_effect=ExtractorError('offline')):
            with self.assertRaisesRegex(ExtractorError,'after trying 1 server'):self.ie._real_extract(URL)

    def test_private_player_is_blocked_before_any_fetch(self):
        from utils.net_guard import BlockedAddressError
        with patch('downloaders.hianime.assert_url_allowed',side_effect=BlockedAddressError('blocked')),patch.object(self.ie,'_download_webpage') as fetch:
            with self.assertRaises(BlockedAddressError):self.ie._player_formats('https://127.0.0.1/video','1',URL)
            fetch.assert_not_called()

    def test_matching_player_config_survives_host_rename(self):
        with patch('downloaders.hianime.assert_url_allowed'),patch.object(self.ie,'_download_webpage',return_value=encode_config({'src':STREAM})),patch.object(self.ie,'_extract_m3u8_formats',return_value=[{'url':STREAM}]):
            formats,headers,_=self.ie._player_formats('https://new-player.example.com/embed/1','1',URL)
            self.assertEqual(formats[0]['url'],STREAM)

    def test_standard_hls_player_is_recognized(self):
        with patch('downloaders.hianime.assert_url_allowed'),patch.object(self.ie,'_download_webpage',return_value='<video><source src="'+STREAM+'"></video>'),patch.object(self.ie,'_extract_m3u8_formats',return_value=[{'url':STREAM}]) as manifest:
            formats,_,_=self.ie._player_formats(PLAYER,'1',URL)
            self.assertEqual(formats[0]['url'],STREAM)
            manifest.assert_called_once()

    def test_unknown_player_uses_existing_ytdlp_extractors(self):
        with patch('downloaders.hianime.assert_url_allowed'),patch.object(self.ie,'_download_webpage',return_value='<html/>'),patch.object(self.ie._downloader,'extract_info',return_value={'formats':[{'url':STREAM}]}):
            formats,_,_=self.ie._player_formats(PLAYER,'1',URL)
            self.assertEqual(formats[0]['url'],STREAM)

    def test_server_probes_are_bounded(self):
        fragment=''.join(server(f'https://player{i}.example.com/embed/1') for i in range(20))
        self.assertEqual(len(HiAnimeIE.player_urls(fragment)),6)
