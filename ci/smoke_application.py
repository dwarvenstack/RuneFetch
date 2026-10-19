"""Manual integration audit using the application's real dispatcher and engine."""
import asyncio
import json
import logging
import pathlib
import secrets
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from utils import settings
from core import engine as engine_module, queue_persistence
from core.engine import EngineFacade
from core.ui_server import UIServer, _fetch_formats_sync
from core.detector import detect

OUT = ROOT / 'build' / 'application-qa'
OUT.mkdir(parents=True, exist_ok=True)
DOWNLOADS = OUT / ('downloads-' + time.strftime('%Y%m%d-%H%M%S'))
DOWNLOADS.mkdir(exist_ok=True)
settings.CONFIG_DIR = str(OUT)
settings.CONFIG_PATH = str(OUT / 'config.json')
engine_module.HISTORY_PATH = OUT / 'history.json'
queue_persistence._STATE_FILE = OUT / 'queue.json'
cfg = dict(settings.DEFAULTS, save_path=str(DOWNLOADS), ui_token=secrets.token_hex(24),
           bridge_token=secrets.token_hex(24), keep_history=True, auto_check_updates=False)
engine = EngineFacade(cfg)
server = UIServer(engine, cfg)
results = []

def record(name, success, detail=''):
    results.append(dict(test=name, passed=bool(success), detail=str(detail)))
    print(('PASS ' if success else 'FAIL ') + name + (': ' + str(detail) if detail else ''), flush=True)
    (OUT / 'report.json').write_text(json.dumps(results, indent=2), encoding='utf-8')

async def call(action, **data):
    reply = await server._dispatch(json.dumps(dict(action=action, token=cfg['ui_token'], **data)))
    if not reply.get('ok'):
        raise RuntimeError(f'{action}: {reply.get("error")}')
    return reply

async def wait_terminal(item_id, timeout=180):
    deadline = time.monotonic() + timeout
    last_state = None
    while time.monotonic() < deadline:
        item = engine.get_item_dict(item_id)
        if item['state'] != last_state:
            print(f'  Download state: {item["state"]}', flush=True)
            last_state = item['state']
        if item['state'] in ('Complete', 'Error', 'Cancelled'):
            return item
        await asyncio.sleep(.2)
    raise TimeoutError('Download did not reach terminal state')

async def main():
    from core.version import __version__
    record('Ping/version', (await call('ping'))['version'] == __version__)
    bad = await server._dispatch(json.dumps(dict(action='ping', token='invalid')))
    record('Reject invalid authentication', bad.get('error') == 'unauthorized')
    malformed = await server._dispatch('{')
    record('Reject malformed messages', malformed.get('error') == 'invalid_json')
    record('Empty URL validation', not (await server._dispatch(json.dumps(dict(action='add',token=cfg['ui_token'],url='')))).get('ok'))
    await call('save_settings', settings=dict(theme='light', max_concurrent=1, throttle_kbps=0))
    saved = settings.load()
    record('Save and load isolated settings', saved['theme']=='light' and saved['max_concurrent']==1)
    await call('save_settings', settings=dict(theme='dark', max_concurrent=2))
    record('Restore theme and concurrency', (await call('get_settings'))['settings']['theme']=='dark')
    record('UI token excluded from settings', 'ui_token' not in (await call('get_settings'))['settings'])
    await call('set_throttle', value=256)
    record('Set speed limit', engine._qm.throttle_kbps==256)
    await call('set_throttle', value=0)

    url='https://www.youtube.com/shorts/HysJ32YP0x0'
    detection=(await call('detect',url=url))['detection']
    record('Detect YouTube Short', detection['type']=='youtube', detection.get('label'))
    try:
        formats,title=await asyncio.wait_for(asyncio.to_thread(_fetch_formats_sync,url,''),timeout=90)
        record('Fetch real Short formats', bool(formats), f'{title}; {len(formats)} formats')
    except Exception as exc:
        title='YouTube Short HysJ32YP0x0'
        record('Fetch real Short formats',False,exc)
    opts=dict(title=title, dl_type='youtube',source_label='YouTube',start_paused=True,
              fmt='bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best',quality='1080p')
    item_id=(await call('add',url=url,opts=opts))['id']
    record('Add to queue paused', engine.get_item_dict(item_id)['state']=='Paused')
    queue_persistence.save_queue(engine._qm.get_items())
    record('Persist queued download', any(i['url']==url for i in queue_persistence.load_queue()))
    await call('resume',id=item_id)
    await asyncio.sleep(.3)
    await call('pause',id=item_id)
    record('Pause active download', engine.get_item_dict(item_id)['state']=='Paused')
    await call('resume',id=item_id)
    record('Resume active download', engine.get_item_dict(item_id)['state'] in ('Downloading','Complete'))
    item=await wait_terminal(item_id)
    record('Download requested YouTube Short',item['state']=='Complete', item.get('error_msg') or item['title'])
    await asyncio.sleep(.4)
    history=(await call('get_history'))['history']
    record('Record download history', any(h['id']==item_id for h in history))
    videos=list(DOWNLOADS.glob('*.mp4'))
    if item['state']=='Complete' and videos:
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_type,codec_name,width,height','-of','json',str(videos[-1])],capture_output=True,text=True,timeout=30)
        info=json.loads(probe.stdout) if probe.returncode==0 else {}
        streams=info.get('streams',[])
        record('Downloaded media has video and audio', any(s['codec_type']=='video' for s in streams) and any(s['codec_type']=='audio' for s in streams), info)
        record('Downloaded file exists check', (await call('check_file_exists',save_path=str(DOWNLOADS),title=videos[-1].name))['exists'])
    paused_id=(await call('add',url=url,opts=opts))['id']
    await call('cancel',id=paused_id)
    record('Cancel queued download', engine.get_item_dict(paused_id)['state']=='Cancelled')
    await call('remove',id=paused_id)
    record('Remove test queue entry', engine.get_item_dict(paused_id) is None)
    try:
        direct=(await call('add',url='https://raw.githubusercontent.com/dwarvenstack/RuneFetch/main/README.md',opts=dict(dl_type='direct',title='README.md')))['id']
        direct_item=await wait_terminal(direct,timeout=90)
        record('Direct file download',direct_item['state']=='Complete',direct_item.get('error_msg'))
    except Exception as exc:
        record('Direct file download',False,exc)
    await asyncio.sleep(.4)
    latest=(await call('check_update',force=True))['update']
    record('Live update check', not latest.get('error'), f'Latest {latest.get("version")}')
    await call('clear_completed')
    record('Clear finished test queue', not engine.snapshot())
    history=(await call('get_history'))['history']
    if history:
        entry=history[-1]['id']
        record('Delete isolated history entry',(await call('delete_history',id=entry))['found'])
    await call('clear_history')
    record('Clear isolated history',not (await call('get_history'))['history'])
    print('OUTPUT DIRECTORY: '+str(DOWNLOADS),flush=True)

try:
    asyncio.run(main())
finally:
    server.stop()
if any(not result['passed'] for result in results):
    sys.exit(1)
