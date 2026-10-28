"""Import user-supplied models with recorded hashes; no download or redistribution."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def import_model(robot, source, assets=ROOT / 'assets'):
    source, assets = Path(source).resolve(), Path(assets).resolve()
    expected = json.loads((ROOT / 'assets/sources.json').read_text())[robot]['sha256']
    destination = assets / robot
    if destination.exists():
        raise FileExistsError(f'Asset destination already exists: {destination}')
    for name, digest in expected.items():
        if sha(source / name) != digest:
            raise ValueError(f'{robot} asset checksum mismatch: {name}')
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__'))
    (destination / 'telemovo-import.json').write_text(json.dumps({
        'robot': robot, 'source': str(source), 'verified_sha256': expected,
    }, indent=2) + '\n')
    return destination


def import_garment(source, assets=ROOT / 'assets'):
    source, assets = Path(source).resolve(), Path(assets).resolve()
    expected = json.loads((ROOT / 'assets/sources.json').read_text())['garment']['obj_sha256']
    if sha(source) != expected:
        raise ValueError('Garment checksum mismatch; use the documented exported garment')
    destination = assets / 'garment'
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source, destination / 'garment.obj')
    (destination / 'manifest.json').write_text(json.dumps({
        'source': str(source), 'obj_sha256': expected,
    }, indent=2) + '\n')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot', choices=['franka', 'x5'])
    parser.add_argument('--source', type=Path, help='Model directory including meshes')
    parser.add_argument('--garment', type=Path, help='Already exported garment OBJ')
    args = parser.parse_args()
    if bool(args.robot) != bool(args.source) or not (args.robot or args.garment):
        parser.error('Use --robot ROBOT --source DIR and/or --garment FILE')
    if args.robot:
        print(import_model(args.robot, args.source))
    if args.garment:
        print(import_garment(args.garment))


if __name__ == '__main__':
    main()
