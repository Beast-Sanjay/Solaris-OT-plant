"""L0 synthetic pyranometer, ambient sensor and anemometer. Deterministic accelerated sunlight."""
import math, os, time
from http.server import ThreadingHTTPServer
from common import JSONHandler, send_json
START=time.monotonic()

def weather(at=None):
    elapsed=(time.monotonic() if at is None else at)-START
    # Accelerated demonstration day; intentionally starts in daylight.
    phase=2*math.pi*elapsed/float(os.getenv('SUN_CYCLE_SECONDS','900'))
    cloud=0.90+0.07*math.sin(phase*3.2)+0.03*math.cos(phase*7.9)
    elevation=max(0.0,0.82+0.16*math.sin(phase-0.35))
    poa=round(max(0,1000*elevation*cloud),1)
    ambient=round(28+4*math.sin(phase-0.7),2)
    return {'device':'MET-01','irradiance_w_m2':poa,'ambient_c':ambient,
            'module_c':round(ambient+poa*0.024,2),'wind_m_s':round(3.2+0.8*math.sin(phase*2),2),
            'site':'SOLARIS ONE','measured_at':time.time(),'simulation':True,'connected':True}
class Handler(JSONHandler):
    def do_GET(self):
        if self.path=='/api/state': send_json(self,200,weather())
        elif self.path=='/health': send_json(self,200,{'ok':True})
        else: send_json(self,404,{'error':'not_found'})
if __name__=='__main__': ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
