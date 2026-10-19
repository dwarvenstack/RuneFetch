"""Byte-for-byte transfers over real loopback HTTP using a test-only allowlist."""
import gzip
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from core.queue_manager import DownloadItem
from downloaders.direct_downloader import download_direct
from downloaders.segmented_downloader import download
from utils import net_guard


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
        self.payload=bytes(range(256))*5000
        payload=self.payload
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_HEAD(self):
                self.send_response(200);self.send_header('Content-Length',str(len(payload)))
                self.send_header('Accept-Ranges','bytes');self.end_headers()
            def do_GET(self):
                body=payload;status=200;headers={}
                byte_range=self.headers.get('Range')
                if byte_range and 'ignore' not in self.path:
                    lo,hi=byte_range.removeprefix('bytes=').split('-');lo=int(lo);hi=int(hi) if hi else len(payload)-1
                    body=payload[lo:hi+1];status=206;headers['Content-Range']=f'bytes {lo}-{hi}/{len(payload)}'
                if 'compressed' in self.path:
                    body=gzip.compress(body);headers['Content-Encoding']='gzip'
                self.send_response(status)
                self.send_header('Content-Length',str(len(body)))
                for key,value in headers.items():self.send_header(key,value)
                self.end_headers();self.wfile.write(body)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.05),daemon=True)
        self.thread.start();self.base=f'http://127.0.0.1:{self.server.server_port}/'
        def allow_fixture_only(url):
            if not url.startswith(self.base): raise net_guard.BlockedAddressError('Not the local test fixture')
            return {'127.0.0.1'}
        self.guard=patch.object(net_guard,'assert_url_allowed',side_effect=allow_fixture_only);self.guard.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.guard.stop();self.temp.cleanup()
    def item(self,name='file.bin'):
        return DownloadItem('id',self.base+name,'','','','best','',str(self.root),'direct',fragment_threads=4)
    def test_parallel_ranges_over_http(self):
        self.assertTrue(download(self.item(),lambda *a,**k:None))
        self.assertEqual((self.root/'file.bin').read_bytes(),self.payload)
    def test_ignored_ranges_fall_back_over_http(self):
        self.assertTrue(download(self.item('ignore.bin'),lambda *a,**k:None))
        self.assertEqual((self.root/'ignore.bin').read_bytes(),self.payload)
    def test_gzip_response_decoded_without_false_truncation(self):
        download_direct(self.item('compressed.bin'),lambda *a,**k:None)
        self.assertEqual((self.root/'compressed.bin').read_bytes(),self.payload)
    def test_resume_over_http(self):
        item=self.item();(self.root/'file.bin.part').write_bytes(self.payload[:700])
        (self.root/'file.bin.part.url').write_text(item.url)
        download_direct(item,lambda *a,**k:None)
        self.assertEqual((self.root/'file.bin').read_bytes(),self.payload)
    def test_speed_limit_on_real_http_transfer(self):
        item=self.item(); item.throttle_kbps=512
        started=time.monotonic()
        self.assertTrue(download(item,lambda *a,**k:None))
        elapsed=time.monotonic()-started
        self.assertGreaterEqual(elapsed, .8*len(self.payload)/(512*1024))
        self.assertEqual((self.root/'file.bin').read_bytes(),self.payload)


if __name__=='__main__':unittest.main()
