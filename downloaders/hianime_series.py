"""HiAnime series discovery and ordered batch downloads with optional ZIP output."""
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
import zipfile
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import yt_dlp
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError, clean_html, sanitize_filename
from utils.net_guard import assert_url_allowed

PAGE_RE = re.compile(r'https?://(?:www\.)?hianime\.[a-z]{2,12}/(?:watch/)?(?P<slug>[^/?#]+-(?P<id>\d+))(?:[?#].*)?$')


def is_series_page(url):
    return bool(PAGE_RE.fullmatch(url))


def parse_episodes(fragment, origin, slug):
    class Episodes(HTMLParser):
        def __init__(self):
            super().__init__()
            self.episodes = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            episode_id = attrs.get('data-id', '')
            number = attrs.get('data-number', '')
            if tag != 'a' or 'ep-item' not in attrs.get('class', '').split():
                return
            if not episode_id.isdigit() or not re.fullmatch(r'\d{1,6}(?:\.\d{1,3})?', number):
                return
            self.episodes.setdefault(episode_id, {'id': episode_id, 'number': number,
                'url': f'{origin}/watch/{slug}?ep={episode_id}'})
    parser = Episodes()
    parser.feed(fragment)
    episodes = sorted(parser.episodes.values(), key=lambda e: (float(e['number']), e['id']))
    if not episodes or len(episodes) > 2000:
        raise ValueError('Could not read a complete episode list (supported range: 1–2000 episodes)')
    return episodes


def inspect_series(url, proxy=''):
    match = PAGE_RE.fullmatch(url)
    if not match:
        raise ValueError('Unsupported series page')
    assert_url_allowed(url)
    origin = 'https://' + urlsplit(url).netloc
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'socket_timeout': 15,
                          'extractor_retries': 0, **({'proxy': proxy} if proxy else {})}) as ydl:
        ie = InfoExtractor(ydl)
        page = ie._download_webpage(url, match['id'])
        title = clean_html(ie._html_extract_title(page, default=None)) or 'HiAnime series'
        if 'HiAnime' not in title or 'film-name' not in page:
            raise ValueError('This is not a recognized HiAnime series page')
        endpoint = origin + '/api/theme/episode/list/' + match['id']
        assert_url_allowed(endpoint)
        data = ie._download_json(endpoint, match['id'], headers={'Referer': url, 'X-Requested-With': 'XMLHttpRequest'})
        if not isinstance(data, dict) or not data.get('status') or not isinstance(data.get('html'), str):
            raise ValueError('The website did not return an episode list')
        episodes = parse_episodes(data['html'], origin, match['slug'])
    current_id = parse_qs(urlsplit(url).query).get('ep', [''])[0]
    current = next((e for e in episodes if e['id'] == current_id), None)
    if current_id and current is None:
        raise ValueError('The linked episode is missing from the series episode list')
    title = re.sub(r'\s*\|\s*HiAnime\s*$', '', title)
    title = re.sub(r'^Watch\s+', '', title)
    if current:
        title = re.sub(r'\s+Episode\s+[\d.]+\s*$', '', title, flags=re.I)
    return {'id': match['id'], 'title': title.strip(), 'count': len(episodes), 'episodes': episodes,
            'current_episode': current, 'series_url': origin + '/' + match['slug']}


