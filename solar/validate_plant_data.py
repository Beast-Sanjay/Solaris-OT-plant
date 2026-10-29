#!/usr/bin/env python3
"""Offline model validation against time-aligned real plant data CSV.
Reads CSV without network access and reports errors. Does not modify plant states.
This is a simple static calibration check, NOT proof of a validated twin.
"""
import csv
import math
import sys
from pathlib import Path


def predict(irradiance_wm2, ambient_c, ppc_limit_mw=100.0, grid_breaker_closed=True):
    if not grid_breaker_closed: return 0.0
    g=float(irradiance_wm2); t=float(ambient_c)
    if not (0<=g<=1200 and -10<=t<=65):raise ValueError('weather out of range')
    celltemp=t+0.03*g
    dc=max(0,27.5*g/1000*max(0,1-0.0035*(celltemp-25))*0.97)
    ac=min(25,dc*0.96)*4
    return min(100,max(0,float(ppc_limit_mw)), ac*0.985)


def compare(path):
    pairs=[]
    with open(path,newline='',encoding='utf-8-sig') as f:
        for i,r in enumerate(csv.DictReader(f),2):
            if not all(k in r for k in ('irradiance_wm2','ambient_c','observed_export_mw')):
                raise ValueError('Required columns: irradiance_wm2, ambient_c, observed_export_mw')
            obs=float(r['observed_export_mw'])
            if not math.isfinite(obs) or obs<0: raise ValueError(f'invalid measurement at line {i}')
            sim=predict(float(r['irradiance_wm2']),float(r['ambient_c']),
                        float(r.get('ppc_limit_mw') or '100'), str(r.get('grid_breaker_closed','true')).lower() not in ('false','0','open'))
            pairs.append((obs,sim))
    if not pairs: raise ValueError('empty CSV')
    diffs=[sim-obs for obs,sim in pairs]
    mae=sum(abs(x) for x in diffs)/len(diffs)
    rmse=math.sqrt(sum(x*x for x in diffs)/len(diffs))
    bias=sum(diffs)/len(diffs)
    return {'samples':len(pairs),'mae_mw':round(mae,4),'rmse_mw':round(rmse,4),'bias_mw':round(bias,4),
            'note':'Validation compares static model point predictions; it does not capture transients or proving operational equivalence.'}


if __name__=='__main__':
    import json
    if len(sys.argv)!=2: raise SystemExit('usage: python solar/validate_plant_data.py real_plant.csv')
    print(json.dumps(compare(sys.argv[1]),indent=2))
