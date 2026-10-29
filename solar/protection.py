"""Level 1 synthetic grid protection relay. Passive check, latches PCC breaker open.
Trips when grid-source frequency is outside 49..51 Hz or voltage outside 30..36 kV.
The trip is a DEMO, not an IEC 61850 relay, safety PLC or real protection study.
"""
import os
import time
from common import request_json

FIELD = os.getenv('FIELD_URL','http://solar-field-conduit:8080')


def assess(state):
    p=state['pcc']
    if not p['breaker_closed']: return None
    if not 49 <= p['source_frequency_hz'] <= 51: return 'grid_frequency_out_of_range'
    if not 30 <= p['source_voltage_kv'] <= 36: return 'grid_voltage_out_of_range'
    return None


if __name__=='__main__':
    print('[solar-protection] Level 1 protection relay online',flush=True)
    while True:
        try:
            state=request_json(FIELD+'/api/state')
            fault=assess(state)
            if fault:
                request_json(FIELD+'/api/command',{'action':'grid_breaker','closed':False,'source':'protection-relay-'+fault})
                print('[solar-protection] TRIPPED:',fault,flush=True)
        except Exception as e: print('[solar-protection] unavailable',type(e).__name__,flush=True)
        time.sleep(.5)
