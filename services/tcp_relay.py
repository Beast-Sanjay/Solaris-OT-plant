"""Port-by-port L1/L2 and IT/IDMZ gateway, *not* an IP router."""
import os
import socket
import socketserver
import threading


def make_handler(target_host, target_port):
    class TCPHandler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                remote = socket.create_connection((target_host, target_port), timeout=5)
            except OSError:
                return
            with remote:
                self.request.settimeout(30)
                remote.settimeout(30)

                def copy(src, dst):
                    try:
                        while True:
                            data = src.recv(8192)
                            if not data:
                                break
                            dst.sendall(data)
                    except (OSError, TimeoutError):
                        pass
                    try:
                        dst.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                t = threading.Thread(target=copy, args=(self.request, remote), daemon=True)
                t.start()
                copy(remote, self.request)
                t.join(timeout=3)
    return TCPHandler


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    mappings = [v.strip() for v in os.environ['TCP_RELAYS'].split(',')]
    servers = []
    for mapping in mappings:
        port, endpoint = mapping.split('=', 1)
        host, dest_port = endpoint.rsplit(':', 1)
        server = Server(('0.0.0.0', int(port)), make_handler(host, int(dest_port)))
        servers.append(server)
        print(f'[conduit] {port} -> {host}:{dest_port}', flush=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Event().wait()
