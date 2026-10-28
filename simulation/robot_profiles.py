"""Robot-specific kinematics; source model joint limits remain authoritative."""
PROFILES = {
    'franka': dict(label='双 Franka', importer='MJCF',
        arm_joints=[f'joint{i}' for i in range(1,8)],
        finger_joints=['finger_joint1','finger_joint2'],
        tool_link='hand', finger_links=['left_finger','right_finger'],
        roots=[[-.45,-.45,.765],[.45,-.45,.765]], yaw_deg=[45.,135.]),
    'x5': dict(label='双 X5', importer='URDF',
        arm_joints=[f'joint{i}' for i in range(1,7)],
        finger_joints=['joint7','joint8'],
        tool_link='link6', finger_links=['link7','link8'],
        roots=[[-.30,-.45,.765],[.30,-.45,.765]], yaw_deg=[90.,90.]),
}


def profile(config):
    name=config.get('robot_type','franka')
    if name not in PROFILES:raise ValueError('Unsupported robot_type: '+str(name))
    return PROFILES[name]
