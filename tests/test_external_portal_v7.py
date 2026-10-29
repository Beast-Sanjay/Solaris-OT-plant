"""External website contracts: real data, no OT operations, persistent support workflow."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'))

class PublicPortalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'PUBLIC_DB':str(Path(self.tmp.name)/'portal.sqlite3'),
                                     'PUBLIC_SALT':'test-only-secret', 'PUBLIC_ADMIN_TOKEN':'test-only-admin',
                                     'PUBLIC_POLL_SECONDS':'30'})
        self.env.start()
        import solar_public
        self.mod=importlib.reload(solar_public)
        self.mod.initialize()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_ticket_lifecycle_is_persistent_and_private(self):
        pub=self.mod
        req={'full_name':'Solar Visitor','email':'person@example.com','category':'site_visit',
             'message':'I would like a technical tour of the solar training lab.'}
        ticket=pub.enquiries_submit(req,'198.18.0.16')
        self.assertRegex(ticket['reference'],r'^SOL-[A-F0-9]{12}$')
        self.assertNotIn('access_hash', ticket)
        self.assertIsNone(pub.track_enquiry(ticket['reference'],'wrong_code'))
        self.assertEqual(pub.track_enquiry(ticket['reference'],ticket['access_code'])['status'],'received')
        self.assertEqual(pub.staff_list()[0]['email'],'person@example.com')
        pub.staff_update({'reference':ticket['reference'],'status':'under_review'})
        pub.staff_update({'reference':ticket['reference'],'status':'responded','response':'You can visit during the virtual demo.'})
        t=pub.track_enquiry(ticket['reference'],ticket['access_code'])
        self.assertEqual(t['status'],'responded')
        self.assertIn('virtual demo',t['response'])
        pub.staff_update({'reference':ticket['reference'],'status':'closed'})
        self.assertEqual(pub.track_enquiry(ticket['reference'],ticket['access_code'])['status'],'closed')
        with pub.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM enquiries').fetchone()[0],1)
        with self.assertRaises(ValueError):pub.staff_update({'reference':ticket['reference'],'status':'received'})

    def test_rate_limit_and_field_validation(self):
        m=self.mod
        good={'full_name':'Solar User','email':'solar@example.com','category':'general',
              'message':'Requesting public solar plant data.'}
        with self.assertRaises(ValueError):m.enquiries_submit({**good,'category':'scada_control'},'127.0.0.3')
        with self.assertRaises(ValueError):m.enquiries_submit({**good,'message':'<short>'},'127.0.0.3')
        with self.assertRaises(ValueError):m.enquiries_submit({**good,'website':'spam.com'},'127.0.0.3')
        for _ in range(5):m.enquiries_submit(good,'127.0.0.3')
        with self.assertRaises(RuntimeError):m.enquiries_submit(good,'127.0.0.3')
        # Other visitor can still create one.
        self.assertTrue(m.enquiries_submit(good,'127.0.0.4')['ok'])

    def test_notice_management_is_persistent(self):
        m=self.mod
        r=m.staff_notice({'title':'Public solar demonstration','message':'Digital twin demonstration available.',
                          'severity':'information'})
        self.assertEqual(len(m.public_notices()),1)
        self.assertEqual(m.public_notices()[0]['title'],'Public solar demonstration')
        m.staff_notice_close({'id':r['id']})
        self.assertEqual(m.public_notices(),[])

    def test_live_sanitization_and_energy_excludes_gaps(self):
        m=self.mod
        now=int(time.time())
        sample={'time':now-5,'generation_kw':8900,'export_kw':8000,'irradiance_w_m2':921,
                'alarm_count':0,'online_inverters':4,'plc_ip':'192.168.95.11','control_token':'secret'}
        with patch('solar_public.time.time',return_value=now):
            m.update_from_historian(sample,[sample],now=now)
        self.assertTrue(m.public['online'])
        self.assertNotIn('plc_ip',m.public)
        self.assertNotIn('control_token',m.public)
        utc_start=__import__('datetime').datetime.fromtimestamp(now,__import__('datetime').timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        base=int(max(utc_start+100,now-3600))
        with m.connect() as db:
            db.execute('DELETE FROM telemetry')
            db.executemany('INSERT INTO telemetry VALUES(?,?,?,?)',[(base,7.0,6.0,800),
                      (base+30,7.0,6.0,800),(base+600,7.0,6.0,800)])
        stats=m.public_statistics(now=max(now,base+601))
        self.assertAlmostEqual(stats['energy_today_mwh'],6*30/3600,places=4)
        self.assertAlmostEqual(stats['observed_minutes'],0.5)

    def test_docker_isolation_and_nginx_api_allowlist(self):
        import yaml
        s=yaml.safe_load((ROOT/'compose.yaml').read_text())['services']
        self.assertEqual(set(s['public-publisher']['networks']),{'web_dmz','idmz'})
        self.assertEqual(set(s['public-case-conduit']['networks']),{'web_dmz','idmz'})
        self.assertEqual(set(s['public-ops']['networks']),{'level4','idmz'})
        self.assertEqual(s['public-case-conduit']['environment']['CONDUIT_REQUIRE_AUTH_GET'],'true')
        self.assertEqual(s['web-server']['ports'],['127.0.0.1:18081:80'])
        self.assertEqual(s['public-ops']['ports'],['127.0.0.1:18085:8080'])
        conf=(ROOT/'docs/web/nginx.conf').read_text()
        for p in ('/api/public/statistics','/api/public/notices','/api/enquiries','/api/enquiries/track'):
            self.assertIn('location = '+p,conf)
        self.assertNotIn('location = /api/internal',conf)
        self.assertIn('location / { return 404; }',conf)
        html=(ROOT/'docs/web/index.html').read_text()
        self.assertIn('enquiryForm',html)
        self.assertIn('trackForm',html)
        self.assertNotIn('X-PPC-Token',html)

    def test_strict_internal_get_conduit_requires_auth(self):
        with patch.dict(os.environ,{'TARGET_URL':'http://127.0.0.1:1',
                'ALLOWED_PATHS':'/api/internal/enquiries','ALLOWED_METHODS':'GET,POST',
                'CONDUIT_AUTH_TOKEN':'special','CONDUIT_REQUIRE_AUTH_GET':'true'}):
            import http_relay
            r=importlib.reload(http_relay)
            self.assertFalse(r.authorized('GET',''))
            self.assertTrue(r.authorized('GET','special'))
            self.assertFalse(r.allowed('GET','/api/control'))

if __name__=='__main__':unittest.main()
