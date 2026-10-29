"""Dual-homed L1/L2 single-inverter allowlisted HTTP gateway + Modbus TCP relay."""
import os,threading
from http.server import ThreadingHTTPServer
from http_relay import Handler as HTTPHandler
from tcp_relay import Server as TCPServer,make_handler
if __name__=='__main__':
    tcp=TCPServer(('0.0.0.0',int(os.getenv('CONDUIT_MODBUS_PORT','15020'))),make_handler(os.environ['TARGET_MODBUS_HOST'],int(os.getenv('TARGET_MODBUS_PORT','15020'))))
    threading.Thread(target=tcp.serve_forever,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('LISTEN_PORT','8080'))),HTTPHandler).serve_forever()
