"""Level 0 physical process model. All measurements are synthetic."""
import json
import math
import os
import threading
import time
from http.server import ThreadingHTTPServer
from common import JSONHandler, read_json, send_json

lock = threading.Lock()
state = {'level': 44.0, 'pump': False, 'temperature': 27.0, 'flow': 0.0, 'tick': time.time()}


def evolve():
    while True:
        time.sleep(1)
        with lock:
            now = time.time()
            dt = min(3, now - state['tick'])
            state['tick'] = now
            # Tank fills when pump runs and drains steadily into process output.
            state['level'] = max(0, min(100, state['level'] + dt * (0.75 if state['pump'] else -0.22)))
            state['flow'] = round(12.5 if state['pump'] else 0.0, 2)
            state['temperature'] = round(27 + 1.8 * math.sin(now / 80), 2)


class Handler(JSONHandler):
    def do_GET(self):
        if self.path != '/api/state':
            return send_json(self, 404, {'error': 'not_found'})
        with lock:
            snapshot = {k: round(v, 2) if isinstance(v, float) else v for k, v in state.items() if k != 'tick'}
        return send_json(self, 200, {'source': 'synthetic-field-device', **snapshot, 'time': time.time()})

    def do_POST(self):
        if self.path != '/api/actuator':
            return send_json(self, 404, {'error': 'not_found'})
        try:
            obj = read_json(self)
            if type(obj.get('pump')) is not bool:
                raise ValueError('pump must be boolean')
            with lock:
                state['pump'] = obj['pump']
            return send_json(self, 200, {'ok': True, 'pump': obj['pump']})
        except (ValueError, json.JSONDecodeError):
            return send_json(self, 400, {'error': 'invalid_json'})


if __name__ == '__main__':
    threading.Thread(target=evolve, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8080'))), Handler).serve_forever()
