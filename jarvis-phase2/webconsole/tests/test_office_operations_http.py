"""HTTP security and persistent update contract. No production database access."""
import unittest
from unittest.mock import patch
from webconsole.tests import test_web_integration as base
from jarvis import roster

class OfficeHTTPTests(unittest.TestCase):
    setUpClass = classmethod(base.WebConsoleIntegrationTests.setUpClass.__func__)
    tearDownClass = classmethod(base.WebConsoleIntegrationTests.tearDownClass.__func__)
    setUp = base.WebConsoleIntegrationTests.setUp
    _get = base.WebConsoleIntegrationTests._get
    _post = base.WebConsoleIntegrationTests._post
    _login = base.WebConsoleIntegrationTests._login

    def test_office_requires_session(self):
        with patch.object(base.app, '_office_snapshot') as snapshot:
            response,_ = self._get('/api/panel/ofis')
            self.assertEqual(response.status,401)
            snapshot.assert_not_called()

    def test_mutations_require_csrf(self):
        _,session=self._login()
        for path in ('followup','source-check','acknowledge'):
            with self.subTest(path=path), patch.object(base.app, '_office_snapshot') as snapshot:
                response,_ = self._post('/api/office/'+path,{}, {'Cookie':base.app.SESSION_COOKIE+'='+session})
                self.assertEqual(response.status,403)
                snapshot.assert_not_called()

    def test_update_roundtrip_and_conflict(self):
        csrf,session=self._login()
        headers={'Cookie':base.app.SESSION_COOKIE+'='+session,'X-CSRF-Token':csrf}
        team=roster.departman_uyeleri()['WEB']
        item=dict(id='http-test',title='Kaynak kapsamı',detail='Kaydı inceleyin',source='Şirket kaydı',fingerprint='http-test',version=0,status='open')
        body=dict(id=item['id'],department='WEB',owner=team[0].key,due='2026-11-05',status='progress',version=0,note='İnceleme planlandı.')
        with patch.object(base.app, '_office_snapshot',return_value={'items':[item]}):
            response,data=self._post('/api/office/followup',body,headers)
            self.assertEqual(response.status,200)
            self.assertEqual(data['version'],1)
            response,data=self._post('/api/office/followup',body,headers)
            self.assertEqual(response.status,409)
            self.assertIn('değişti',data['error'])

if __name__=='__main__':
    unittest.main()
