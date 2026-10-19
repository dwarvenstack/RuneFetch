"""Live audio-only download and full media validation in an isolated folder."""
import pathlib
import subprocess
import sys
import time
import json

ROOT=pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from core.queue_manager import DownloadItem
from downloaders.router import run_download

out=ROOT/'build'/('audio-smoke-'+time.strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True,exist_ok=True)
item=DownloadItem('audio-test','https://www.youtube.com/shorts/HysJ32YP0x0','','YouTube','','bestaudio/best','Audio only',str(out),'youtube')
run_download(item,lambda *args,**kwargs:None)
files=list(out.glob('*.mp3'))
assert len(files)==1,'Expected one MP3 file'
probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type,codec_name:format=duration','-of','json',str(files[0])],capture_output=True,text=True,check=True)
data=json.loads(probe.stdout)
assert any(s['codec_type']=='audio' for s in data['streams'])
assert not any(s['codec_type']=='video' for s in data['streams'])
assert float(data['format']['duration'])>90
subprocess.run(['ffmpeg','-v','error','-i',str(files[0]),'-f','null','-'],check=True)
print('PASS: live MP3 extraction, audio-only stream and full decode',flush=True)
print(files[0],flush=True)
