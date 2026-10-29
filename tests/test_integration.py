import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'scripts/integrate_upstream.py'


class IntegrationTests(unittest.TestCase):
    def test_original_names_are_preserved_but_flat_network_removed(self):
        spec=importlib.util.spec_from_file_location('integrate',path)
        m=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        src={'services': {name: {'networks': ['otlab','ot-net'], 'ports': ['0.0.0.0:502:502'],
                                 'build': {'context': '..', 'dockerfile':'docker/Dockerfile'}}
                          for name in m.PLC_NAMES+('fuxa',)}}
        generated=m.build(src)['services']
        self.assertEqual(len(generated), 13)
        self.assertEqual(generated['plc-water']['networks'],['level1'])
        self.assertEqual(generated['fuxa']['networks'],['level2'])
        self.assertNotIn('ports',generated['plc-heating'])
        self.assertEqual(generated['plc-heating']['networks']['level1']['aliases'], ['plc-heating-l1'])
        self.assertEqual(generated['fuxa']['ports'],['127.0.0.1:1881:1881'])
        self.assertEqual(generated['sis']['depends_on'],['plc-water'])


if __name__=='__main__': unittest.main()
