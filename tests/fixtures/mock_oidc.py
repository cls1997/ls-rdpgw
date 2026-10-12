import json
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = {'issuer': 'http://127.0.0.1:18080',
                'authorization_endpoint': 'http://127.0.0.1:18080/auth',
                'token_endpoint': 'http://127.0.0.1:18080/token',
                'jwks_uri': 'http://127.0.0.1:18080/keys',
                'id_token_signing_alg_values_supported': ['RS256']}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
HTTPServer(('127.0.0.1', 18080), Handler).serve_forever()
