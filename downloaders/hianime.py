"""Experimental HiAnime adapter, isolated from upstream yt-dlp extractors."""
import base64
import html
import json
import re
from urllib.parse import urlsplit
from html.parser import HTMLParser

import yt_dlp
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError, DownloadError, clean_html
from utils.net_guard import assert_url_allowed, BlockedAddressError


class HiAnimeIE(InfoExtractor):
    IE_NAME = 'runefetch:hianime'
    _VALID_URL = r'https?://(?:www\.)?hianime\.[a-z]{2,12}/watch/[^?#]+\?(?:[^#]*&)?ep=(?P<id>\d+)(?:[&#]|$)'

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
        class Servers(HTMLParser):
            def __init__(self):
                super().__init__()
                self.urls = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if attrs.get('data-type') != 'sub' or not attrs.get('data-hash'):
                    return
                try:
                    url = base64.b64decode(attrs['data-hash'], validate=True).decode('utf-8')
                except (ValueError, UnicodeError):
                    return
                parsed = urlsplit(url)
                if parsed.scheme == 'https' and parsed.hostname and url not in self.urls:
                    self.urls.append(url)

        parser = Servers()
        parser.feed(fragment)
        return parser.urls[:6]

    @staticmethod
    def subtitle_tracks(tracks):
        """Use human labels: some players incorrectly mark every language as en."""
        if not isinstance(tracks, list):
            return {}
        languages = {'english': 'en', 'arabic': 'ar', 'french': 'fr', 'german': 'de',
                     'italian': 'it', 'portuguese': 'pt', 'spanish': 'es', 'hindi': 'hi',
                     'japanese': 'ja', 'russian': 'ru', 'turkish': 'tr'}
        subtitles = {}
        for track in tracks:
            if not isinstance(track, dict) or track.get('kind', 'subtitles') not in ('subtitles', 'captions'):
                continue
            url = track.get('src') or track.get('url') or ''
            if not isinstance(url, str) or urlsplit(url).scheme != 'https':
                continue
            try:
                assert_url_allowed(url)
            except (BlockedAddressError, ValueError, OSError):
                continue
            label = str(track.get('label') or track.get('name') or '').strip()
            key = label.lower()
            language = next((code for name, code in languages.items() if key == name or key.startswith(name + ' ')), None)
            if label:
                language = language or re.sub(r'[^a-z0-9-]+', '-', key).strip('-') or 'und'
            else:
                language = str(track.get('lang') or track.get('srclang') or 'und').lower()
            if language == 'en' and any(word in key for word in ('signs', 'songs')):
                language = 'en-signs'
            ext = urlsplit(url).path.rsplit('.', 1)[-1].lower()
            if ext not in ('vtt', 'srt', 'ass'):
                continue
            entries = subtitles.setdefault(language, [])
            entry = {'url': url, 'ext': ext, 'name': label or language}
            if entry not in entries:
                # Full default tracks take precedence over alternate versions.
                if track.get('default'):
                    entries.append(entry)
                else:
                    entries.insert(0, entry)
        return subtitles

    def _player_formats(self, embed_url, episode_id, page_url):
        assert_url_allowed(embed_url)
        embed = self._download_webpage(embed_url, episode_id, headers={'Referer': page_url})
        headers = {'Referer': embed_url}
        subtitles = {}
        # Recognize the player configuration rather than relying on its hostname.
        if re.search(r'window\.__P\s*=', embed):
            config = self.decode_config(embed)
            streams = [config['src']]
            subtitles = self.subtitle_tracks(config.get('subtitles', []))
        else:
            # Standard source URLs can be read without executing site scripts.
            streams = re.findall(r'https?://[^\s\"\'<>]+?\.m3u8(?:\?[^\s\"\'<>]*)?',
                                 html.unescape(embed).replace(r'\/', '/'))
        for stream in dict.fromkeys(streams):
            assert_url_allowed(stream)
            formats = self._extract_m3u8_formats(stream, episode_id, 'mp4',
                m3u8_id='hls', headers=headers, fatal=False)
            if formats:
                return formats, headers, subtitles
        # Let existing upstream extractors handle additional player families.
        info = self._downloader.extract_info(embed_url, download=False)
        formats = info.get('formats') if isinstance(info, dict) else None
        if formats:
            raw = info.get('subtitles') or {}
            safe = {}
            for lang, tracks in raw.items() if isinstance(raw, dict) else []:
                if isinstance(tracks, list):
                    safe.update(self.subtitle_tracks([{**t, 'lang': lang} for t in tracks if isinstance(t, dict)]))
            return formats, info.get('http_headers') or headers, safe
        raise ExtractorError('No supported stream found on this server', expected=True)

    def _real_extract(self, url):
        episode_id = self._match_id(url)
        assert_url_allowed(url)
        page = self._download_webpage(url, episode_id)
        if 'hianime_ep_ajax' not in page or 'ani_detail' not in page:
            raise ExtractorError('This page is not a recognized HiAnime episode page', expected=True)
        origin = 'https://' + urlsplit(url).netloc
        servers_url = origin + '/api/theme/episode/servers?episodeId=' + episode_id
        assert_url_allowed(servers_url)
        servers = self._download_json(servers_url, episode_id, headers={
            'Referer': url, 'X-Requested-With': 'XMLHttpRequest'})
        players = self.player_urls(servers.get('html', '') if isinstance(servers, dict) else '')
        if not players:
            raise ExtractorError('No supported subtitled server found for this episode', expected=True)
        formats = None
        failures = 0
        for embed_url in players:
            if embed_url == url or self.suitable(embed_url):
                continue  # Never recursively resolve an episode as its own player.
            try:
                formats, headers, subtitles = self._player_formats(embed_url, episode_id, url)
                if self.get_param('writesubtitles') and not subtitles.get('en'):
                    raise ExtractorError('English subtitles are unavailable on this server', expected=True)
                break
            except (ExtractorError, DownloadError, BlockedAddressError, ValueError, OSError):
                formats = None
                failures += 1
                self.to_screen(f'Server {failures} unavailable; trying the next server')
        if not formats:
            requirement = ' with English subtitles' if self.get_param('writesubtitles') else ''
            raise ExtractorError(
                f'No working supported subtitled server{requirement} found after trying {failures} server(s)',
                expected=True)
        title = clean_html(self._html_extract_title(page, default=None)) or 'HiAnime episode ' + episode_id
        title = re.sub(r'\s*\|\s*HiAnime\s*$', '', title)
        return {'id': episode_id, 'title': title, 'formats': formats,
                'http_headers': headers, 'webpage_url': url, 'subtitles': subtitles}


def create_ytdlp(options, url):
    """Register the experiment only for its exact supported site."""
    if not HiAnimeIE.suitable(url):
        return yt_dlp.YoutubeDL(options)
    options = dict(options)
    options.setdefault('socket_timeout', 10)
    options.setdefault('extractor_retries', 0)
    ydl = yt_dlp.YoutubeDL(options, auto_init=False)
    ydl.add_info_extractor(HiAnimeIE())
    ydl.add_default_info_extractors()
    return ydl

