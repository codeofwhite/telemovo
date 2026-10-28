# TeleMovo

**WebXR Robot Teleoperation for PICO**

TeleMovo is an experimental browser-based VR teleoperation interface for PICO,
with immersive visualization, guided bimanual control, and Genesis simulation
examples for Franka Panda and X5. Open a headset browser, enter VR, and move the
two simulated arms with your controllers.

[中文](README.zh-CN.md) · [Setup](docs/setup.zh-CN.md) · [Controls](docs/operation.zh-CN.md) · [Architecture](docs/architecture.md) · [Results and limitations](docs/results.zh-CN.md)

The current backend supports Genesis PBD cloth. The viewer renders the scene on
the headset; the server sends geometry and live state rather than a CloudXR
video stream. Adding more robots, simulators and headsets is a project direction,
not a claim of existing compatibility.

## What is included

- PICO WebXR immersive stereo viewing and head tracking.
- Two controller inputs, relative motion with Grip clutching, and Trigger grippers.
- Table-aligned movement, optional wrist rotation, colored TCP guides and practice instructions.
- Franka Panda and X5 profiles, independent simulation/gateway processes, optional SSH forwarding.
- Pinned, isolated Genesis contact patch, asset provenance, material checks and benchmarking tools.
- CPU tests and GitHub Actions checks; no headset or GPU required for these checks.

## Project status

This is a research prototype. Actual headset trials demonstrated viewing and
dual-arm control, but the operator still found it difficult to use. Reliable
cloth pickup, release and folding have **not** been established. The X5 fixed-point
grasp test failed. Simulator self-tests passing does not establish task success.

The current launchers do not record demonstration episodes or export LeRobot
datasets. Earlier Isaac/CloudXR and dataset-studio experiments are outside this
repository. There is no real-robot driver here.

## Quick start

Prerequisites: Linux NVIDIA GPU machine with a compatible PyTorch/Genesis
environment, PICO with a WebXR-capable browser, and a shared LAN. The historical
validation used one RTX 5090 on an eight-GPU server. Gateway and simulation can
also run on the same computer; this deployment has not been revalidated here.

1. Use the Genesis source commit in [patches/manifest.json](patches/manifest.json).
   Install the selected GPU environment as described in the setup guide.
2. Import the external robot and garment assets following [the asset guide](docs/assets.zh-CN.md).
   Third-party model meshes are not distributed in this repository.
3. Create the isolated contact package:

   ```bash
   python3 -B scripts/apply_contact_patch.py --source /path/to/genesis-world/genesis
   ```

4. Start the simulation with your existing environment:

   ```bash
   bash scripts/start-simulation.sh --robot franka --teleop --python /path/to/sim-env/bin/python
   ```

5. Start the gateway with a certificate trusted by the headset:

   ```bash
   bash scripts/start-gateway.sh --robot franka --bind YOUR_LAN_IP \
     --cert /path/to/server.crt --key /path/to/server.key \
     --python /path/to/gateway-env/bin/python
   ```

6. In PICO, visit `https://YOUR_LAN_IP:8444/?teleop=1`, enter VR with both Grips
   released, then hold one Grip and make a small movement. Use `--robot x5` and
   gateway port `8445` for X5. Each simulation exits after 1800 seconds by default;
   change `--seconds` explicitly for a longer session.

Use `--dry-run` on either launcher to inspect commands without starting anything.
Remote simulation through SSH, HTTPS certificates and the read-only viewer are
documented in [setup](docs/setup.zh-CN.md).

## Development checks

```bash
# Inside a development environment with requirements/test.txt installed:
python3 -B scripts/check_project.py
```

These checks verify configuration, input validation, coordinate mapping and patch
reproduction. They do not measure VR latency, GPU physics performance or cloth
grasp success. See [verification](docs/verification.zh-CN.md).

## Attribution and license status

Independent community project; not an official PICO, Genesis or Franka release.
See [third-party notices](THIRD_PARTY_NOTICES.md). The project's own open-source
license has not yet been selected by the owner; source availability alone is not
an open-source license grant. Select a license before a public open-source release.
