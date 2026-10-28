# Contributing to TeleMovo

Welcome! First-time contributors are encouraged to join. Small documentation
fixes, setup improvements, reproducible bug reports and operator feedback all
help. You do not need a headset or GPU to work on documentation or CPU tests.

欢迎参与 TeleMovo。代码、文档、复现记录和实际操作反馈都值得贡献；没有 PICO 或 GPU，
也可以从安装说明和 CPU 测试开始。Issue 和 PR 均可使用中文或英文。

## Choose a contribution

- Improve controller direction mapping, clutching, wrist rotation or operation guides.
- Add a robot or simulator adapter with joint/TCP mapping and validation evidence.
- Build episode recording, outcome labels, replay, quality checks or LeRobot export.
  These are contribution goals, not capabilities already provided by this release.
- Improve asset preparation, setup instructions, tests or measured performance reports.

[Browse issues](https://github.com/codeofwhite/telemovo/issues) or
[open an issue](https://github.com/codeofwhite/telemovo/issues/new) with an idea.
For a substantial change, describe the intended files, behavior and validation
before implementation. There is no requirement to solve a large task to contribute.

## Report a problem

Start with a reproducible issue: robot profile, headset/browser, simulator commit,
contact hash, hardware, network topology, exact command, and observed behavior.
Include a small sanitized diagnostic excerpt rather than private keys, full
machine inventories or large unreviewed logs.

Native cloth grasp/release tests are especially useful. A simulator or robot
adapter should declare coordinate
frames, joints, TCP, timestamps, input ownership and disconnect behavior, then
provide independent evidence that its mapping works.

## Submit a pull request

1. Fork the repository and create a branch for one focused change.
2. Make the change, keeping unrelated tuning or refactoring separate.
3. Run `python3 -B scripts/check_project.py` in a development environment with
   the CPU test dependencies installed. For hardware-dependent changes, also
   describe what you tested on the actual simulator or headset.
4. Open a PR against `main`, explaining the problem, the behavior after the
   change, the checks run and anything that remains unverified. If you lack
   hardware, say so; do not present an unrun check as passed.

CPU tests cannot prove contact stability or real-robot safety. Keep tuning experiments
separate from performance comparisons and retain failed trials.

Before a public release the owner must select an open-source license for the
project's own code. Preserve third-party notices and do not upload model meshes
without establishing their redistribution terms. GitHub publication is not
performed by any launcher or test in this repository.
