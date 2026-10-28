"""CPU-only checks; no Genesis import, GPU initialization or service startup."""
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [p for p in ROOT.rglob('*') if p.is_file() and not any(
        part in ('.git', '.runtime', '.local', '.venv', '__pycache__', 'outputs') for part in p.relative_to(ROOT).parts)]
    for path in files:
        if path.suffix == '.py':
            ast.parse(path.read_text(), filename=str(path))
        if path.suffix == '.json':
            json.loads(path.read_text())
        if path.suffix == '.md':
            for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
                if '://' in link or link.startswith('#'):
                    continue
                target = (path.parent / link.split('#')[0]).resolve()
                if not target.is_file() and not target.is_dir():
                    raise ValueError(f'Broken documentation link: {path.relative_to(ROOT)} -> {link}')
    subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT, check=True)
    subprocess.run(['node', '--check', 'viewer/viewer.js'], cwd=ROOT, check=True)
    subprocess.run(['node', 'tests/coordinates.test.cjs'], cwd=ROOT, check=True)
    for name in ('start-simulation.sh', 'start-gateway.sh'):
        subprocess.run(['bash', '-n', 'scripts/' + name], cwd=ROOT, check=True)
    for robot in ('franka', 'x5'):
        for service in ('simulation', 'gateway'):
            result = subprocess.run([sys.executable, '-B', 'scripts/launch.py', service,
                                     '--robot', robot, '--dry-run'], cwd=ROOT, check=True,
                                    capture_output=True, text=True)
            plan = json.loads(result.stdout)
            if plan['tunnel'] is not None:
                raise ValueError('Unexpected SSH tunnel in default local plan')
            if not Path(plan['command'][2]).is_file():
                raise ValueError('Launcher target does not exist')
        result = subprocess.run([sys.executable, '-B', 'scripts/launch.py', 'gateway', '--robot', robot,
                                 '--ssh-host', 'example-gpu', '--dry-run'], cwd=ROOT, check=True,
                                capture_output=True, text=True)
        tunnel = json.loads(result.stdout)['tunnel']
        expected = '127.0.0.1:9743:127.0.0.1:9742' if robot == 'x5' else '127.0.0.1:9741:127.0.0.1:9740'
        if expected not in tunnel:
            raise ValueError('Incorrect robot tunnel mapping')
    print(f'PASS: {len(files)} files inspected; syntax, documentation links, unit tests, browser coordinates, launch plans')


if __name__ == '__main__':
    main()
