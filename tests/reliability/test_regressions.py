"""Deterministic regression tests. Mocked providers do NOT establish live parity."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from src.brain.channels.runtime_state import RuntimeState, owner_allowed, confined_file, process_request

ROOT = Path(__file__).resolve().parents[2]
HAS_FASTAPI = importlib.util.find_spec('fastapi') is not None


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = RuntimeState(self.root / 'state.db')

    def test_owner_private_only(self):
        self.assertTrue(owner_allowed({'chat': {'type': 'private', 'id': 7}, 'from': {'id': 7}}, '7'))

    def test_other_user_rejected(self):
        self.assertFalse(owner_allowed({'chat': {'type': 'private', 'id': 8}, 'from': {'id': 8}}, '7'))

    def test_group_rejected(self):
        self.assertFalse(owner_allowed({'chat': {'type': 'group', 'id': 7}, 'from': {'id': 7}}, '7'))

    def test_missing_owner_fails_closed(self):
        self.assertFalse(owner_allowed({}, ''))

    def test_history_survives_restart(self):
        self.state.remember('7', 'первый вариант', 'ответ')
        restarted = RuntimeState(self.root / 'state.db')
        self.assertEqual(restarted.get('history:7')[1]['content'], 'ответ')

    def test_history_is_bounded_and_separated(self):
        for i in range(20):
            self.state.remember('7', str(i), 'ok')
        self.assertEqual(len(self.state.get('history:7')), 12)
        self.assertIsNone(self.state.get('history:8'))

    def test_update_deduplication(self):
        self.state.enqueue({'update_id': 10})
        self.state.enqueue({'update_id': 10})
        self.state.finish(10, True)
        self.assertIsNone(self.state.next_update())

    def test_offset_never_moves_backwards(self):
        self.state.enqueue({'update_id': 20})
        self.state.enqueue({'update_id': 10})
        self.assertEqual(self.state.get('offset'), 21)

    def test_pending_survives_restart(self):
        self.state.enqueue({'update_id': 9, 'message': {'text': 'hello'}})
        self.assertEqual(RuntimeState(self.root / 'state.db').next_update()[0], 9)

    def test_delivery_retry_is_bounded(self):
        self.state.enqueue({'update_id': 10})
        for _ in range(3):
            self.state.finish(10, False)
        self.assertIsNone(self.state.next_update())
        with self.state.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM telegram_inbox').fetchone()[0], 'failed')

    def test_existing_upload_allowed(self):
        file = self.root / 'image.jpg'
        file.write_bytes(b'fixture')
        self.assertEqual(confined_file(file, self.root), file)

    def test_outside_file_rejected(self):
        with self.assertRaises(ValueError):
            confined_file(__file__, self.root)

    def test_symlink_escape_rejected(self):
        link = self.root / 'escape'
        try:
            link.symlink_to(Path(__file__).resolve())
        except OSError:
            self.skipTest('Symlinks unavailable on this platform')
        with self.assertRaises(ValueError):
            confined_file(link, self.root)

    def test_provider_error_not_returned_as_success(self):
        brain = Mock()
        brain.process_chat.return_value = {'status_code': 500, 'response': 'provider error'}
        with self.assertRaises(RuntimeError):
            process_request(brain, 'hello', self.root)

    def test_failed_vision_stops_generation(self):
        file = self.root / 'test.jpg'
        file.write_bytes(b'fixture')
        brain = Mock()
        brain.shooting_engine.critique_shot.return_value = {'status': 'ERROR'}
        with self.assertRaises(ValueError):
            process_request(brain, 'describe', self.root, images=[str(file)])
        brain.process_chat.assert_not_called()

    def test_excess_images_rejected(self):
        with self.assertRaises(ValueError):
            process_request(Mock(), 'describe', self.root, images=['x'] * 5)

    def test_history_forwarded_without_duplicate_current_turn(self):
        brain = Mock()
        brain.process_chat.return_value = {'status_code': 200, 'response': 'ok'}
        history = [{'role': 'user', 'content': 'previous'}]
        process_request(brain, 'current', self.root, conversation_history=history)
        self.assertEqual(brain.process_chat.call_args.kwargs['conversation_history'], history)
        self.assertEqual(brain.process_chat.call_args.kwargs['query'], 'current')


class AudioTests(unittest.TestCase):
    def setUp(self):
        from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'voice.ogg'
        self.file.write_bytes(b'not-real-audio')
        self.extractor = AudioExtractor()

    def test_missing_file_fails(self):
        result = self.extractor.extract(self.root / 'missing.ogg', 'test', self.root / 'derived')
        self.assertFalse(result.success)
        self.assertEqual(result.raw_text, '')

    def test_transcriber_failure_never_fabricates_text(self):
        with patch.object(self.extractor, 'normalize_audio', return_value=False), patch.object(
                self.extractor, '_transcribe_with_whisper', side_effect=RuntimeError('unavailable')):
            result = self.extractor.extract(self.file, 'test', self.root / 'derived')
        self.assertFalse(result.success)
        self.assertEqual(result.raw_text, '')

    def test_empty_transcript_fails(self):
        with patch.object(self.extractor, 'normalize_audio', return_value=False), patch.object(
                self.extractor, '_transcribe_with_whisper', return_value=([], 'ru')):
            result = self.extractor.extract(self.file, 'test', self.root / 'derived')
        self.assertFalse(result.success)

    def test_production_ignores_sidecars(self):
        sidecar = self.file.with_suffix('.ogg.transcript.json')
        sidecar.write_text(json.dumps({'segments': [{'start': 0, 'end': 1, 'text': 'fake'}]}))
        with patch.object(self.extractor, 'normalize_audio', return_value=False), patch.object(
                self.extractor, '_transcribe_with_whisper', side_effect=RuntimeError('unavailable')):
            result = self.extractor.extract(self.file, 'test', self.root / 'derived')
        self.assertFalse(result.success)
        self.assertNotIn('fake', result.raw_text)

    def test_explicit_fixture_mode(self):
        sidecar = self.file.with_suffix('.ogg.transcript.json')
        sidecar.write_text(json.dumps({'segments': [{'start': 0, 'end': 1, 'text': 'fixture only'}]}))
        self.extractor.allow_sidecar = True
        result = self.extractor.extract(self.file, 'test', self.root / 'derived')
        self.assertTrue(result.success)
        self.assertEqual(result.media_info['source'], 'sidecar')


@unittest.skipUnless(HAS_FASTAPI, 'FastAPI is not installed in this execution environment')
class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BRAIN_API_KEY': 'regression-only-not-a-production-key-0001'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_valid_bearer(self):
        from src.brain.api.security import verify_brain_api_key
        self.assertTrue(verify_brain_api_key('Bearer ' + os.environ['BRAIN_API_KEY']))

    def test_legacy_test_tokens_rejected(self):
        from fastapi import HTTPException
        from src.brain.api.security import verify_brain_api_key
        with self.assertRaises(HTTPException) as caught:
            verify_brain_api_key('Bearer valid-test-token')
        self.assertEqual(caught.exception.status_code, 401)

    def test_cookie_cannot_authenticate(self):
        from fastapi import HTTPException
        from src.brain.api.security import verify_brain_api_key
        with self.assertRaises(HTTPException):
            verify_brain_api_key(brain_token=os.environ['BRAIN_API_KEY'])

    def test_missing_configuration_fails_closed(self):
        from fastapi import HTTPException
        from src.brain.api.security import verify_brain_api_key
        with patch.dict(os.environ, {'BRAIN_API_KEY': ''}), self.assertRaises(HTTPException) as caught:
            verify_brain_api_key('Bearer anything')
        self.assertEqual(caught.exception.status_code, 503)

    def test_api_boundaries(self):
        from fastapi.testclient import TestClient
        from src.brain.api.app import app
        with TestClient(app) as client:
            for path in ['/brain/profile', '/api/uploads/example.jpg', '/health/ready']:
                self.assertEqual(client.get(path).status_code, 401, path)
            for path in ['/api/upload', '/api/upload_knowledge', '/knowledge/sources']:
                self.assertEqual(client.post(path).status_code, 401, path)
            page = client.get('/')
            self.assertEqual(page.status_code, 200)
            self.assertNotIn(os.environ['BRAIN_API_KEY'], page.text)
            self.assertNotIn('set-cookie', page.headers)
            self.assertIn('Content-Security-Policy', page.headers)
            result = client.get('/brain/profile', headers={'Authorization': 'Bearer ' + os.environ['BRAIN_API_KEY']})
            self.assertEqual(result.status_code, 200)


class BrowserSafetyTests(unittest.TestCase):
    def test_no_html_interpolation_or_persistent_secret_storage(self):
        page = (ROOT / 'src/brain/web/index.html').read_text(encoding='utf-8')
        for forbidden in ['innerHTML', 'localStorage', 'sessionStorage', 'brain-secure-stage', 'onclick=']:
            self.assertNotIn(forbidden, page)
        self.assertIn('textContent', page)


if __name__ == '__main__':
    unittest.main()
