import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[2])]
from tests import isolated_webapp

# Route tests use a private module instance, not the shared app import whose
# cached authentication paths may point at production during discovery.
with isolated_webapp("cari_api_test_app") as app:
    pass



class Handler:
    _route_cari = app.Handler._route_cari
    _cari_sahibi = app.Handler._cari_sahibi
    headers = {}

    def __init__(self, *, authenticated=True, csrf=True):
        self.session = SimpleNamespace(username='test-operator') if authenticated else None
        self.csrf = csrf
        self.response = None

    def _current_session(self):
        return self.session

    def _require_csrf(self, session):
        return self.csrf

    def _send_json(self, status, body, *unused):
        self.response = status, body


class CariApiTests(unittest.TestCase):
    def test_get_and_post_require_existing_session(self):
        handler = Handler(authenticated=False)
        with patch.object(app.cari, 'list_accounts') as reader, patch.object(app.cari, 'create_account') as writer:
            app.Handler._route_api_get(handler, '/api/cari/accounts', {})
            self.assertEqual(handler.response[0], 401)
            app.Handler._route_api_post(handler, '/api/cari/accounts')
            self.assertEqual(handler.response[0], 401)
        reader.assert_not_called()
        writer.assert_not_called()

    def test_post_requires_existing_csrf_boundary(self):
        handler = Handler(csrf=False)
        with patch.object(app.cari, 'post_entry') as writer:
            app.Handler._route_api_post(handler, '/api/cari/entries')
        self.assertEqual(handler.response[0], 403)
        writer.assert_not_called()

    def test_read_owner_comes_from_session(self):
        handler = Handler()
        with patch.object(app.cari, 'list_accounts', return_value={'accounts': []}) as reader:
            app.Handler._route_api_get(handler, '/api/cari/accounts', {'owner': ['someone-else']})
        reader.assert_called_once_with('test-operator')
        self.assertEqual(handler.response, (200, {'accounts': []}))

    def test_overview_is_owner_scoped_and_accepts_explicit_report_date(self):
        handler = Handler()
        with patch.object(app.cari, 'portfolio', return_value={'as_of': '2026-02-15'}) as reader:
            app.Handler._route_api_get(handler, '/api/cari/overview',
                {'owner': ['someone-else'], 'as_of': ['2026-02-15']})
        reader.assert_called_once_with('test-operator', '2026-02-15')
        self.assertEqual(handler.response[0], 200)

    def test_channel_read_and_observation_use_the_session_owner(self):
        handler = Handler()
        with patch.object(app.cari_channels, 'board', return_value={'orders': []}) as reader:
            app.Handler._route_api_get(handler, '/api/cari/channels', {'owner': ['other']})
        reader.assert_called_once_with('test-operator')
        body = {'owner': 'other', 'source': 'wix'}
        with patch.object(app, '_read_json_body', return_value=body), \
             patch.object(app.cari_channels, 'observe', return_value={'id':'test'}) as writer:
            app.Handler._route_api_post(handler, '/api/cari/channels/observe')
        writer.assert_called_once_with('test-operator', body)

    def test_post_owner_comes_from_session_and_malformed_body_is_rejected(self):
        handler = Handler()
        body = {'owner': 'someone-else', 'account_id': 'abc'}
        with patch.object(app, '_read_json_body', return_value=body), \
             patch.object(app.cari, 'post_entry', return_value={'id': 'entry'}) as writer:
            app.Handler._route_api_post(handler, '/api/cari/entries')
        writer.assert_called_once_with('test-operator', 'abc', body)
        with patch.object(app, '_read_json_body', return_value=[]):
            app.Handler._route_api_post(handler, '/api/cari/entries')
        self.assertEqual(handler.response[0], 400)

    def test_edit_routes_keep_session_owner_and_account_id(self):
        handler = Handler()
        body = {'account_id': 'account', 'owner': 'someone-else'}
        with patch.object(app, '_read_json_body', return_value=body), \
             patch.object(app.cari, 'update_account', return_value={'id': 'account'}) as update:
            app.Handler._route_api_post(handler, '/api/cari/accounts/update')
        update.assert_called_once_with('test-operator', 'account', body)
        with patch.object(app, '_read_json_body', return_value=body), \
             patch.object(app.cari, 'correct_entry', return_value={'id': 'entry'}) as correct:
            app.Handler._route_api_post(handler, '/api/cari/correct')
        correct.assert_called_once_with('test-operator', 'account', body)

    def test_invoice_review_routes_use_session_owner_and_csrf(self):
        handler = Handler()
        with patch.object(app.cari_invoice, 'list_documents', return_value={'documents': []}) as reader:
            app.Handler._route_api_get(handler, '/api/cari/documents', {'account_id': ['account']})
        reader.assert_called_once_with('test-operator', 'account')
        body = {'id': 'invoice-id', 'extracted': {'buyer': {'name': 'Buyer'}}}
        with patch.object(app, '_read_json_body', return_value=body), \
             patch.object(app.cari_invoice, 'approve', return_value={'status': 'posted'}) as writer:
            app.Handler._route_api_post(handler, '/api/cari/documents/approve')
        writer.assert_called_once_with('test-operator', 'invoice-id', body['extracted'])
        handler.csrf = False
        with patch.object(app.cari_invoice, 'approve') as denied:
            app.Handler._route_api_post(handler, '/api/cari/documents/approve')
        self.assertEqual(handler.response[0], 403)
        denied.assert_not_called()

    def test_draft_approval_uses_session_owner(self):
        handler = Handler()
        body = {'account_id': 'account', 'draft_id': 'draft'}
        with patch.object(app, '_read_json_body', return_value=body), \
             patch.object(app.cari_draft, 'post', return_value={'id': 'entry'}) as writer:
            app.Handler._route_api_post(handler, '/api/cari/drafts/post')
        writer.assert_called_once_with('test-operator', 'account', 'draft')
        self.assertEqual(handler.response[0], 200)

    def test_preview_never_posts_a_financial_entry(self):
        handler = Handler()
        with patch.object(app.cari, 'post_entry') as writer:
            handler._route_cari('/api/cari/preview', handler.session,
                                body={'kind': 'collection', 'date': '2026-01-10', 'amount': '12.34'})
        writer.assert_not_called()
        self.assertEqual(handler.response[0], 200)
        self.assertEqual(handler.response[1]['signed_cents'], -1234)

    def test_missing_conflicting_and_invalid_inputs_are_distinguished(self):
        for exception, status in ((app.cari.CariNotFound('missing'), 404),
                                  (app.cari.CariConflict('conflict'), 409),
                                  (app.cari.CariError('invalid'), 400)):
            handler = Handler()
            with self.subTest(status=status), patch.object(app.cari, 'list_accounts', side_effect=exception):
                handler._route_cari('/api/cari/accounts', handler.session, query={})
            self.assertEqual(handler.response[0], status)

    def test_database_errors_do_not_disclose_internal_information(self):
        handler = Handler()
        with patch.object(app.cari, 'list_accounts', side_effect=RuntimeError('private database details')), \
             patch.object(app.traceback, 'print_exc'):
            handler._route_cari('/api/cari/accounts', handler.session, query={})
        self.assertEqual(handler.response[0], 503)
        self.assertNotIn('private database', str(handler.response))


if __name__ == '__main__':
    unittest.main()
