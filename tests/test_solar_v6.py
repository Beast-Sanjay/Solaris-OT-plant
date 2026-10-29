"""Regressions for writable conduit, field maintenance, and public data isolation."""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'))

class FunctionalV6(unittest.TestCase):
    def test_control_conduit_fails_closed(self):
        with patch.dict(os.environ,{'TARGET_URL':'http://127.0.0.1:1','ALLOWED_PATHS':'/api/limit',
                 'ALLOWED_METHODS':'GET,POST','CONDUIT_AUTH_TOKEN':'secret','CONDUIT_AUTH_HEADER':'X-PPC-Token',
                 'CONDUIT_ALLOW_UNAUTH_POST':'false'}):
            import http_relay
            h=importlib.reload(http_relay)
            self.assertTrue(h.allowed('POST','/api/limit'))
            self.assertFalse(h.allowed('POST','/api/trip'))
            self.assertFalse(h.authorized('POST','wrong'))
            self.assertFalse(h.authorized('POST',''))
            self.assertTrue(h.authorized('POST','secret'))
            self.assertTrue(h.authorized('GET',''))

    def test_soc_explicit_telemetry_exception(self):
        with patch.dict(os.environ,{'TARGET_URL':'http://127.0.0.1:1','ALLOWED_PATHS':'/api/events',
                 'ALLOWED_METHODS':'POST','CONDUIT_ALLOW_UNAUTH_POST':'true'},clear=True):
            import http_relay
            h=importlib.reload(http_relay)
            self.assertTrue(h.authorized('POST',''))
            self.assertFalse(h.allowed('POST','/api/trip'))

    def test_field_service_persists_soiling_and_strings(self):
        import solar_array as array
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'array.json')
            with patch.object(array,'STATE_FILE',path):
                with patch.object(array,'STRINGS',36):
                    result=array.service('inject_soiling',15)
                    self.assertEqual(result['soiling_pct'],15)
                    array.service('disconnect_strings',4)
                    saved=json.loads(Path(path).read_text())
                    self.assertEqual(saved,{'soiling_pct':15,'failed_strings':4})
                    array.service('repair_strings')
                    array.service('clean')
                    self.assertEqual(json.loads(Path(path).read_text())['failed_strings'],0)
                    self.assertEqual(array.state['soiling_pct'],0.5)
                    with self.assertRaises(ValueError):array.service('disconnect_strings',99)

    def test_public_strict_allowlist(self):
        import solar_public as pub
        raw={'time':100.0,'generation_kw':6600,'export_kw':6200,'online_inverters':4,
             'irradiance_w_m2':930,'alarm_count':0,'private_ip':'192.168.95.21','password':'not_for_public'}
        sanitized=pub.sanitize(raw)
        self.assertAlmostEqual(sanitized['export_mw'],6.2)
        self.assertNotIn('private_ip',sanitized)
        self.assertNotIn('password',sanitized)
        self.assertTrue(sanitized['status']=='NORMAL')
        self.assertEqual(pub.sanitize({**raw,'export_kw':20000})['export_mw'],6.6)

    def test_realistic_asset_contracts_and_web(self):
        import yaml
        root=Path(__file__).resolve().parents[1]
        s=yaml.safe_load((root/'compose.yaml').read_text())['services']
        for i in range(1,5):
            c=s[f'inverter-conduit-{i:02d}']
            self.assertEqual(c['environment']['CONDUIT_AUTH_HEADER'],'X-PPC-Token')
            self.assertIn('CONDUIT_AUTH_TOKEN',c['environment'])
            self.assertIn('STATE_FILE',s[f'pv-array-{i:02d}']['environment'])
        self.assertEqual(s['soc-conduit']['environment']['CONDUIT_ALLOW_UNAUTH_POST'],'true')
        self.assertEqual(s['field-service']['networks'],['level0'])
        self.assertEqual(set(s['public-publisher']['networks']),{'web_dmz','idmz'})
        website=(root/'docs/web/index.html').read_text()
        self.assertIn('/api/public/history',(root/'docs/web/app.js').read_text())
        self.assertNotIn('/api/control',website)
        nginx=(root/'docs/web/nginx.conf').read_text()
        self.assertIn('location = /api/public',nginx)
        self.assertIn('location / { return 404; }',nginx)

if __name__=='__main__':unittest.main()
