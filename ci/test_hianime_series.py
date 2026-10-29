"""Series discovery, validation, persistence and failure-safe ZIP regression tests."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from core.queue_manager import DownloadItem, QueueManager
from core import queue_persistence
from downloaders.hianime_series import (parse_episodes, inspect_series, validate_batch,
    download_series, write_archive, is_series_page)

URL='https://hianime.at/fullmetal-alchemist-brotherhood-1140'
WATCH='https://hianime.at/watch/fullmetal-alchemist-brotherhood-1140?ep=19026'
FRAGMENT=''.join(f'<a class="ssl-item ep-item" data-id="{19025+n}" data-number="{n}" href="https://evil.example/x">Episode {n}</a>' for n in [3,1,2,1])
PAGE='<title>Watch Fullmetal Alchemist: Brotherhood | HiAnime</title><h2 class="film-name">Series</h2>'

def batch(zip_output=True):
    return {'title':'Fullmetal Alchemist: Brotherhood','episodes':parse_episodes(FRAGMENT,'https://hianime.at','fullmetal-alchemist-brotherhood-1140'),'zip':zip_output}

class SeriesDiscoveryTests(unittest.TestCase):
    def test_recognizes_both_input_links(self):
        self.assertTrue(is_series_page(URL));self.assertTrue(is_series_page(WATCH))
        self.assertFalse(is_series_page('https://hianime.at.evil.test/show-1140'))
    def test_real_count_sorted_deduplicated_and_canonical_urls(self):
        result=parse_episodes(FRAGMENT,'https://hianime.at','show-1140')
        self.assertEqual([e['number'] for e in result],['1','2','3'])
        self.assertEqual(len(result),3)
        self.assertTrue(all(e['url'].startswith('https://hianime.at/watch/show-1140?ep=') for e in result))
    def test_no_episode_list_is_error(self):
        with self.assertRaises(ValueError):parse_episodes('<a href="ad">Advertisement</a>','https://hianime.at','show-1')
    def test_ignores_malformed_episode_numbers(self):
        fragment=FRAGMENT+'<a class="ep-item" data-number="../../x" data-id="123">x</a>'
        self.assertEqual(len(parse_episodes(fragment,'https://hianime.at','show-1')),3)
    def discover(self,url,data=None,page=PAGE):
        with patch('downloaders.hianime_series.assert_url_allowed'),patch('downloaders.hianime_series.InfoExtractor._download_webpage',return_value=page),patch('downloaders.hianime_series.InfoExtractor._download_json',return_value=data or {'status':True,'totalItems':1,'html':FRAGMENT}):
            return inspect_series(url)
    def test_counts_episodes_not_api_group_count(self):
        result=self.discover(URL)
        self.assertEqual(result['count'],3);self.assertIsNone(result['current_episode'])
        self.assertEqual(result['title'],'Fullmetal Alchemist: Brotherhood')
    def test_episode_link_preserves_selected_episode(self):
        result=self.discover(WATCH)
        self.assertEqual(result['current_episode']['id'],'19026')
        self.assertEqual(result['count'],3)
    def test_missing_current_episode_fails(self):
        with self.assertRaisesRegex(ValueError,'missing'):self.discover(WATCH.replace('19026','99999'))
    def test_unrecognized_page_fails(self):
        with self.assertRaisesRegex(ValueError,'not a recognized'):self.discover(URL,page='<title>Other site</title>')
    def test_failed_endpoint_is_not_reported_as_zero_episodes(self):
        with self.assertRaisesRegex(ValueError,'did not return'):self.discover(URL,{'status':False})

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.item=DownloadItem('series',URL,'Series','HiAnime','','best','1080p',str(self.root),'hianime_series')
        self.item.series=validate_batch(URL,batch())
    def tearDown(self):self.temp.cleanup()
    def transfer(self,child,cb):
        self.assertIs(child.cancel_event,self.item.cancel_event)
        self.assertIs(child.pause_event,self.item.pause_event)
        output=Path(child.output_template.replace('%(ext)s','mp4'))
        output.write_bytes(('media '+child.url).encode())
        cb(100,'1 MB/s','', '',speed_bps=1024)
    def test_complete_series_zip_contains_every_episode_and_keeps_files(self):
        with patch('downloaders.ytdlp_downloader.download_ytdlp',side_effect=self.transfer):download_series(self.item,lambda *a,**k:None)
        archives=list(self.root.glob('*.zip'));self.assertEqual(len(archives),1)
        with zipfile.ZipFile(archives[0]) as z:
            self.assertIsNone(z.testzip());self.assertEqual(len(z.namelist()),3)
            self.assertEqual(z.namelist(),['Episode 001.mp4','Episode 002.mp4','Episode 003.mp4'])
            for name in z.namelist():self.assertEqual(z.read(name),next(self.root.glob('*/'+name)).read_bytes())
        self.assertFalse(list(self.root.glob('*.zip.part')))
    def test_zip_includes_separate_english_subtitles_for_each_episode(self):
        def transfer_with_subtitle(child, cb):
            self.transfer(child, cb)
            Path(child.output_template.replace('.%(ext)s', '.en.vtt')).write_text('WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nSubtitles\n')
        with patch('downloaders.ytdlp_downloader.download_ytdlp', side_effect=transfer_with_subtitle):
            download_series(self.item, lambda *a, **k: None)
        with zipfile.ZipFile(next(self.root.glob('*.zip'))) as archive:
            self.assertEqual(len(archive.namelist()), 6)
            self.assertEqual(len([n for n in archive.namelist() if n.endswith('.en.vtt')]), 3)
            self.assertIsNone(archive.testzip())

    def test_unchecked_zip_saves_only_episode_files(self):
        self.item.series['zip']=False
        with patch('downloaders.ytdlp_downloader.download_ytdlp',side_effect=self.transfer):download_series(self.item,lambda *a,**k:None)
        self.assertEqual(len(list(self.root.glob('*/*.mp4'))),3);self.assertFalse(list(self.root.glob('*.zip')))
    def test_failed_episode_preserves_previous_files_and_no_archive(self):
        calls=[0]
        def failing(child,cb):
            calls[0]+=1
            if calls[0]==2:raise RuntimeError('network error')
            self.transfer(child,cb)
        with patch('downloaders.ytdlp_downloader.download_ytdlp',side_effect=failing):
            with self.assertRaisesRegex(RuntimeError,'Episode 2 failed'):download_series(self.item,lambda *a,**k:None)
        self.assertEqual(len(list(self.root.glob('*/*.mp4'))),1);self.assertFalse(list(self.root.glob('*.zip')))
    def test_cancel_prevents_archive_and_more_transfers(self):
        def cancelling(child,cb):self.transfer(child,cb);self.item.cancel_event.set()
        with patch('downloaders.ytdlp_downloader.download_ytdlp',side_effect=cancelling) as transfer:
            with self.assertRaises(InterruptedError):download_series(self.item,lambda *a,**k:None)
        self.assertEqual(transfer.call_count,1);self.assertFalse(list(self.root.glob('*.zip')))
    def test_missing_output_file_cannot_mark_series_complete(self):
        with patch('downloaders.ytdlp_downloader.download_ytdlp'):
            with self.assertRaisesRegex(RuntimeError,'did not produce'):download_series(self.item,lambda *a,**k:None)
    def test_existing_zip_is_never_overwritten(self):
        source=self.root/'episode.mp4';source.write_bytes(b'video')
        target=self.root/'series.zip';target.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):write_archive([source],target,self.item,lambda *a,**k:None)
        self.assertEqual(target.read_bytes(),b'existing');self.assertFalse(list(self.root.glob('*.zip.part')))
    def test_archive_cancel_cleans_partial_archive(self):
        source=self.root/'episode.mp4';source.write_bytes(b'x'*(2*1024*1024))
        def cancel(*a,**k):self.item.cancel_event.set()
        with self.assertRaises(InterruptedError):write_archive([source],self.root/'series.zip',self.item,cancel)
        self.assertFalse((self.root/'series.zip').exists());self.assertFalse(list(self.root.glob('*.zip.part')))
    def test_archive_write_failure_cleans_partial(self):
        source=self.root/'episode.mp4';source.write_bytes(b'video')
        with patch('downloaders.hianime_series.zipfile.ZipFile',side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):write_archive([source],self.root/'series.zip',self.item,lambda *a,**k:None)
        self.assertFalse(list(self.root.glob('*.zip.part')))
    def test_job_identifier_persists_for_resume(self):
        restored=validate_batch(URL,self.item.series)
        self.assertEqual(restored['job_id'],self.item.series['job_id'])
    def test_arbitrary_episode_urls_are_rebuilt(self):
        info=batch();info['episodes'][0]['url']='http://127.0.0.1/private'
        self.assertTrue(validate_batch(URL,info)['episodes'][0]['url'].startswith('https://hianime.at/watch/'))
    def test_empty_and_duplicate_episode_lists_rejected(self):
        for entries in [[],[batch()['episodes'][0]]*2]:
            with self.assertRaises(ValueError):validate_batch(URL,{'episodes':entries})
    def test_paused_queue_preserves_batch_and_zip_choice_on_disk(self):
        qm=QueueManager();key=qm.add(URL,'Series','HiAnime','','best','1080p',str(self.root),'hianime_series',start_paused=True,series=self.item.series)
        with patch.object(queue_persistence,'_STATE_FILE',self.root/'queue.json'):
            queue_persistence.save_queue(qm.get_items());records=queue_persistence.load_queue()
        self.assertTrue(records[0]['series']['zip']);self.assertEqual(records[0]['series']['job_id'],self.item.series['job_id'])

class SeriesAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_discover_then_queue_paused_and_snapshot_retains_archive_choice(self):
        import queue
        import threading
        from core.engine import EngineFacade
        from core.ui_server import UIServer
        engine=EngineFacade.__new__(EngineFacade)
        engine._cfg={'save_path':'.'};engine._qm=QueueManager()
        engine._history=[];engine._events=queue.Queue();engine._lock=threading.Lock()
        server=UIServer(engine,{'ui_token':'test-token'})
        try:
            async def send(action,**data):
                return await server._dispatch(json.dumps({'token':'test-token','action':action,**data}))
            detected=await send('detect',url=URL)
            self.assertTrue(detected['detection']['series_capable'])
            metadata={**batch(), 'count':3}
            with patch('downloaders.hianime_series.inspect_series',return_value=metadata):
                discovered=await send('inspect_series',url=URL)
            self.assertEqual(discovered['series']['count'],3)
            added=await send('add',url=URL,opts={'dl_type':'hianime_series','series':metadata,'start_paused':True})
            self.assertTrue(added['ok'])
            snapshot=await send('snapshot')
            self.assertEqual(snapshot['items'][0]['state'],'Paused')
            self.assertTrue(snapshot['items'][0]['series']['zip'])
            self.assertEqual(len(snapshot['items'][0]['series']['episodes']),3)
        finally:server.stop()

    async def test_invalid_batch_rejected_before_queueing(self):
        from core.engine import EngineFacade
        engine=EngineFacade.__new__(EngineFacade);engine._cfg={};engine._qm=QueueManager()
        with self.assertRaises(ValueError):engine.add(URL,{'dl_type':'hianime_series','series':{'episodes':[]}})
        self.assertEqual(engine.snapshot(),[])
