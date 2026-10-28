"""Portable simulation/gateway launcher. --dry-run never starts a service."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def plan(args):
    env = os.environ.copy()
    robot = args.robot
    sim_port = args.simulation_port or (9742 if robot == 'x5' else 9740)
    if args.service == 'simulation':
        python = args.python or env.get('TELEMOVO_SIM_PYTHON', sys.executable)
        patch_parent = Path(env.get('TELEMOVO_GENESIS_PATH', ROOT / '.runtime/genesis-contact')).expanduser().resolve()
        if not args.dry_run:
            manifest = json.loads((ROOT / 'patches/manifest.json').read_text())
            import hashlib
            contact = patch_parent / 'genesis' / manifest['file']
            if not contact.is_file() or hashlib.sha256(contact.read_bytes()).hexdigest() != manifest['patched_sha256']:
                raise ValueError('Pinned contact patch unavailable; run scripts/apply_contact_patch.py first')
            sys.path.insert(0, str(ROOT / 'simulation'))
            from configuration import load_config
            load_config(ROOT / 'configs' / robot)
        env['PYTHONPATH'] = str(patch_parent) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
        env['CUDA_VISIBLE_DEVICES'] = env.get('TELEMOVO_GPU', '0')
        env['EGL_DEVICE_ID'] = env.get('TELEMOVO_EGL_DEVICE', '0')
        env['OMP_NUM_THREADS'] = env.get('OMP_NUM_THREADS', '4')
        command = [python, '-B', str(ROOT / 'simulation/live.py'), '--config-dir', str(ROOT / 'configs' / robot),
                   '--port', str(sim_port), '--seconds', str(args.seconds)]
        if args.teleop:
            command.append('--teleop')
        if args.self_test:
            command.append('--self-test')
        return command, env, None
    python = args.python or env.get('TELEMOVO_GATEWAY_PYTHON', sys.executable)
    ssh_host = args.ssh_host or env.get('TELEMOVO_SSH_HOST')
    upstream = args.upstream_port or ((9743 if robot == 'x5' else 9741) if ssh_host else sim_port)
    port = args.port or (8445 if robot == 'x5' else 8444)
    host = args.bind or env.get('TELEMOVO_BIND', '127.0.0.1')
    cert = args.cert or env.get('TELEMOVO_CERT', str(ROOT / '.local/tls/server.crt'))
    key = args.key or env.get('TELEMOVO_KEY', str(ROOT / '.local/tls/server.key'))
    command = [python, '-B', str(ROOT / 'viewer/gateway.py'), '--robot', robot, '--host', host,
               '--port', str(port), '--upstream-port', str(upstream), '--cert', str(cert), '--key', str(key)]
    tunnel = ['ssh', '-NT', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8',
              '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
              '-L', f'127.0.0.1:{upstream}:127.0.0.1:{sim_port}', '--', ssh_host] if ssh_host else None
    return command, env, tunnel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('service', choices=['simulation', 'gateway'])
    parser.add_argument('--robot', choices=['franka', 'x5'], default='franka')
    parser.add_argument('--python', help='Existing target interpreter; no installation is performed')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--simulation-port', type=int, choices=[9740, 9742])
    parser.add_argument('--seconds', type=int, default=1800)
    parser.add_argument('--teleop', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--bind')
    parser.add_argument('--port', type=int)
    parser.add_argument('--upstream-port', type=int)
    parser.add_argument('--ssh-host')
    parser.add_argument('--cert')
    parser.add_argument('--key')
    args = parser.parse_args()
    if args.seconds <= 0 or any(p is not None and not 1 <= p <= 65535 for p in (args.port, args.upstream_port)):
        parser.error('Positive duration and ports in 1..65535 required')
    command, env, tunnel = plan(args)
    if args.dry_run:
        print(json.dumps({'command': command, 'tunnel': tunnel,
                          'environment': {k: env.get(k) for k in ('CUDA_VISIBLE_DEVICES', 'EGL_DEVICE_ID', 'PYTHONPATH')}}, indent=2))
        return
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    if not tunnel:
        os.execvpe(command[0], command, env)
    processes = []
    def stop(*_):
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    try:
        processes.append(subprocess.Popen(tunnel))
        try:
            code = processes[0].wait(timeout=1)
        except subprocess.TimeoutExpired:
            code = None
        if code is not None:
            raise RuntimeError(f'SSH tunnel failed: exit {code}')
        processes.append(subprocess.Popen(command, env=env))
        while True:
            try:
                code = processes[1].wait(timeout=1)
                break
            except subprocess.TimeoutExpired:
                if processes[0].poll() is not None:
                    raise RuntimeError('SSH tunnel disconnected; stopping gateway')
        raise SystemExit(code)
    finally:
        stop()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
