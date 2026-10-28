import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))
from configuration import load_config
from teleop_control import TeleopControl, support_valid_fraction
import numpy as np


class ConfigurationTests(unittest.TestCase):
    def test_both_profiles_resolve_independently_of_cwd(self):
        for robot, joints in [('franka', 7), ('x5', 6)]:
            config, control = load_config(ROOT / 'configs' / robot, require_assets=False)
            self.assertTrue(Path(config['robot_asset']).is_relative_to(ROOT / 'assets' / robot))
            self.assertEqual(len(control['arm_kp']), joints)
            self.assertEqual(control['control_hz_sim'], 50)
            self.assertEqual(control['platform']['height_m'], .12)

    def test_wrong_robot_and_nonintegral_control_frequency_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in ('config.json', 'teleop_config.json'):
                (directory / name).write_bytes((ROOT / 'configs/franka' / name).read_bytes())
            cfg = json.loads((directory / 'config.json').read_text())
            cfg['robot_type'] = 'x5'
            (directory / 'config.json').write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):
                load_config(directory, require_assets=False)
            cfg['robot_type'] = 'franka'
            cfg['dt'] = .003
            (directory / 'config.json').write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):
                load_config(directory, require_assets=False)

    def test_overhang_uses_table_outside_platform_and_five_mm_tolerance(self):
        _, config = load_config(ROOT / 'configs/x5', require_assets=False)
        top = config['table_top_m'] + .12
        particles = np.array([[0, -.1, top - .0049], [0, -.31, .765], [0, -.1, top - .0051]])
        self.assertAlmostEqual(support_valid_fraction(particles, config), 2/3)


class InputTests(unittest.TestCase):
    def setUp(self):
        control = TeleopControl.__new__(TeleopControl)
        control.cfg = {'input_timeout_s': .25}
        control.lock = threading.RLock()
        control.owner = None
        control.latest = None
        control.received = 0.
        control.seq = -1
        control.accepted = control.rejected = 0
        control.arms = [dict(side=side, release=True, anchor=None, previous=None) for side in ('left', 'right')]
        self.control = control
        hand = dict(pose=[0,0,1,0,0,0,1], valid=True, grip=False, trigger=0.)
        self.packet = dict(type='xr', version=1, sequence=1, hands={side:copy.deepcopy(hand) for side in ('left','right')},
                           input_frame='table', rotation_mode='locked')

    def test_ownership_sequence_hold_and_disconnect(self):
        c = self.control
        self.assertTrue(c.submit('alice', self.packet))
        self.assertFalse(c.submit('bob', self.packet))
        self.assertFalse(c.submit('alice', self.packet))
        c.submit('bob', {'type':'hold'})
        self.assertIsNotNone(c.latest)
        c.submit('alice', {'type':'hold'})
        self.assertIsNone(c.latest)
        c.release('alice')
        self.assertIsNone(c.owner)

    def test_invalid_tracking_or_trigger_cannot_enter_control_state(self):
        for field, value in [('pose',[0,0,1,float('nan'),0,0,1]), ('trigger',1.1), ('valid',1)]:
            packet = copy.deepcopy(self.packet)
            packet['hands']['left'][field] = value
            with self.assertRaises(ValueError):
                self.control.submit('alice', packet)
            self.assertIsNone(self.control.latest)

    def test_mode_change_and_reset_require_released_grips(self):
        c = self.control
        c.submit('alice', self.packet)
        packet = copy.deepcopy(self.packet)
        packet['sequence'] = 2
        packet['hands']['left']['grip'] = True
        c.submit('alice', packet)
        with self.assertRaises(ValueError):
            c.submit('alice', {'type':'reset'})
        packet['sequence'] = 3
        packet['rotation_mode'] = 'free'
        with self.assertRaises(ValueError):
            c.submit('alice', packet)


class PatchTests(unittest.TestCase):
    def test_patch_exactly_reconstructs_verified_contact_without_touching_source(self):
        spec = importlib.util.spec_from_file_location('patcher', ROOT / 'scripts/apply_contact_patch.py')
        patcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(patcher)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'upstream/genesis'
            target = Path(tmp) / 'isolated/genesis'
            contact = source / 'engine/couplers/legacy_coupler.py'
            contact.parent.mkdir(parents=True)
            original = (ROOT / 'patches/upstream-contact.py.txt').read_bytes()
            contact.write_bytes(original)
            patcher.apply(source, target)
            self.assertEqual(contact.read_bytes(), original)
            expected = json.loads((ROOT / 'patches/manifest.json').read_text())['patched_sha256']
            self.assertEqual(patcher.digest(target / 'engine/couplers/legacy_coupler.py'), expected)
            with self.assertRaises(ValueError):
                patcher.apply(source, target)
            contact.write_text('wrong version')
            with self.assertRaises(ValueError):
                patcher.apply(source, Path(tmp) / 'other/genesis')


if __name__ == '__main__':
    unittest.main()
