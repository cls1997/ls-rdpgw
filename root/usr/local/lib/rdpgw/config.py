#!/usr/bin/python3
"""Container configuration initialization, validation and local readiness check."""
import os
from pathlib import Path
import secrets
import ssl
import sys
import urllib.request

import yaml

CONFIG = Path('/config/rdpgw.yaml')
TEMPLATE = Path('/defaults/rdpgw.yaml')


def initialize():
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG.exists():
        return
    text = TEMPLATE.read_text()
    for marker in ('GENERATE_SESSION_KEY', 'GENERATE_SESSION_ENCRYPTION_KEY',
                   'GENERATE_PAA_KEY', 'GENERATE_USER_KEY',
                   'GENERATE_PAA_ENCRYPTION_KEY', 'GENERATE_USER_SIGNING_KEY'):
        text = text.replace(marker, secrets.token_hex(16))
    # Exclusive creation also protects configurations created concurrently.
    try:
        fd = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, 'w') as output:
        output.write(text)
    print(f'已生成带注释的默认配置 {CONFIG}；请替换 CHANGE_ME 值并重启。')


def normalize(value):
    if isinstance(value, dict):
        return {str(k).lower(): normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def load():
    data = normalize(yaml.safe_load(CONFIG.read_text()))
    if not isinstance(data, dict):
        raise ValueError('配置必须是 YAML 映射')
    # Match the upstream RDPGW_ prefix and double-underscore nesting convention.
    for name, value in os.environ.items():
        if name.startswith('RDPGW_'):
            keys = name[6:].lower().split('__')
            target = data
            for key in keys[:-1]:
                target = target.setdefault(key, {})
            target[keys[-1]] = value.strip()
    server = data.get('server', {})
    if not isinstance(server, dict):
        raise ValueError('Server 必须是 YAML 映射')
    port = server.get('port', 443)
    if isinstance(port, bool) or not str(port).isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError('Server.Port 必须为 1–65535 的整数')
    tls = server.get('tls', 'auto')
    if tls not in ('auto', 'enable', 'disable'):
        raise ValueError('Server.Tls 必须为 auto、enable 或 disable')
    return data, int(port), tls


def validate():
    data, _, _ = load()

    def placeholders(value):
        if isinstance(value, dict):
            return any(placeholders(v) for v in value.values())
        if isinstance(value, list):
            return any(placeholders(v) for v in value)
        return isinstance(value, str) and ('CHANGE_ME' in value or 'GENERATE_' in value)

    if placeholders(data):
        raise ValueError(f'请编辑 {CONFIG}，替换默认配置中的 CHANGE_ME 占位值后重启')


def check():
    _, port, tls = load()
    scheme = 'http' if tls == 'disable' else 'https'
    # Disable proxies and redirects: a readiness request must stay on loopback.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    handlers = [urllib.request.ProxyHandler({}), NoRedirect()]
    if scheme == 'https':
        handlers.append(urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
    opener = urllib.request.build_opener(*handlers)
    with opener.open(f'{scheme}://127.0.0.1:{port}/metrics', timeout=3) as response:
        if response.status != 200:
            raise ValueError(f'健康检查返回 HTTP {response.status}')


if __name__ == '__main__':
    try:
        {'init': initialize, 'validate': validate, 'check': check}[sys.argv[1]]()
    except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
        print(f'rdpgw: {error}', file=sys.stderr)
        sys.exit(1)
