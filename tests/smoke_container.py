"""Build ls-rdpgw:verify first; validates startup, not an authenticated RDP session."""
import subprocess
import time
import tempfile
import os
from pathlib import Path

IMAGE = os.environ.get('RDPGW_TEST_IMAGE', 'ls-rdpgw:verify')

def docker(*args, check=True):
    r = subprocess.run(['docker', *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f'{args}: {r.stdout}\n{r.stderr}')
    return r

with tempfile.TemporaryDirectory(prefix='rdpgw-smoke-') as tmp:
    mount = f'{tmp}:/config'
    readonly = docker('run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}',
                      '-v', f'{tmp}:/config:ro', '--entrypoint', 'python3',
                      IMAGE, '/usr/local/lib/rdpgw/config.py', 'init', check=False)
    assert readonly.returncode != 0 and 'Read-only file system' in readonly.stderr
    docker('run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}', '-v', mount, '--entrypoint', 'python3', IMAGE,
           '/usr/local/lib/rdpgw/config.py', 'init')
    config = Path(tmp) / 'rdpgw.yaml'
    before = config.read_text()
    assert 'GENERATE_' not in before and 'CHANGE_ME' in before
    docker('run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}', '-v', mount, '--entrypoint', 'python3', IMAGE,
           '/usr/local/lib/rdpgw/config.py', 'init')
    assert before == config.read_text()
    invalid = docker('run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}', '-v', mount, '--entrypoint', 'python3', IMAGE,
                     '/usr/local/lib/rdpgw/config.py', 'validate', check=False)
    assert invalid.returncode != 0 and 'CHANGE_ME' in invalid.stderr
    replacements = {'CHANGE_ME_GATEWAY': 'https://localhost', 'CHANGE_ME_HOST': 'localhost',
                    'CHANGE_ME_PROVIDER_URL': 'http://127.0.0.1:18080',
                    'CHANGE_ME_CLIENT_ID': 'test', 'CHANGE_ME_CLIENT_SECRET': 'test-secret'}
    for key, value in replacements.items(): before = before.replace(key, value)
    config.write_text(before)
    name = f'rdpgw-smoke-{int(time.time())}'
    try:
        docker('run', '-d', '--name', name, '-e', f'PUID={os.getuid()}', '-e', f'PGID={os.getgid()}', '-v', mount,
               '-v', f'{Path(__file__).resolve().parent}/fixtures/mock_oidc.py:/mock.py:ro',
               '--entrypoint', '/bin/bash', IMAGE,
               '-c', 'python3 /mock.py & exec /init')
        for _ in range(40):
            probe = docker('exec', name, '/etc/s6-overlay/s6-rc.d/svc-rdpgw/data/check', check=False)
            if probe.returncode == 0:
                ready = docker('exec', name, 's6-svstat', '-o', 'ready',
                               '/run/service/svc-rdpgw', check=False)
                if ready.returncode == 0 and ready.stdout.strip() == 'true':
                    break
            time.sleep(1)
        else:
            raise RuntimeError(docker('logs', name, check=False).stdout + docker('logs', name, check=False).stderr)
        ready = docker('exec', name, 's6-svstat', '-o', 'ready', '/run/service/svc-rdpgw')
        assert ready.stdout.strip() == 'true', ready.stdout
        libs = docker('exec', name, 'ldd', '/opt/rdpgw/rdpgw-auth')
        assert 'not found' not in libs.stdout
        for path in ('/', '/connect?host=localhost%3A3389&credential_mode=custom&username=test-user'):
            response = docker('exec', name, 'curl', '-ksS', '-o', '/dev/null', '-w', '%{http_code} %{redirect_url}',
                              f'https://127.0.0.1{path}')
            assert response.stdout.startswith('302 http://127.0.0.1:18080/auth?'), response.stdout
        expired = docker('exec', name, 'curl', '-ksS', '-o', '/dev/null', '-w', '%{http_code}',
                         '-H', 'X-Landing-Refresh: 1', 'https://127.0.0.1/')
        assert expired.stdout == '401', expired.stdout
        print('OIDC discovery, TLS gateway, /metrics probe and s6 ready: PASS')
        print('Landing and GET /connect OIDC redirects, expired refresh: PASS')
        print('PAM dynamic libraries:', libs.stdout)
    finally:
        docker('rm', '-f', name, check=False)
