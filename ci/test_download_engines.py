"""Transfer tests with deterministic HTTP responses; no external network."""
import pathlib
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import requests
from requests.structures import CaseInsensitiveDict

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from core.queue_manager import DownloadItem
from downloaders import direct_downloader as direct, segmented_downloader as segmented


class Response:
    def __init__(self, body=b'', status=200, headers=None, before_chunk=None):
        self.body=body; self.status_code=status; self.closed=False
        self.headers=CaseInsensitiveDict(headers or {}); self.before_chunk=before_chunk
    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    def close(self): self.closed=True
    def raise_for_status(self):
        if self.status_code>=400: raise requests.HTTPError(str(self.status_code))
    def iter_content(self,chunk_size):
        for offset in range(0,len(self.body),chunk_size):
            if self.before_chunk: self.before_chunk()
            yield self.body[offset:offset+chunk_size]


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=pathlib.Path(self.temp.name)
        self.item=DownloadItem('id','https://example.com/file.bin','','','','best','',''+str(self.root),'direct')
        self.data=bytes(range(256))*400
        self.item.fragment_threads=4
    def tearDown(self): self.temp.cleanup()
    def request(self,method,url,**kwargs):
        if method=='HEAD': return Response(headers={'Content-Length':str(len(self.data)), 'Accept-Ranges':'bytes'})
        range_header=kwargs.get('headers',{}).get('Range')
        if range_header:
            lo,hi=range_header.removeprefix('bytes=').split('-');lo=int(lo);hi=int(hi) if hi else len(self.data)-1
            body=self.data[lo:hi+1]
            return Response(body,206,{'Content-Length':str(len(body)),'Content-Range':f'bytes {lo}-{hi}/{len(self.data)}'})
        return Response(self.data,headers={'Content-Length':str(len(self.data))})
    def run_direct(self, request=None):
        with patch.object(direct.net_guard,'safe_request',side_effect=request or self.request):
            direct.download_direct(self.item,lambda *a,**k:None)
    def run_segmented(self,request=None):
        with patch.object(segmented.net_guard,'safe_request',side_effect=request or self.request),patch.object(segmented,'_MIN_SEG_SIZE',1):
            return segmented.download(self.item,lambda *a,**k:None)
    def seed_partial(self):
        (self.root/'file.bin.part').write_bytes(self.data[:300])
        (self.root/'file.bin.part.url').write_text(self.item.url)
    def test_direct_complete_bytes(self):
        self.run_direct(); self.assertEqual((self.root/'file.bin').read_bytes(),self.data)
    def test_direct_collision_preserves_original(self):
        (self.root/'file.bin').write_bytes(b'original'); self.run_direct()
        self.assertEqual((self.root/'file.bin').read_bytes(),b'original')
        self.assertEqual((self.root/'file (1).bin').read_bytes(),self.data)
    def test_direct_resumes_matching_partial(self):
        self.seed_partial(); ranges=[]
        def request(method,url,**kwargs):
            if method=='GET': ranges.append(kwargs['headers'].get('Range'))
            return self.request(method,url,**kwargs)
        self.run_direct(request)
        self.assertEqual(ranges,['bytes=300-'])
        self.assertEqual((self.root/'file.bin').read_bytes(),self.data)
    def test_direct_ignored_resume_restarts_without_duplicate_bytes(self):
        self.seed_partial()
        def request(method,url,**kwargs):
            if method=='GET': return Response(self.data,headers={'Content-Length':str(len(self.data))})
            return self.request(method,url,**kwargs)
        self.run_direct(request); self.assertEqual((self.root/'file.bin').read_bytes(),self.data)
    def test_direct_truncation_does_not_create_completed_file(self):
        def request(method,url,**kwargs):
            if method=='GET': return Response(b'partial',headers={'Content-Length':str(len(self.data))})
            return self.request(method,url,**kwargs)
        with self.assertRaises(Exception): self.run_direct(request)
        self.assertFalse((self.root/'file.bin').exists())
    def test_direct_404_does_not_create_completed_file(self):
        def request(method,url,**kwargs):
            return Response(status=404) if method=='GET' else self.request(method,url,**kwargs)
        with self.assertRaises(Exception): self.run_direct(request)
        self.assertFalse((self.root/'file.bin').exists())
    def test_compressed_content_length_is_not_decoded_size(self):
        def request(method,url,**kwargs):
            if method=='GET': return Response(self.data,headers={'Content-Length':'50','Content-Encoding':'gzip'})
            return self.request(method,url,**kwargs)
        self.run_direct(request); self.assertEqual((self.root/'file.bin').read_bytes(),self.data)
    def test_direct_cancel_preserves_partial_only(self):
        def request(method,url,**kwargs):
            if method=='GET': return Response(self.data,headers={'Content-Length':str(len(self.data))},before_chunk=self.item.cancel_event.set)
            return self.request(method,url,**kwargs)
        self.run_direct(request); self.assertFalse((self.root/'file.bin').exists())
    def test_segmented_assembles_correct_bytes(self):
        self.assertTrue(self.run_segmented());self.assertEqual((self.root/'file.bin').read_bytes(),self.data)
        self.assertFalse(list(self.root.glob('*.part*')))
    def test_segmented_truncation_not_reported_as_success(self):
        def request(method,url,**kwargs):
            response=self.request(method,url,**kwargs)
            if method=='GET': response.body=response.body[:3]
            return response
        self.assertFalse(self.run_segmented(request)); self.assertFalse((self.root/'file.bin').exists())
    def test_segmented_ignored_range_falls_back(self):
        def request(method,url,**kwargs):
            return Response(self.data,headers={'Content-Length':str(len(self.data))}) if method=='GET' else self.request(method,url,**kwargs)
        with patch.object(direct,'download_direct') as fallback:
            self.assertTrue(self.run_segmented(request));fallback.assert_called_once()
    def test_segmented_cancel_does_not_complete(self):
        self.item.cancel_event.set()
        self.assertFalse(self.run_segmented()); self.assertFalse((self.root/'file.bin').exists())
    def test_segmented_pause_waits_until_resume(self):
        self.item.pause_event.clear(); done=threading.Event()
        def worker():
            try: self.run_segmented()
            finally: done.set()
        thread=threading.Thread(target=worker)
        thread.start()
        premature=done.wait(.15)
        self.item.pause_event.set();thread.join(3)
        self.assertFalse(premature); self.assertTrue(done.is_set())
    def test_throttled_transfer_uses_single_stream(self):
        self.item.throttle_kbps=100
        with patch.object(direct,'download_direct') as fallback:
            self.assertTrue(self.run_segmented());fallback.assert_called_once()


if __name__=='__main__': unittest.main()
