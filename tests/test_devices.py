"""Device-level functional tests without a Docker daemon."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services"))

ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class HistorianTests(unittest.TestCase):
    def test_independent_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=load('historian',ROOT/'services/historian.py')
            old=m.DB
            m.DB=str(Path(tmp)/'hist.db')
            try:
                d={}
                for name,level in [('plc-demo',40),('plc-secondary',80)]:
                    d[name]={'connected':True,'values':{'level_pct':level,'temperature_c':25,
                       'flow_lpm':2.5,'pump_on':False,'setpoint_pct':55,'field_connected':True}}
                assert len(m.save_snapshot({'devices':d},now=123456789))==2
                self.assertEqual(set(m.latest_devices()),set(d))
                self.assertEqual(m.rows(1)[0]['level_pct'],40)
                self.assertEqual(m.device_rows(1,'plc-secondary')[0]['level_pct'],80)
            finally:
                m.DB=old

    def test_missing_telemetry_not_inserted(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=load('historian_missing',ROOT/'services/historian.py')
            m.DB=str(Path(tmp)/'hist.db')
            values={'devices':{'plc-secondary':{'connected':False,'values':{}}}}
            self.assertEqual(m.save_snapshot(values),[])
            self.assertEqual(m.latest_devices(),{})


class ScadaTests(unittest.TestCase):
    def test_two_controller_endpoints(self):
        m=load('scada',ROOT/'services/scada.py')
        previous=os.environ.get('DEVICE_ENDPOINTS')
        os.environ['DEVICE_ENDPOINTS']='plc-demo=control-conduit:15020,plc-secondary=control-conduit:15021'
        try:
            self.assertEqual(m.endpoints(),{'plc-demo':('control-conduit',15020),
                                            'plc-secondary':('control-conduit',15021)})
        finally:
            if previous is None: os.environ.pop('DEVICE_ENDPOINTS',None)
            else:os.environ['DEVICE_ENDPOINTS']=previous


class CertificateAuthorityTests(unittest.TestCase):
    def test_sign_and_verify_csr(self):
        if not shutil_which('openssl'):self.skipTest('openssl unavailable')
        os.environ['CA_ENROLL_TOKEN']='test-only-secret'
        m=load('ca_service',ROOT/'ca/ca_service.py')
        with tempfile.TemporaryDirectory() as tmp:
            m.ROOT=Path(tmp)
            m.CA=Path(tmp)/'ca.pem'
            m.KEY=Path(tmp)/'ca.key'
            m.bootstrap()
            key=Path(tmp)/'leaf.key'
            req=Path(tmp)/'leaf.csr'
            cert=Path(tmp)/'leaf.crt'
            subprocess.run(['openssl','req','-newkey','rsa:2048','-nodes','-keyout',str(key),
                            '-out',str(req),'-subj','/CN=corp-portal.corp.otlab.test'],
                           check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            cert.write_text(m.sign_csr(req.read_text()))
            subprocess.run(['openssl','verify','-CAfile',str(m.CA),str(cert)],check=True,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.assertTrue(m.CA.exists())


def shutil_which(command):
    import shutil
    return shutil.which(command)


if __name__ == '__main__': unittest.main()
