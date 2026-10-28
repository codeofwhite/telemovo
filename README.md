# TeleMovo

**Immersive Robot Teleoperation for Simulation Data Collection**

![TeleMovo: PICO VR teleoperation with a dual-arm cloth simulation; IPPLab watermark](docs/assets/telemovo-hero.png)

TeleMovo connects PICO VR interaction with robot simulation through WebXR,
providing an extensible teleoperation foundation for bimanual manipulation,
deformable-object interaction, and demonstration data-collection research.

The current integration uses Genesis, with Franka Panda and X5 dual-arm examples,
immersive visualization, controller-based teleoperation, and visual operation guides.

[中文](README.zh-CN.md) · [Getting started](docs/setup.zh-CN.md) · [Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md)

## Key features

- **Immersive interaction** — stereoscopic visualization, head tracking, and dual-controller input through the PICO browser.
- **Bimanual control** — relative pose mapping, gripper control, and visual guidance for coordinated manipulation.
- **Deformable simulation** — cloth interaction scenes built on Genesis PBD.
- **Configurable deployment** — local execution or remote simulation with an independent HTTPS gateway.
- **Extensible foundation** — robot profiles and documented interfaces for further integration.

## Getting started

1. Follow the [setup guide](docs/setup.zh-CN.md) to prepare the environment and pinned Genesis integration.
2. Prepare the robot and garment assets using the [asset guide](docs/assets.zh-CN.md).
3. Launch the selected simulation and gateway, then open the gateway address in PICO.

See the [operation guide](docs/operation.zh-CN.md) for calibration and controls.

## Roadmap

- Episode recording, success/failure annotation, and replay.
- Dataset quality checks and LeRobot export.
- Additional robot and simulator adapters.
- Improved operator interaction and cloth-manipulation workflows.

Recording and dataset export are planned extensions to the current teleoperation interface.

## Contributing

Help build TeleMovo with us. Contributions to interaction design, robot adapters,
data workflows, documentation, and testing are welcome. First-time contributors
can start with documentation, setup improvements, or CPU tests without VR hardware.

[Open an issue](https://github.com/codeofwhite/telemovo/issues/new)
· [Browse issues](https://github.com/codeofwhite/telemovo/issues)
· [Contribution guide](CONTRIBUTING.md)
· [Pull requests](https://github.com/codeofwhite/telemovo/pulls)

For substantial changes, open an issue to discuss the proposed scope and validation.

## Documentation

| Guide | Contents |
|---|---|
| [Setup](docs/setup.zh-CN.md) | Environment, deployment, HTTPS, and launch commands |
| [Assets](docs/assets.zh-CN.md) | Model preparation, provenance, and import |
| [Operation](docs/operation.zh-CN.md) | Calibration, controls, and visual guidance |
| [Architecture](docs/architecture.md) | Components, coordinate frames, and protocols |
| [Verification](docs/verification.zh-CN.md) | Development checks and hardware validation |
| [Experiments](docs/results.zh-CN.md) | Evaluation results and current validation scope |
| [Troubleshooting](docs/troubleshooting.zh-CN.md) | Connection, interaction, and simulation diagnostics |

## License and attribution

Project-wide license selection is pending. See [third-party notices](THIRD_PARTY_NOTICES.md)
for component and asset provenance. TeleMovo is an independent community project.
