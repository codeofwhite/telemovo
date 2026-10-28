"""Resolve asset paths relative to the selected robot configuration, not cwd."""
import json
import math
from pathlib import Path


def load_config(directory, *, require_assets=True):
    directory = Path(directory).resolve()
    physics = json.loads((directory / 'config.json').read_text())
    control = json.loads((directory / 'teleop_config.json').read_text())
    robot = physics.get('robot_type', 'franka')
    if robot not in ('franka', 'x5') or control.get('robot_type', 'franka') != robot:
        raise ValueError('Robot profile/config mismatch')
    dt, hz = physics['dt'], control['control_hz_sim']
    if not all(math.isfinite(v) and v > 0 for v in (dt, hz)):
        raise ValueError('Positive finite physics dt and control frequency required')
    decimation = round(1 / (dt * hz))
    if decimation < 1 or abs(decimation * dt * hz - 1) > 1e-8:
        raise ValueError('Control frequency must evenly divide physics step frequency')
    for key in ('robot_asset', 'garment_asset'):
        path = Path(physics[key]).expanduser()
        path = (directory / path).resolve() if not path.is_absolute() else path.resolve()
        if require_assets and not path.is_file():
            raise FileNotFoundError(f'{key}: {path}. Import assets first; see docs/assets.zh-CN.md')
        physics[key] = str(path)
    return physics, control
