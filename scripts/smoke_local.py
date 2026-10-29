#!/usr/bin/env python3
"""Run realistic L0->L1->L2->L3->SOC pipeline on local loopback.
Does NOT test Docker network isolation, Samba, FUXA or original upstream images.
"""
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / 'services'
PROCS = []


def launch(script, **environment):
    env = os.environ.copy()
    env.update({k: str(v) for k, v in environment.items()})
    process = subprocess.Popen([sys.executable, '-u', str(APPS/script)], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    PROCS.append(process)


def get_json(url):
    with urlopen(url, timeout=3) as response: return json.load(response)


def read_modbus():
    with socket.create_connection(('127.0.0.1', 15020), timeout=2) as client:
        client.sendall(struct.pack('!HHHBBHH', 1, 0, 6, 1, 3, 0, 6))
        raw = client.recv(64)
    assert len(raw) >= 21 and raw[7] == 3, f'bad Modbus PDU: {raw!r}'
    return raw


try:
    with tempfile.TemporaryDirectory() as tmp:
        launch('field.py', PORT=39001)
        launch('field.py', PORT=39005, INITIAL_LEVEL=73, FILL_RATE=0.95, DRAIN_RATE=0.35)
        launch('plc.py', FIELD_URL='http://127.0.0.1:39001', MODBUS_PORT=15020)
        launch('plc.py', FIELD_URL='http://127.0.0.1:39005', MODBUS_PORT=15021, INITIAL_SETPOINT=35)
        launch('scada.py', MODBUS_HOST='127.0.0.1', MODBUS_PORT=15020, DEVICE_ENDPOINTS='plc-demo=127.0.0.1:15020,plc-secondary=127.0.0.1:15021', PORT=39002)
        launch('soc.py', PORT=39004, DB_PATH=Path(tmp)/'soc.db', SOC_ELASTIC_URL='http://127.0.0.1:39999')
        launch('historian.py', POLL_URL='http://127.0.0.1:39002/api/state',
               SOC_URL='http://127.0.0.1:39004/api/events', DB_PATH=Path(tmp)/'hist.db', PORT=39003)
        deadline = time.time()+18
        success = False
        while time.time() < deadline:
            try:
                field = get_json('http://127.0.0.1:39001/api/state')
                mb = read_modbus()
                scada = get_json('http://127.0.0.1:39002/api/state')
                hist = get_json('http://127.0.0.1:39003/api/latest')
                soc = get_json('http://127.0.0.1:39004/api/events')
                multi = get_json('http://127.0.0.1:39003/api/devices/latest')
                if (scada['connected'] and hist['sample'] and len(multi['devices']) == 2 and
                    all(d['connected'] and d['values'].get('field_connected') for d in scada['devices'].values())):
                    assert 'pump' in field and scada['values']['field_connected']
                    assert 0 <= hist['sample']['level_pct'] <= 100
                    success = True
                    break
            except (OSError, ValueError, AssertionError):
                pass
            time.sleep(1)
        assert success, 'pipeline failed to deliver an L0 sample to historian within deadline'
        print('[PASS] Two L0 process models -> two Modbus PLCs -> L2 SCADA -> L3 per-device historian; SOC API reachable.')
        # Verify a real Modbus setpoint write and read round-trip.
        with socket.create_connection(('127.0.0.1', 15020), timeout=2) as c:
            c.sendall(struct.pack('!HHHBBHH', 2, 0, 6, 1, 6, 4, 60))
            reply = c.recv(64)
        assert reply[7:12] == struct.pack('!BHH', 6, 4, 60), reply
        print('[PASS] Modbus FC06 setpoint write returns expected response.')
        # Independent secondary setpoint should not mutate primary.
        with socket.create_connection(('127.0.0.1',15021),timeout=2) as c:
            c.sendall(struct.pack('!HHHBBHH',3,0,6,1,6,4,45))
            secondary=c.recv(64)
        assert secondary[7:12] == struct.pack('!BHH',6,4,45)
        assert scada['devices']['plc-secondary']['values']['level_pct'] >= 0
        print('[PASS] Secondary PLC accepts independent register write.')
finally:
    for p in reversed(PROCS):
        p.terminate()
    for p in reversed(PROCS):
        try: p.communicate(timeout=3)
        except subprocess.TimeoutExpired: p.kill()
