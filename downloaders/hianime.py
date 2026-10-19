"""Experimental HiAnime adapter, isolated from upstream yt-dlp extractors."""
import base64
import html
import json
import re
from urllib.parse import urlsplit

import yt_dlp
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError, clean_html
from utils.net_guard import assert_url_allowed


class HiAnimeIE(InfoExtractor):
    IE_NAME = 'runefetch:hianime'
    _VALID_URL = r'https?://(?:www\.)?hianime\.at/watch/[^?#]+\?(?:[^#]*&)?ep=(?P<id>\d+)(?:[&#]|$)'

    @staticmethod
    def decode_config(page):
        match = re.search(r'window\.__P\s*=\s*"([A-Za-z0-9+/=]+)"', page)
        if not match:
            raise ExtractorError('The video host changed its player configuration', expected=True)
        try:
            raw = base64.b64decode(match[1], validate=True)
            key = b'otaku-embed-v1'
            config = json.loads(bytes(value ^ key[i % len(key)] for i, value in enumerate(raw)))
            if not isinstance(config, dict) or not isinstance(config.get('src'), str):
                raise ValueError('Missing stream')
            if urlsplit(config['src']).scheme != 'https':
                raise ValueError('Invalid stream URL')
            return config
        except (ValueError, UnicodeError) as exc:
            raise ExtractorError('Invalid video host configuration', expected=True) from exc

    @staticmethod
    def player_urls(fragment):
        urls = []
        # Prefer subtitled playback. Dub selection can be added independently.
        for tag in re.findall(r'<div\b[^>]*\bdata-hash="[^"]+"[^>]*>', fragment):
            attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', tag))
            if attrs.get('data-type') != 'sub':
                continue
            try:
                url = base64.b64decode(html.unescape(attrs['data-hash']), validate=True).decode('utf-8')
            except (ValueError, UnicodeError):
                continue
            parsed = urlsplit(url)
            if parsed.scheme == 'https' and parsed.hostname == 'zokoanime.video' and parsed.path.startswith('/stream/'):
                urls.append(url)
        return urls

    def _real_extract(self, url):
        episode_id = self._match_id(url)
        assert_url_allowed(url)
        page = self._download_webpage(url, episode_id)
        origin = 'https://' + urlsplit(url).netloc
        servers_url = origin + '/api/theme/episode/servers?episodeId=' + episode_id
        assert_url_allowed(servers_url)
        servers = self._download_json(servers_url, episode_id, headers={
            'Referer': url, 'X-Requested-With': 'XMLHttpRequest'})
        players = self.player_urls(servers.get('html', '') if isinstance(servers, dict) else '')
        if not players:
            raise ExtractorError('No supported subtitled server found for this episode', expected=True)
        embed_url = players[0]
        assert_url_allowed(embed_url)
        embed = self._download_webpage(embed_url, episode_id, headers={'Referer': url})
        config = self.decode_config(embed)
        assert_url_allowed(config['src'])
        headers = {'Referer': embed_url}
        formats = self._extract_m3u8_formats(config['src'], episode_id, 'mp4',
            m3u8_id='hls', headers=headers)
        title = clean_html(self._html_extract_title(page, default=None)) or 'HiAnime episode ' + episode_id
        title = re.sub(r'\s*\|\s*HiAnime\s*$', '', title)
        return {'id': episode_id, 'title': title, 'formats': formats,
                'http_headers': headers, 'webpage_url': url}


def create_ytdlp(options, url):
    """Register the experiment only for its exact supported site."""
    if not HiAnimeIE.suitable(url):
        return yt_dlp.YoutubeDL(options)
    ydl = yt_dlp.YoutubeDL(options, auto_init=False)
    ydl.add_info_extractor(HiAnimeIE())
    ydl.add_default_info_extractors()
    return ydl

