"""Offline boundary tests for network guards and download filenames."""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from utils import net_guard as guard
from downloaders.direct_downloader import _sanitize_filename, _get_filename, _contain, _unique_path


class NetworkTests(unittest.TestCase):
    def test_private_and_invalid_addresses(self):
        for address in ('127.0.0.1', '10.0.0.1', '172.16.0.1', '192.168.1.1',
                        '169.254.169.254', '100.64.0.1', '0.0.0.0', '224.0.0.1',
                        '::1', 'fc00::1', 'fe80::1', '::ffff:127.0.0.1', 'invalid'):
            with self.subTest(address=address):
                self.assertTrue(guard._is_blocked_ip(address))

    def test_public_addresses(self):
        for address in ('1.1.1.1', '8.8.8.8', '2606:4700:4700::1111'):
            with self.subTest(address=address):
                self.assertFalse(guard._is_blocked_ip(address))

    def test_mixed_dns_answers_rejected(self):
        with patch.object(guard, '_resolve_all', return_value={'8.8.8.8', '127.0.0.1'}):
            with self.assertRaises(guard.BlockedAddressError):
                guard.assert_url_allowed('https://example.com/file')

    def test_dns_failure_and_empty_answers_fail_closed(self):
        for answers in (set(), None):
            with self.subTest(answers=answers), patch.object(guard, '_resolve_all', return_value=answers):
                with self.assertRaises(guard.BlockedAddressError):
                    guard.assert_url_allowed('https://example.com')
        with patch.object(guard, '_resolve_all', side_effect=OSError('offline')):
            with self.assertRaises(guard.BlockedAddressError):
                guard.assert_url_allowed('https://example.com')

    def test_missing_host_rejected(self):
        for url in ('', '/file', 'https:///file'):
            with self.subTest(url=url), self.assertRaises(guard.BlockedAddressError):
                guard.assert_url_allowed(url)

    def test_website_origins_rejected(self):
        for origin in ('https://evil.example', 'http://localhost.evil.example', 'http://127.0.0.1.evil.example'):
            with self.subTest(origin=origin):
                self.assertFalse(guard.ws_origin_allowed(origin))

    def test_local_and_extension_origins_allowed(self):
        for origin in (None, 'null', 'file://', 'http://127.0.0.1:52829', 'http://localhost:8000', 'chrome-extension://test'):
            with self.subTest(origin=origin):
                self.assertTrue(guard.ws_origin_allowed(origin))

    def test_redirect_to_private_host_blocked(self):
        session = Mock()
        response = Mock(is_redirect=True, headers={'Location': 'http://127.0.0.1/secret'})
        session.request.return_value = response
        with patch.object(guard, '_resolve_all', return_value={'8.8.8.8'}):
            with self.assertRaises(guard.BlockedAddressError):
                guard.safe_request('GET', 'https://example.com', session=session)
        self.assertEqual(session.request.call_count, 1)
        response.close.assert_called_once()

    def test_relative_redirect_followed_and_checked(self):
        session = Mock()
        redirect = Mock(is_redirect=True, headers={'Location': '/next'})
        final = Mock(is_redirect=False)
        session.request.side_effect = [redirect, final]
        with patch.object(guard, 'assert_url_allowed') as check:
            self.assertIs(guard.safe_request('GET', 'https://example.com/start', session=session), final)
            self.assertEqual([c.args[0] for c in check.call_args_list], ['https://example.com/start', 'https://example.com/next'])

    def test_redirect_loop_bounded(self):
        session = Mock()
        session.request.return_value = Mock(is_redirect=True, headers={'Location': '/again'})
        with patch.object(guard, 'assert_url_allowed'), self.assertRaises(guard.BlockedAddressError):
            guard.safe_request('GET', 'https://example.com', session=session)
        self.assertEqual(session.request.call_count, guard.SAFE_MAX_REDIRECTS + 1)

    def test_proxy_resolution_delegated(self):
        session = Mock()
        session.request.return_value = Mock(is_redirect=False)
        with patch.object(guard, 'assert_url_allowed') as check:
            guard.safe_request('GET', 'https://example.com', proxies={'https':'http://proxy.example:8080'}, session=session)
            check.assert_not_called()


class FilenameTests(unittest.TestCase):
    def test_paths_and_illegal_characters_sanitized(self):
        for name in ('../../secret.txt', r'C:\Windows\secret.txt', '/etc/passwd', 'a<>:"|?*.txt', '..', '', '\x00'):
            with self.subTest(name=name):
                result = _sanitize_filename(name)
                self.assertTrue(result)
                self.assertFalse(any(c in result for c in '<>:"/\\|?*\x00'))
                self.assertNotIn(result, ('.', '..'))

    def test_reserved_windows_names_sanitized(self):
        for name in ('CON', 'con.txt', 'NUL.zip', 'AUX', 'PRN', 'COM1.mp4', 'LPT9.txt'):
            with self.subTest(name=name):
                self.assertNotEqual(_sanitize_filename(name).split('.')[0].upper(), name.split('.')[0].upper())

    def test_unicode_filename_and_length(self):
        self.assertEqual(_sanitize_filename('日本語 café.mp4'), '日本語 café.mp4')
        self.assertLessEqual(len(_sanitize_filename('a'*250+'.mp4')), 200)

    def test_header_and_content_type_names(self):
        cases = [
            ({'Content-Disposition': 'attachment; filename="report.pdf"'}, 'report.pdf'),
            ({'Content-Disposition': "attachment; filename*=UTF-8''caf%C3%A9.pdf"}, 'café.pdf'),
            ({'Content-Type': 'image/png; charset=utf-8'}, 'download.png'),
        ]
        for headers, expected in cases:
            with self.subTest(headers=headers):
                self.assertEqual(_get_filename('https://example.com/resource', headers), expected)

    def test_url_name_without_query(self):
        self.assertEqual(_get_filename('https://example.com/file%20name.zip?token=test', {}), 'file name.zip')

    def test_path_containment_and_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.assertEqual(pathlib.Path(_contain(directory, str(root.parent / 'outside.txt'))).resolve(), (root/'download.bin').resolve())
            (root/'file.txt').write_text('original')
            self.assertEqual(pathlib.Path(_unique_path(directory,'file.txt')).name, 'file (1).txt')


if __name__ == '__main__':
    unittest.main()
