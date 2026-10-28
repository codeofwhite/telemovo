# Contributing to TeleMovo

Start with a reproducible issue: robot profile, headset/browser, simulator commit,
contact hash, hardware, network topology, exact command, and observed behavior.
Include a small sanitized diagnostic excerpt rather than private keys, full
machine inventories or large unreviewed logs.

Useful contributions include easier clutch/rotation interaction, reproducible
asset preparation, real headset performance measurements, and native cloth
grasp/release tests. A simulator or robot adapter should declare coordinate
frames, joints, TCP, timestamps, input ownership and disconnect behavior, then
provide independent evidence that its mapping works.

Run `python3 -B scripts/check_project.py` before proposing a change. CPU tests
cannot prove contact stability or real-robot safety. Keep tuning experiments
separate from performance comparisons and retain failed trials.

Before a public release the owner must select an open-source license for the
project's own code. Preserve third-party notices and do not upload model meshes
without establishing their redistribution terms. GitHub publication is not
performed by any launcher or test in this repository.
