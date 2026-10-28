# Third-party sources and license boundaries

## Genesis contact patch

Upstream: https://github.com/Genesis-Embodied-AI/genesis-world

Pinned commit: `9727f6e857d8ea6951a30fd761bc489c82e224ec`.
Observed distribution version: `genesis-world 1.3.1`.

The contact patch and the unmodified contact source fixture derive from
`genesis/engine/couplers/legacy_coupler.py` at that commit. Genesis uses
Apache-2.0; the license is reproduced in
[Genesis-Apache-2.0.txt](patches/licenses/Genesis-Apache-2.0.txt).
The fixture is unmodified. The patch changes PBD/rigid contact to provide optional
per-geometry static/dynamic friction, adjusts normal reaction accounting, and
removes the depenetration contribution to bounce velocity. It adds no adhesion
or particle binding. Hashes in [the manifest](patches/manifest.json) identify both
the original and modified contact files. The installer writes an adjacent
`TELEMOVO-CONTACT-NOTICE.json` in its isolated runtime copy.

## External models (not distributed here)

- Franka Panda: the tested MJCF was derived from Genesis's
  `assets/xml/franka_emika_panda`, whose model README identifies the Franka
  description and Apache-2.0. The tested local copy uses explicit planar finger
  collision pads. Only hashes are distributed; import the matching model and
  preserve its upstream license notices locally. An arbitrary stock Panda model
  is not assumed to reproduce these contacts.
- X5: RoboDojo `Robots/x5/X5A.urdf` and associated meshes. Exact file hashes are
  recorded; this package does not establish redistribution permission for them.
- Garment: RoboDojo `Object/RoboDojo/Garment/Top_Long/00004/object.usdz`, exported
  with a saved layout. Source, layout and exported OBJ hashes are recorded.
  Neither the USDZ nor derived OBJ is distributed here.

The RoboDojo/X5 asset license and availability have not been independently
established in this packaging work. Users must obtain permitted copies; an
import checksum is an identity check, not a license grant.

## Related projects

XRoboToolkit and Open-TeleVision are relevant alternative approaches, not bundled
dependencies of the TeleMovo WebXR path. PICO, Genesis, Franka and RoboDojo names
identify compatibility or provenance and do not imply endorsement.

## TeleMovo source

The owner has not selected a project-wide open-source license. No license badge
or license grant for original TeleMovo code is asserted in this prepared snapshot.
