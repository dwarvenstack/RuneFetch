"""Start the Windows bundle with an isolated profile and ping its UI server."""
import json
import os
import pathlib
import subprocess
import tempfile
import time
from websockets.sync.client import connect

root = pathlib.Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='runefetch_bundle_') as directory:
    env = dict(os.environ, USERPROFILE=directory)
    process = subprocess.Popen([str(root / 'dist/RuneFetch/RuneFetch.exe')], env=env)
    try:
        config = pathlib.Path(directory) / '.runefetch/config.json'
        deadline = time.monotonic() + 40
        last_error = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'Bundle exited early: {process.returncode}')
            try:
                cfg = json.loads(config.read_text(encoding='utf-8'))
                with connect('ws://127.0.0.1:8770', open_timeout=2) as ws:
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
    finally:
        process.terminate()
        process.wait(timeout=10)
