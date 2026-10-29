"""Demo CA01: creates a CA, signs CSR requests with a lab-only enrollment token.
PKI tests only. Never use this key or issued certificates in production.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path('/data')
CA = ROOT / 'ca.pem'
KEY = ROOT / 'ca.key'
TOKEN = os.environ['CA_ENROLL_TOKEN']


def bootstrap():
    ROOT.mkdir(parents=True,exist_ok=True)
    if not CA.exists() or not KEY.exists():
        subprocess.run(['openssl','req','-x509','-newkey','rsa:3072','-nodes','-days','365',
                        '-keyout',str(KEY),'-out',str(CA), '-subj','/CN=Purdue Lab CA01/O=Purdue Lab'],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        KEY.chmod(0o600)


def sign_csr(csr):
    if len(csr)>16384 or '-----BEGIN CERTIFICATE REQUEST-----' not in csr:
        raise ValueError('invalid PEM CSR')
    with tempfile.TemporaryDirectory() as tmp:
        csr_file=Path(tmp)/'req.csr'
        cert_file=Path(tmp)/'cert.pem'
        csr_file.write_text(csr)
        # Explicitly do not trust requested CSR extensions/SAN; CA only grants simple
        # leaf certificates to requests authenticated with the local enrollment token.
        subprocess.run(['openssl','req','-in',str(csr_file),'-noout','-verify'], check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(['openssl','x509','-req','-in',str(csr_file),'-CA',str(CA),'-CAkey',str(KEY),
                        '-CAcreateserial','-out',str(cert_file),'-days','30','-sha256'],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return cert_file.read_text()


class Handler(BaseHTTPRequestHandler):
    def reply(self,code,data,content_type='application/json'):
        payload=data if isinstance(data,bytes) else json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/ca.pem': return self.reply(200,CA.read_bytes(),'application/x-pem-file')
        if path in ('/','/api/status'):
            return self.reply(200,{'issuer':'Purdue Lab CA01','ca_ready':CA.exists(),'enrollment':'token_required',
                                   'note':'Laboratory CA only. No production trust or CRL/OCSP.'})
        return self.reply(404,{'error':'not_found'})

    def do_POST(self):
        if urlsplit(self.path).path!='/api/sign': return self.reply(404,{'error':'not_found'})
        if not secrets.compare_digest(self.headers.get('X-Lab-Enrollment-Token',''),TOKEN):
            return self.reply(401,{'error':'unauthorized'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 1<=size<=16384: return self.reply(413,{'error':'invalid_size'})
            body=json.loads(self.rfile.read(size))
            cert=sign_csr(body['csr'])
            return self.reply(200,{'certificate':cert,'ca_certificate':CA.read_text()})
        except (ValueError,KeyError,TypeError,subprocess.CalledProcessError):
            return self.reply(400,{'error':'invalid_csr'})


if __name__=='__main__':
    bootstrap()
    ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
