#!/usr/bin/env python3
"""Functional device test without Docker: real Modbus/TCP and HTTP processes on loopback.
Runs simulated plant, 4 TCP inverter devices, PPC, SCADA, historian.
Fails if commands, energy balance, or end-to-end telemetry are incorrect.
"""
import contextlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOLAR = ROOT / 'solar'
procs = []


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def run(module, env):
    p = subprocess.Popen([sys.executable, '-u', str(SOLAR / module)],cwd=SOLAR,
                         env={**os.environ,**{k:str(v) for k,v in env.items()}},
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    procs.append(p)
    return p


def req(url, data=None):
    request = Request(url, data=None if data is None else json.dumps(data).encode(),
                      headers={'Content-Type':'application/json'})
    with urlopen(request,timeout=3) as r:
        return json.load(r)


def ready(url, pred=None, seconds=16):
    start=time.time();last=None
    while time.time()-start < seconds:
        try:
            obj=req(url)
            if pred is None or pred(obj): return obj
        except Exception as ex: last=ex
        time.sleep(.24)
    raise AssertionError(f'Not ready {url}: {last}')


def wait_plant(url, condition, label, seconds=12):
    start=time.time(); last={}
    while time.time()-start < seconds:
        try:
            last=req(url)
            if condition(last): return last
        except Exception as ex: last={'transport_error':repr(ex)}
        time.sleep(.3)
    raise AssertionError(f'{label} did not converge: {str(last)[:500]}')


def check(s):
    p=s['plant']
    power=sum(i['ac_power_mw'] for i in p['inverters'].values())
    assert abs(power-p['ac_total_mw'])<.005, 'inverter aggregate mismatch'
    assert abs(p['pcc']['export_mw']-power*.985)<.015,'PCC feeder loss balance'
    assert len(s['device_status'])==4 and all(d['connected'] for d in s['device_status'].values())
    return p


def main():
    physics, ppc, scada, hist = [port() for _ in range(4)]
    inv_ports=[port() for _ in range(4)]
    with tempfile.TemporaryDirectory() as tmp:
        db=os.path.join(tmp,'hist.sqlite3')
        root=f'http://127.0.0.1:{physics}'
        ppcuri=f'http://127.0.0.1:{ppc}'
        scadauri=f'http://127.0.0.1:{scada}'
        histuri=f'http://127.0.0.1:{hist}'
        try:
            run('physics.py',{'PORT':physics});ready(root+'/api/state')
            for i,p in enumerate(inv_ports,1):
                run('inverter.py',{'INVERTER_ID':f'INV-{i:02d}', 'MODBUS_PORT':p,'FIELD_URL':root})
            # Confirm actual transport-level register reads from all four inverter TCP servers.
            sys.path.insert(0,str(SOLAR));from common import read_regs,write_reg
            for p in inv_ports:
                for _ in range(60):
                    try:
                        regs=read_regs('127.0.0.1',p,0,10)
                        assert regs[1]>10000 and regs[3]==1
                        break
                    except OSError: time.sleep(.08)
                else: raise AssertionError(f'Inverter TCP {p} offline')
            write_reg('127.0.0.1',100,5000,port=inv_ports[0])
            assert read_regs('127.0.0.1',inv_ports[0],0,10)[2]==5000, 'FC06 did not actuate'
            print('[PASS] Four independent Modbus TCP servers, FC03 and FC06 actuator')
            run('protection.py',{'FIELD_URL':root})
            run('ppc.py',{'FIELD_URL':root,'PORT':ppc,'INVERTER_HOSTS':','.join(['127.0.0.1']*4),
                          'INVERTER_PORTS':','.join(map(str,inv_ports))})
            run('scada.py',{'PORT':scada,'PPC_URL':ppcuri})
            run('historian.py',{'PORT':hist,'POLL_URL':scadauri+'/api/state','DB_PATH':db,
                                'SOC_URL':'http://127.0.0.1:1/api/events'})
            s=wait_plant(scadauri+'/api/state',lambda x:x.get('connected') and x.get('plant',{}).get('pcc',{}).get('export_mw',0)>70,'initial generation')
            check(s)
            print('[PASS] Clear-sky photovoltaic generation drives each inverter, PPC, SCADA and PCC')
            req(scadauri+'/api/command',{'action':'plant_limit','mw':40})
            s=wait_plant(scadauri+'/api/state',lambda x:x.get('connected') and abs(x.get('plant',{}).get('pcc',{}).get('export_mw',-1)-40)<.12,'40 MW PPC curtailment')
            check(s)
            assert all(9<k['limit_mw']<12 for k in s['plant']['inverters'].values())
            print('[PASS] PPC Modbus setpoints produce 40 MW grid export across four inverters')
            req(scadauri+'/api/command',{'action':'weather','irradiance_wm2':250,'ambient_c':25})
            s=wait_plant(scadauri+'/api/state',lambda x:x.get('plant',{}).get('weather',{}).get('irradiance_wm2')==250 and x['plant']['pcc']['export_mw']<30,'cloud cover')
            check(s)
            print('[PASS] Cloud cover reduces physics output, inverter values and PCC export')
            req(scadauri+'/api/command',{'action':'grid_breaker','closed':False})
            s=wait_plant(scadauri+'/api/state',lambda x:not x.get('plant',{}).get('pcc',{}).get('breaker_closed',True) and x['plant']['pcc']['export_mw']==0,'breaker open')
            assert all(k['ac_power_mw']==0 for k in s['plant']['inverters'].values())
            print('[PASS] Grid breaker trip changes all inverter power to zero')
            req(scadauri+'/api/command',{'action':'reset'})
            s=wait_plant(scadauri+'/api/state',lambda x:x.get('plant',{}).get('pcc',{}).get('export_mw',0)>70,'recovery')
            check(s)
            print('[PASS] Plant reset and production recovery')
            req(scadauri+'/api/command',{'action':'grid_conditions','frequency_hz':47})
            s=wait_plant(scadauri+'/api/state',lambda x:not x.get('plant',{}).get('pcc',{}).get('breaker_closed',True) and x['plant']['pcc']['export_mw']==0,'protection relay trip')
            assert 'protection-relay' in req(root+'/api/state')['last_command'].get('source','')
            print('[PASS] Independent Level 1 protection relay trips PCC for out-of-range frequency')
            req(scadauri+'/api/command',{'action':'reset'})
            h=ready(histuri+'/api/latest',lambda x:x.get('sample') is not None)
            assert len(h['sample']['state']['plant']['inverters'])==4
            assert h['sample']['state']['plant']['pcc']['export_mw']>=0
            samples=req(histuri+'/api/history?limit=10')['samples']
            assert 1<=len(samples)<=10
            with sqlite3.connect(db) as con: assert con.execute('select count(*) from samples').fetchone()[0]>0
            print('[PASS] Level 3 historian stores unified plant and device records in SQLite')
            print('SOLAR TWIN END-TO-END SMOKE TEST PASSED')
        finally:
            for p in reversed(procs):
                p.terminate()
            for p in reversed(procs):
                try: p.wait(timeout=2)
                except subprocess.TimeoutExpired:p.kill();p.wait()

if __name__=='__main__':main()
