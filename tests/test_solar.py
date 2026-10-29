"""Pure logic regression checks for solar model, PPC and protective relay."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'solar'))
from physics import Plant
from ppc import distribute
from protection import assess
from validate_plant_data import predict


class SolarPhysicsTests(unittest.TestCase):
    def test_energy_balance_clear_sky(self):
        plant=Plant().tick()
        self.assertGreater(plant['pcc']['export_mw'],70)
        self.assertAlmostEqual(plant['pcc']['export_mw'],plant['ac_total_mw']*.985,places=2)

    def test_weather_changes_linked_outputs(self):
        p=Plant()
        before=p.tick()['pcc']['export_mw']
        after=p.command({'action':'weather','irradiance_wm2':200})['pcc']['export_mw']
        self.assertLess(after,before/2)
        self.assertAlmostEqual(after,sum(x['ac_power_mw'] for x in p.tick()['inverters'].values())*.985,places=2)

    def test_breaker_disconnects_all_inverters(self):
        p=Plant()
        state=p.command({'action':'grid_breaker','closed':False})
        self.assertEqual(state['pcc']['export_mw'],0)
        self.assertEqual(state['ac_total_mw'],0)
        self.assertTrue(all(i['ac_power_mw']==0 for i in state['inverters'].values()))

    def test_no_invalid_weather_accepted(self):
        p=Plant()
        for data in ({'action':'weather','irradiance_wm2':-1},
                     {'action':'weather','irradiance_wm2':'one thousand'},
                     {'action':'grid_breaker','closed':1},
                     {'action':'inverter_limit','inverter':'INV-01','limit_kw':30000}):
            with self.assertRaises(ValueError): p.command(data)

    def test_ppc_target_and_capacity(self):
        l=distribute(40,[25,25,25,25]);self.assertAlmostEqual(sum(l)*.985,40)
        l=distribute(90,[10,20,0,5]);self.assertEqual(l,[10,20,0,5])
        self.assertEqual(distribute(0,[25,25]),[0,0])

    def test_protection_trip_boundaries(self):
        p=Plant()
        self.assertIsNone(assess(p.tick()))
        state=p.command({'action':'grid_conditions','frequency_hz':47})
        self.assertEqual(assess(state),'grid_frequency_out_of_range')
        state=p.command({'action':'grid_conditions','frequency_hz':50,'voltage_kv':29})
        self.assertEqual(assess(state),'grid_voltage_out_of_range')

    def test_model_predictor_matches_engine(self):
        self.assertAlmostEqual(predict(1000,25),Plant().tick()['pcc']['export_mw'],places=2)
        self.assertEqual(predict(1000,25,grid_breaker_closed=False),0)
        self.assertAlmostEqual(predict(1000,25,40),40)


if __name__=='__main__':unittest.main()
