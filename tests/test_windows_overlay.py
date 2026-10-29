"""Windows-specific static checks don't depend on Docker or Windows ISO images."""
import unittest
from pathlib import Path
import yaml
R=Path(__file__).resolve().parents[1]

class WindowsOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core=yaml.safe_load((R/'compose.yaml').read_text())
        cls.win=yaml.safe_load((R/'compose.windows.yaml').read_text())
    def test_windows_disks_and_kvm(self):
        for name in ('win-it','win-server','win-ot'):
            s=self.win['services'][name]
            self.assertIn('/dev/kvm',s['devices'])
            self.assertIn('/dev/net/tun',s['devices'])
            self.assertTrue(any('/storage' in v for v in s['volumes']))
            self.assertTrue(any('/custom.iso:ro' in v for v in s['volumes']))
    def test_windows_auth_not_embedded(self):
        for s in self.win['services'].values():
            self.assertNotIn('DOMAIN',s['environment'])
            self.assertTrue(s['environment']['PASSWORD'].startswith('${WINDOWS_'))
    def test_windows_networks_isolated(self):
        self.assertEqual(set(self.win['services']['win-ot']['networks']),{'level3'})
        self.assertEqual(set(self.win['services']['win-it']['networks']),{'level4'})
        self.assertEqual(set(self.win['services']['win-server']['networks']),{'level4'})
    def test_ot_scada_only_read(self):
        s=self.core['services']['ot-scada-read']
        self.assertEqual(s['environment']['ALLOWED_METHODS'],'GET')
        self.assertNotIn('/api/control',s['environment']['ALLOWED_PATHS'])
    def test_corporate_portal_ips(self):
        self.assertEqual(self.core['services']['it-access']['networks']['level4']['ipv4_address'],'10.0.0.30')
        self.assertEqual(self.core['services']['corp-portal']['networks']['level4']['ipv4_address'],'10.0.0.31')
