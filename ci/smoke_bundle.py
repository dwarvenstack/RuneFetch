"""Start the Windows bundle with an isolated profile and ping its UI server."""
import json
import os
import pathlib
import subprocess
import tempfile
import time
import argparse
import socket
from websockets.sync.client import connect

root = pathlib.Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--exe', default=str(root / 'dist/RuneFetch/RuneFetch.exe'))
parser.add_argument('--download-url')
parser.add_argument('--audio-only', action='store_true')
parser.add_argument('--download-dir', default=str(root / 'build/packaged-download'))
parser.add_argument('--hold', type=int, default=0)
args = parser.parse_args()

def free_port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]

with tempfile.TemporaryDirectory(prefix='runefetch_bundle_') as directory:
    env = dict(os.environ, USERPROFILE=directory)
    config = pathlib.Path(directory) / '.runefetch/config.json'
    config.parent.mkdir()
    config.write_text(json.dumps(dict(ui_port=free_port(),bridge_port=free_port(),auto_check_updates=False,clipboard_monitor=False,save_path=args.download_dir)),encoding='utf-8')
    process = subprocess.Popen([args.exe], env=env)
    try:
        config = pathlib.Path(directory) / '.runefetch/config.json'
        deadline = time.monotonic() + 40
        last_error = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'Bundle exited early: {process.returncode}')
            try:
                cfg = json.loads(config.read_text(encoding='utf-8'))
                with connect(f'ws://127.0.0.1:{cfg["ui_port"]}', open_timeout=2) as ws:
                    ws.send(json.dumps({'token': cfg['ui_token'], 'action': 'ping'}))
                    for _ in range(10):
                        reply = json.loads(ws.recv(timeout=3))
                        if reply.get('app') == 'RuneFetch' and reply.get('ok'):
                            expected = (root / 'VERSION').read_text().strip()
                            assert reply['version'] == expected, reply
                            print(f'OK: packaged app starts and authenticates as v{expected}')
                            break
                    else:
                        raise RuntimeError('No ping response')
                break
            except (OSError, KeyError, ValueError, TimeoutError) as exc:
                last_error = exc
                time.sleep(1)
        else:
            log = pathlib.Path(directory) / '.runefetch/runefetch.log'
            if log.exists():
                print(log.read_text(encoding='utf-8')[-6000:])
            raise RuntimeError(f'Bundle startup timed out: {last_error}')
        if args.download_url:
            pathlib.Path(args.download_dir).mkdir(parents=True,exist_ok=True)
            with connect(f'ws://127.0.0.1:{cfg["ui_port"]}',open_timeout=3) as ws:
                def command(action, **data):
                    ws.send(json.dumps(dict(token=cfg['ui_token'],action=action,**data)))
                    while True:
                        reply=json.loads(ws.recv(timeout=20))
                        if 'ok' in reply:
                            if not reply['ok']: raise RuntimeError(reply)
                            return reply
                fmt='bestaudio/best' if args.audio_only else 'bestvideo[height<=1080]+bestaudio/best'
                quality='Audio only' if args.audio_only else '1080p'
                item_id=command('add',url=args.download_url,opts=dict(dl_type='youtube',source_label='YouTube',fmt=fmt,quality=quality))['id']
                download_deadline=time.monotonic()+180
                while time.monotonic()<download_deadline:
                    items=command('snapshot')['items']
                    item=next((i for i in items if i['id']==item_id),None)
                    if item and item['state'] in ('Complete','Error','Cancelled'):
                        if item['state']!='Complete': raise RuntimeError(item.get('error_msg'))
                        print('OK: packaged app completed real download: '+item['title'],flush=True)
                        break
                    time.sleep(.4)
                else: raise TimeoutError('Packaged download timed out')
        if args.hold:
            print('Holding packaged app open for visual inspection',flush=True)
            time.sleep(min(args.hold,60))
    finally:
        process.terminate()
        process.wait(timeout=10)
