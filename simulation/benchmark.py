"""Time the current robot/cloth configuration; never substitute a simpler scene."""
import argparse
import json
import os
from pathlib import Path
import time
from configuration import load_config

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', type=Path, default=ROOT / 'configs/franka')
    parser.add_argument('--mode', choices=['physics', 'render'], required=True)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--output', type=Path, required=True, help='New result directory')
    args = parser.parse_args()
    if not 0 < args.seconds < 3600:
        parser.error('Measurement duration must be in (0, 3600) seconds')
    cfg, control_cfg = load_config(args.config_dir)
    args.output.mkdir(parents=True, exist_ok=False)
    cache = ROOT / 'outputs/cache-benchmark'
    for key, name in {'GS_CACHE_FILE_PATH': 'genesis', 'XDG_CACHE_HOME': 'xdg', 'TMPDIR': 'tmp'}.items():
        path = cache / name
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    os.environ['PYOPENGL_PLATFORM'] = 'egl'
    import genesis as gs
    import numpy as np
    import torch
    from teleop_control import build, TeleopControl
    gs.init(backend=gs.gpu, seed=1, logging_level='warning')
    camera = []
    def add_camera(scene):
        if args.mode == 'render':
            camera.append(scene.add_camera(res=(640, 480), pos=(0, -.9, 1.7),
                                           lookat=(0, -.05, .90), fov=60, GUI=False))
    scene, _, robots, cloth, _ = build(cfg, control_cfg, before_build=add_camera)
    every = round(1 / (cfg['dt'] * control_cfg['control_hz_sim']))
    control = TeleopControl(robots, cloth, control_cfg, every * cfg['dt'])
    def step(i):
        if i % every == 0:
            control.advance()
        scene.step()
    for i in range(100):
        step(i)
    if camera:
        camera[0].render()
    torch.cuda.synchronize()
    start = time.perf_counter()
    step_ms, render_ms, steps = [], [], 0
    while time.perf_counter() - start < args.seconds:
        tick = time.perf_counter()
        step(steps)
        torch.cuda.synchronize()
        step_ms.append((time.perf_counter() - tick) * 1000)
        steps += 1
        if camera and steps % 4 == 0:
            tick = time.perf_counter()
            camera[0].render()
            torch.cuda.synchronize()
            render_ms.append((time.perf_counter() - tick) * 1000)
    wall = time.perf_counter() - start
    def summary(samples):
        return ({'mean_ms': float(np.mean(samples)), 'p95_ms': float(np.percentile(samples, 95)),
                 'max_ms': float(np.max(samples))} if samples else None)
    result = dict(physics_config=cfg, control_config=control_cfg, mode=args.mode, steps=steps,
                  wall_s=wall, physics_rtf=steps * cfg['dt'] / wall, physics_step=summary(step_ms),
                  render_call=summary(render_ms), particle_count=cloth.n_particles,
                  limits=['Step includes servo control at configured simulation frequency',
                          'CUDA synchronized per step; not identical to live asynchronous scheduling',
                          'Optional 640x480 server camera is a diagnostic, not the PICO renderer',
                          'Does not measure headset FPS, network latency, or grasp quality'])
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
