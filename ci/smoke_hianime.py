"""Manual live check for the experimental HiAnime adapter (not ordinary CI)."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.queue_manager import DownloadItem
from core.ui_server import _fetch_formats_sync
from downloaders.router import run_download


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    args = parser.parse_args()
    formats, title = _fetch_formats_sync(args.url, '')
    assert any(f.get('height') for f in formats), 'No video resolutions found'
    out = ROOT / 'build' / ('hianime-smoke-' + time.strftime('%Y%m%d-%H%M%S'))
    out.mkdir(exist_ok=False)
    item = DownloadItem('hianime-smoke', args.url, '', title, '', 'best', 'Best quality', str(out), 'ytdlp')
    run_download(item, lambda *a, **k: None)
    files = list(out.glob('*.mp4'))
    assert len(files) == 1, 'Expected exactly one completed MP4'
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
        'format=duration,size:stream=codec_type,codec_name,width,height', '-of', 'json', str(files[0])],
        capture_output=True, text=True, check=True, timeout=30)
    data = json.loads(probe.stdout)
    assert any(s['codec_type'] == 'video' for s in data['streams'])
    assert any(s['codec_type'] == 'audio' for s in data['streams'])
    assert float(data['format']['duration']) > 0
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(files[0]), '-f', 'null', '-'], check=True, timeout=300)
    print(json.dumps({'title': title, 'file': str(files[0]), 'probe': data}, indent=2))
    print('PASS: format lookup, routed download, audio/video streams and full decode')


if __name__ == '__main__':
    main()
