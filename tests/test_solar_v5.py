"""Deterministic checks of the new purpose-driven devices; no Docker required."""
import importlib,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'))

class SolarPlantV5Tests(unittest.TestCase):
    def test_transformer_loss_and_winding(self):
        import solar_transformer as tx
        s=tx.update_input(8000,now=1000)
        self.assertEqual(s['device'],'TX-33KV-01')
        self.assertGreater(s['delivered_kw'],7500)
        self.assertLess(s['delivered_kw'],8000)
        self.assertGreater(s['winding_c'],34)

    def test_grid_dispatch_order_ceiling(self):
        import solar_grid_dispatch as grid
        s=grid.apply_order(36,'GRID-ORDER-TEST')
        self.assertEqual(s['export_limit_pct'],36)
        with self.assertRaises(ValueError):grid.apply_order(150,'EXCEEDS_LIMIT')
        grid.apply_order(100,'GRID-RESTORE')

    def test_latched_feeder_rejects_close_in_model(self):
        import solar_feeder as f
        with f.lock:
            f.state.update(trip_latched=True,breaker_closed=False,trip_reason='TEST')
        self.assertTrue(f.snapshot()['trip_latched'])
        self.assertEqual(f.measure(1000,now=3000)['export_kw'],0)
        with f.lock:f.state.update(trip_latched=False,trip_reason=None,breaker_closed=True)
        self.assertEqual(f.measure(1000,now=3002)['export_kw'],1000)

    def test_maintenance_proposals_live_faults(self):
        # Planner is packaged in a psycopg-enabled container; isolate pure planning function.
        import ast
        path=Path(__file__).resolve().parents[1]/'services'/'maintenance_bot.py'
        module=ast.parse(path.read_text())
        fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='proposals')
        code=compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec')
        ns={};exec(code,ns)
        records={
            'PV-02':{'kind':'pv_array','values':{'soiling_pct':7.5,'failed_strings':0}},
            'PV-03':{'kind':'pv_array','values':{'soiling_pct':1.5,'failed_strings':2}},
            'INV-03':{'kind':'inverter','connected':False,'values':{}},
            'FDR-33KV-01':{'kind':'feeder','values':{'trip_latched':True,'trip_reason':'TEST'}}}
        refs={ref for ref,_ in ns['proposals'](records)}
        self.assertEqual(refs,{'AUTO-PV-02-SOILING','AUTO-PV-03-STRINGS','AUTO-INV-03-COMMS','AUTO-FDR-33KV-01-TRIP'})

    def test_scada_assets_page_covers_every_asset(self):
        root=Path(__file__).resolve().parents[1]
        txt=(root/'services/solar_ui/assets.html').read_text()
        for asset in ('MET-01','PV-01','PV-02','PV-03','PV-04','INV-01','INV-02',
                      'INV-03','INV-04','TX-33KV-01','FDR-33KV-01','REL-33KV-01',
                      'PPC-01','SCADA-01','GRID-ORDER-01'):
            self.assertIn(asset,txt)

if __name__=='__main__':unittest.main()