def validate_batch(url, batch):
    match = PAGE_RE.fullmatch(url)
    if not match or not isinstance(batch, dict):
        raise ValueError('Invalid series download')
    episodes = batch.get('episodes')
    if not isinstance(episodes, list) or not 1 <= len(episodes) <= 2000:
        raise ValueError('Invalid episode list')
    origin = 'https://' + urlsplit(url).netloc
    clean = []
    seen = set()
    seen_numbers = set()
    for episode in episodes:
        if not isinstance(episode, dict):
            raise ValueError('Invalid episode')
        episode_id, number = str(episode.get('id', '')), str(episode.get('number', ''))
        if not episode_id.isdigit() or not re.fullmatch(r'\d{1,6}(?:\.\d{1,3})?', number) or episode_id in seen or number in seen_numbers:
            raise ValueError('Invalid or duplicate episode number')
        seen.add(episode_id)
        seen_numbers.add(number)
        # Reconstruct the URL rather than accepting arbitrary client-supplied URLs.
        clean.append({'id': episode_id, 'number': number,
                      'url': f'{origin}/watch/{match["slug"]}?ep={episode_id}'})
    job_id = batch.get('job_id', '')
    if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{8}', job_id):
        job_id = uuid.uuid4().hex[:8]
    return {'id': match['id'], 'title': str(batch.get('title') or 'HiAnime series')[:120],
            'episodes': sorted(clean, key=lambda e: float(e['number'])),
            'zip': bool(batch.get('zip')), 'job_id': job_id}


def checkpoint(item):
    item.pause_event.wait()
    if item.cancel_event.is_set():
        raise InterruptedError('Series download cancelled')


def write_archive(files, target, item, progress_cb):
    """Write one complete archive atomically, keeping all source episode files."""
    total = sum(p.stat().st_size for p in files)
    done = 0
    fd, temporary = tempfile.mkstemp(prefix=target.stem + '-', suffix='.zip.part', dir=target.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
            for source in files:
                checkpoint(item)
                with source.open('rb') as src, archive.open(source.name, 'w', force_zip64=True) as dst:
                    while True:
                        checkpoint(item)
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        dst.write(chunk)
                        done += len(chunk)
                        progress_cb(95 + 4 * done / max(total, 1), '', 'Creating ZIP archive', '', speed_bps=0)
        checkpoint(item)
        # All job paths contain a persisted random ID; never overwrite a prior archive.
        if target.exists():
            raise FileExistsError('An archive with this name already exists')
        if os.name == 'nt':
            os.rename(temporary, target)  # Windows refuses to overwrite an existing file.
        else:
            os.link(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def download_series(item, progress_cb):
    from downloaders.ytdlp_downloader import download_ytdlp, _is_audio_only
    batch = validate_batch(item.url, item.series)
    item.series = batch
    root = Path(item.save_path)
    name = sanitize_filename(batch['title'], restricted=False)[:100].strip(' .') or 'HiAnime series'
    folder = root / f'{name} [{batch["id"]}] - {batch["job_id"]}'
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    count = len(batch['episodes'])
    scale = 95 if batch['zip'] else 99
    for index, episode in enumerate(batch['episodes']):
        checkpoint(item)
        child = copy.copy(item)
        child.url = episode['url']
        child.dl_type = 'ytdlp'
        child.is_playlist = False
        child.save_path = str(folder)
        prefix = 'Episode ' + episode['number'].zfill(3)
        child.output_template = str(folder / (prefix + '.%(ext)s'))
        def progress(pct, speed='', eta='', size='', speed_bps=0):
            progress_cb(scale * (index + min(pct, 100) / 100) / count, speed,
                        f'Episode {index + 1}/{count} — {eta}', '', speed_bps=speed_bps)
        try:
            download_ytdlp(child, progress)
        except Exception as exc:
            raise RuntimeError(f'Episode {episode["number"]} failed; completed files kept in {folder}: {exc}') from exc
        checkpoint(item)
        output = folder / (prefix + ('.mp3' if _is_audio_only(child) else '.mp4'))
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError(f'Episode {episode["number"]} did not produce a completed media file; ZIP was not created')
        files.append(output)
        # Keep the separate subtitles with their episode in the archive too.
        for subtitle in sorted(folder.glob(prefix + '.en.*')):
            if subtitle.suffix.lower() in ('.vtt', '.srt', '.ass'):
                files.append(subtitle)
        progress_cb(scale * (index + 1) / count, '', f'{index + 1}/{count} episodes complete', '')
    if batch['zip']:
        archive = Path(str(folder) + '.zip')
        write_archive(files, archive, item, progress_cb)
        item.title = archive.name
    else:
        item.title = folder.name
    item.save_path = str(root)
    progress_cb(99, '', 'Series complete', '')
