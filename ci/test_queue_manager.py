"""Concurrency regressions: each download starts once and respects the limit."""
import collections
import pathlib
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from core.queue_manager import QueueManager


class QueueTests(unittest.TestCase):
    def test_waiting_items_run_once(self):
        release = threading.Event()
        started = threading.Event()
        counts = collections.Counter()
        def download(item, progress):
            counts[item.id] += 1
            started.set()
            release.wait(3)
        queue = QueueManager(max_concurrent=1)
        with patch('downloaders.router.run_download', side_effect=download):
            ids = [queue.add('https://example.com/file', '', '', '', 'best', '', '.', 'direct')]
            self.assertTrue(started.wait(2))
            ids.extend(queue.add('https://example.com/file', '', '', '', 'best', '', '.', 'direct') for _ in range(2))
            release.set()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and any(i.state != 'Complete' for i in queue.get_items()):
                time.sleep(.01)
            time.sleep(.1)
            self.assertEqual(counts, collections.Counter({i: 1 for i in ids}))

    def test_changing_limit_keeps_running_jobs_counted(self):
        release = threading.Event()
        started = threading.Event()
        second = threading.Event()
        def download(item, progress):
            (started if item.title == 'first' else second).set()
            release.wait(3)
        queue = QueueManager(max_concurrent=1)
        with patch('downloaders.router.run_download', side_effect=download):
            queue.add('https://example.com/a', 'first', '', '', 'best', '', '.', 'direct')
            self.assertTrue(started.wait(2))
            queue.add('https://example.com/b', 'second', '', '', 'best', '', '.', 'direct')
            queue.set_concurrency(1)
            premature = second.wait(.2)
            release.set()
            self.assertTrue(second.wait(2))
            for item in queue.get_items():
                if item._thread: item._thread.join(timeout=2)
            self.assertFalse(premature, 'Changing concurrency started a second job above the limit')


if __name__ == '__main__':
    unittest.main()
