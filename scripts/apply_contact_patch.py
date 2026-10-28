"""Create a separate pinned Genesis package; never patch the installed package."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    manifest = json.loads((ROOT / 'patches/manifest.json').read_text())
    patch = ROOT / 'patches/genesis-contact-v4.patch'
    if digest(patch) != manifest['patch_sha256']:
        raise ValueError('Patch checksum mismatch')
    if digest(source / manifest['file']) != manifest['original_sha256']:
        raise ValueError('Unsupported Genesis source: original contact checksum mismatch')
    if destination.exists() or source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Destination must be new and separate from the source package')
    if shutil.which('patch') is None:
        raise RuntimeError('The system patch command is required')
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(patch)],
                   cwd=destination, check=True)
    if digest(destination / manifest['file']) != manifest['patched_sha256']:
        raise ValueError('Patched contact checksum mismatch; do not use this copy')
    (destination.parent / 'TELEMOVO-CONTACT-NOTICE.json').write_text(json.dumps({
        **manifest, 'modification': 'TeleMovo contact v4: per-geometry Coulomb friction; no adhesion or node binding',
    }, indent=2) + '\n')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Pinned upstream genesis package directory')
    parser.add_argument('--destination', type=Path, default=ROOT / '.runtime/genesis-contact/genesis')
    args = parser.parse_args()
    print(apply(args.source, args.destination))


if __name__ == '__main__':
    main()
