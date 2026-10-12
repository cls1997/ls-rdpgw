"""Run with /usr/bin/python3 -m unittest discover -s tests -v."""
import importlib.util
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('container_config', ROOT / 'root/usr/local/lib/rdpgw/config.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class Handler(BaseHTTPRequestHandler):
    status = 200

    def do_GET(self):
        self.send_response(self.status if self.path == '/metrics' else 404)
        self.end_headers()

    def log_message(self, *args):
        pass


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'rdpgw.yaml'
        self.patch = patch.multiple(config, CONFIG=self.path, TEMPLATE=ROOT / 'root/defaults/rdpgw.yaml')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def write(self, text):
        self.path.write_text(text)

    def test_initialize_preserves_config_and_keys(self):
        config.initialize()
        first = self.path.read_text()
        self.assertIn('# 首次启动', first)
        self.assertNotIn('GENERATE_', first)
        data = yaml.safe_load(first)
        keys = [data['Server']['SessionKey'], data['Server']['SessionEncryptionKey']]
        keys += [v for k, v in data['Security'].items() if k.endswith('Key')]
        self.assertEqual(len(set(keys)), 6)
        self.assertTrue(all(len(k) == 32 for k in keys))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        config.initialize()
        self.assertEqual(first, self.path.read_text())
        with self.assertRaisesRegex(ValueError, 'CHANGE_ME'):
            config.validate()
        self.write(first.replace('CHANGE_ME', 'configured'))
        config.validate()

    def test_write_error(self):
        with patch.object(config.os, 'open', side_effect=PermissionError('not writable')):
            with self.assertRaisesRegex(PermissionError, 'not writable'):
                config.initialize()

    def test_yaml_and_overrides(self):
        self.write('Server:\n  Port: 8443 # custom\n  Tls: enable\n')
        self.assertEqual(config.load()[1:], (8443, 'enable'))
        with patch.dict(os.environ, {'RDPGW_SERVER__PORT': '8080', 'RDPGW_SERVER__TLS': 'disable'}):
            self.assertEqual(config.load()[1:], (8080, 'disable'))
        for text in ('[]', 'Server: []', 'Server: {Port: 0}', 'Server: {Port: 65536}',
                     'Server: {Port: true}', 'Server: {Tls: invalid}', 'Server: ['):
            with self.subTest(text=text):
                self.write(text)
                with self.assertRaises((ValueError, yaml.YAMLError)):
                    config.load()

    def probe_server(self, tls=False, status=200):
        handler = type('Response', (Handler,), {'status': status})
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        if tls:
            cert = Path(self.temp.name) / 'cert.pem'
            key = Path(self.temp.name) / 'key.pem'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-keyout', str(key), '-out', str(cert), '-days', '1',
                            '-subj', '/CN=localhost'], check=True, capture_output=True)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert, key)
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.write(f'Server:\n  Port: {server.server_port}\n  Tls: {"enable" if tls else "disable"}\n')
            config.check()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_http(self):
        self.probe_server()

    def test_self_signed_https(self):
        self.probe_server(tls=True)

    def test_bad_status(self):
        with self.assertRaises(OSError):
            self.probe_server(status=503)

    def test_connection_failure(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        port = server.server_port
        server.server_close()
        self.write(f'Server: {{Port: {port}, Tls: disable}}')
        with self.assertRaises(OSError):
            config.check()


if __name__ == '__main__':
    unittest.main()
