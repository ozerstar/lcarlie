import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from test_web_integration import app


class ImprovementApiTests(unittest.TestCase):
    def handler(self, session=True, csrf=True):
        h=object.__new__(app.Handler)
        h._current_session=Mock(return_value=SimpleNamespace(username='real-operator') if session else None)
        h._require_csrf=Mock(return_value=csrf)
        h._send_json=Mock()
        return h

    def test_get_requires_auth(self):
        h=self.handler(session=False)
        h._route_api_get('/api/improvement',{})
        self.assertEqual(h._send_json.call_args.args[0],401)

    def test_post_requires_auth(self):
        h=self.handler(session=False)
        h._route_api_post('/api/improvement')
        self.assertEqual(h._send_json.call_args.args[0],401)

    def test_post_requires_csrf(self):
        h=self.handler(csrf=False)
        h._route_api_post('/api/improvement')
        self.assertEqual(h._send_json.call_args.args[0],403)

    def test_authenticated_get(self):
        h=self.handler()
        with patch('jarvis.improvement.Store') as store:
            store.return_value.snapshot.return_value={'works':[]}
            h._route_api_get('/api/improvement',{})
        self.assertEqual(h._send_json.call_args.args,(200,{'works':[]}))

    def test_authenticated_post_uses_session_actor(self):
        h=self.handler()
        with patch('jarvis.improvement.Store') as store,patch.object(app,'_read_json_body',return_value={'operation':'correction'}):
            store.return_value.operation.return_value={'ok':True}
            h._route_api_post('/api/improvement')
            store.return_value.operation.assert_called_once_with({'operation':'correction'},'real-operator')
        self.assertEqual(h._send_json.call_args.args[0],200)

    def test_invalid_measurement_is_400(self):
        h=self.handler()
        with patch('jarvis.improvement.Store') as store,patch.object(app,'_read_json_body',return_value={}):
            store.return_value.operation.side_effect=ValueError('missing evidence')
            h._route_api_post('/api/improvement')
        self.assertEqual(h._send_json.call_args.args[0],400)
