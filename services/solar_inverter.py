"""L1 PV inverter controller: Modbus TCP plus HTTP telemetry and PPC dispatch.

REGISTER MAP is LAB-PROPRIETARY, not SunSpec certified:
0 P(kW)*10, 1 Pdc(kW)*10, 2 Vac(V), 3 Iac(A)*10, 4 freq(Hz)*100,
5 PV temp(C)*10, 6 irradiance(W/m²), 7 limit(%)*10, 8 status (1 online),
9 energy(kWh, low 16-bit), 10 power factor*1000, 11 connected (1/0).
Coil writes are NOT supported. PPC commands via token-protected HTTP endpoint.
"""
import json, os, socketserver, struct, threading, time
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from common import JSONHandler, read_json, send_json
NAME=os.getenv('ASSET_ID','INV-01')
RATED=float(os.getenv('AC_KW','2500'))
FIELD=os.getenv('FIELD_URL','http://array-conduit-01:8080')
TOKEN=os.getenv('CONTROL_TOKEN','')
lock=threading.RLock()
state={'device':NAME,'connected':False,'array_connected':False,'array':os.getenv('ARRAY_ID','PV-01'),
       'active_kw':0,'dc_kw':0,'available_dc_kw':0,'ac_voltage_v':690.0,'ac_current_a':0,
       'frequency_hz':50.0,'power_factor':0.995,'efficiency_pct':97.8,'limit_pct':100,
       'energy_kwh':0,'irradiance_w_m2':0,'module_c':28,'dc_voltage_v':0,
       'dc_current_a':0,'soiling_pct':0,'failed_strings':0,'active_strings':0,'strings':0,'measured_at':0,'status':'INITIALIZING','rated_kw':RATED}
def poll():
    last=time.monotonic()
    while True:
        now=time.monotonic(); dt=min(5,now-last);last=now
        try:
            with urlopen(FIELD+'/api/state',timeout=3) as r: field=json.load(r)
            if not field['connected']:raise ValueError('field_offline')
            dc=float(field['dc_kw']); eff=0.978 if dc>300 else 0.92
            with lock:
                output=min(dc*eff, RATED*state['limit_pct']/100)
                actual_dc=output/eff if eff else 0
                state.update(connected=True,array_connected=True,active_kw=round(output,2),dc_kw=round(actual_dc,2),available_dc_kw=dc,
                    ac_current_a=round(output*1000/(1.732*690*0.995),2),
                    energy_kwh=round(state['energy_kwh']+output*dt/3600,3),
                    efficiency_pct=round(eff*100,2),irradiance_w_m2=field['irradiance_w_m2'],
                    module_c=field['module_c'],dc_voltage_v=field['dc_voltage_v'],
                    dc_current_a=round(actual_dc*1000/max(1,field['dc_voltage_v']),2),measured_at=time.time(),
                    soiling_pct=field.get('soiling_pct',0),failed_strings=field.get('failed_strings',0),
                    active_strings=field.get('active_strings',0),strings=field.get('strings',0),
                    status='CURTAILED' if output+1 < dc*eff else 'GENERATING')
        except (OSError,ValueError,KeyError,TimeoutError):
            with lock:state.update(connected=False,array_connected=False,active_kw=0,dc_kw=0,status='COMMUNICATION_LOSS')
        time.sleep(2)
def registers():
    with lock:s=dict(state)
    return [min(65535,int(s['active_kw']*10)),min(65535,int(s['dc_kw']*10)),
      int(s['ac_voltage_v']),min(65535,int(s['ac_current_a']*10)),int(s['frequency_hz']*100),
      min(65535,int(s['module_c']*10)),int(s['irradiance_w_m2']),int(s['limit_pct']*10),
      int(s['connected']),int(s['energy_kwh'])%65536,int(s['power_factor']*1000),int(s['array_connected'])]
def modbus_pdu(pdu):
    if not pdu:return b''
    fc=pdu[0]
    if fc not in (3,4):return bytes([fc|0x80,1])
    if len(pdu)!=5:return bytes([fc|0x80,3])
    offset,count=struct.unpack('!HH',pdu[1:]); regs=registers()
    if count<1 or count>125:return bytes([fc|0x80,3])
    if offset+count>len(regs):return bytes([fc|0x80,2])
    return bytes([fc,count*2])+struct.pack('!'+'H'*count,*regs[offset:offset+count])
class ModbusHandler(socketserver.BaseRequestHandler):
    def exact(self,n):
        b=bytearray()
        while len(b)<n:
            part=self.request.recv(n-len(b))
            if not part:return None
            b.extend(part)
        return bytes(b)
    def handle(self):
        self.request.settimeout(10)
        try:
            while True:
                header=self.exact(7)
                if not header:return
                tid,proto,length,unit=struct.unpack('!HHHB',header)
                if proto or not 2<=length<=253:return
                pdu=self.exact(length-1)
                if pdu is None:return
                response=modbus_pdu(pdu)
                self.request.sendall(struct.pack('!HHHB',tid,0,len(response)+1,unit)+response)
        except (OSError,TimeoutError):pass
class ModbusServer(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True
class Handler(JSONHandler):
    def do_GET(self):
        if self.path=='/api/state':
            with lock:s=dict(state)
            send_json(self,200,s)
        elif self.path=='/health':
            with lock:online=state['connected']
            send_json(self,200 if online else 503,{'ok':online,'device':NAME})
        else:send_json(self,404,{'error':'not_found'})
    def do_POST(self):
        if self.path!='/api/limit':return send_json(self,404,{'error':'not_found'})
        if not TOKEN or self.headers.get('X-PPC-Token')!=TOKEN:return send_json(self,403,{'error':'ppc_authorization_required'})
        try:
            req=read_json(self);limit=req.get('limit_pct')
            if type(limit) not in (float,int) or not 0<=limit<=100:raise ValueError()
            with lock:state['limit_pct']=float(limit)
            send_json(self,200,{'ok':True,'device':NAME,'limit_pct':limit})
        except (ValueError,TypeError):send_json(self,400,{'error':'invalid_limit'})
if __name__=='__main__':
    threading.Thread(target=poll,daemon=True).start()
    srv=ModbusServer(('0.0.0.0',int(os.getenv('MODBUS_PORT','15020'))),ModbusHandler)
    threading.Thread(target=srv.serve_forever,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
