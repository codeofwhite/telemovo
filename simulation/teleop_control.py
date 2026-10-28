"""Dynamic joint-servo teleoperation. Cloth writes occur only in explicit reset."""
import json
import math
from pathlib import Path
import threading
import time
import numpy as np
from robot_profiles import profile

ROOT=Path(__file__).resolve().parent
SIDES=('left','right')


def array(x):
    return x.detach().cpu().numpy().copy() if hasattr(x,'detach') else np.array(x,copy=True)


def qmul(a,b):
    x,y,z,w=a;X,Y,Z,W=b
    return np.array([w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z])


def qinv(q):return np.array([-q[0],-q[1],-q[2],q[3]])


def qmatrix(q):
    x,y,z,w=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def rotvec(q):
    q=np.asarray(q);q=q if q[3]>=0 else -q;n=np.linalg.norm(q[:3])
    return q[:3]*(2*math.atan2(n,q[3])/n) if n>1e-9 else np.zeros(3)


def work_surface_height(t):
    return t['table_top_m']+t.get('platform',{}).get('height_m',0.)


def work_surface_bounds(t):
    platform=t.get('platform')
    center=np.asarray(platform['center_xy_m'] if platform else [0.,0.])
    size=np.asarray(platform['size_xy_m'] if platform else [1.4,1.1])
    return center-size/2,center+size/2


def support_valid_fraction(p,t):
    """Check top penetration inside the support; permit approved overhang outside it."""
    lo,hi=work_surface_bounds(t)
    inside=np.all((p[:,:2]>=lo)&(p[:,:2]<=hi),axis=1)
    floor=np.where(inside,work_surface_height(t),t['table_top_m'])
    return float(np.mean(p[:,2]>=floor-.005))


def build(cfg,t,before_build=None,platform_entities=None):
    import genesis as gs
    scene=gs.Scene(show_viewer=False,
        sim_options=gs.options.SimOptions(dt=cfg['dt'],substeps=cfg['substeps']),
        pbd_options=gs.options.PBDOptions(particle_size=cfg['particle_size_m'],gravity=(0,0,-19.62),
            max_stretch_solver_iterations=cfg['stretch_iterations'],max_bending_solver_iterations=cfg['bending_iterations'],
            lower_bound=(-1.5,-1.5,-.1),upper_bound=(1.5,1.5,2.)),
        rigid_options=gs.options.RigidOptions(iterations=100,tolerance=1e-8),
        profiling_options=gs.options.ProfilingOptions(show_FPS=False))
    rigid=gs.materials.Rigid(needs_coup=True,coup_friction=cfg.get('rigid_friction',.5),coup_restitution=0.)
    scene.add_entity(gs.morphs.Plane(),material=rigid)
    table=scene.add_entity(gs.morphs.Box(size=(1.4,1.1,.05),pos=(0,0,t['table_top_m']-.025),fixed=True),material=rigid)
    supports=[]
    if t.get('platform'):
        platform=t['platform'];height=platform['height_m'];thickness=platform['top_thickness_m']
        if not 0<thickness<height:raise ValueError('Platform requires 0 < top thickness < height')
        cx,cy=platform['center_xy_m'];sx,sy=platform['size_xy_m'];px,py=platform['pillar_size_xy_m']
        if not all(math.isfinite(v) for v in [height,thickness,cx,cy,sx,sy,px,py]) or min(sx,sy,px,py)<=0:
            raise ValueError('Invalid platform dimensions')
        supports.append(scene.add_entity(gs.morphs.Box(size=(sx,sy,thickness),
            pos=(cx,cy,work_surface_height(t)-thickness/2),fixed=True),material=rigid))
        supports.append(scene.add_entity(gs.morphs.Box(size=(px,py,height-thickness),
            pos=(cx,cy,t['table_top_m']+(height-thickness)/2),fixed=True),material=rigid))
    if platform_entities is not None:platform_entities.extend(supports)
    if cfg.get('robot_type','franka')!=t.get('robot_type','franka'):raise ValueError('Robot profile/config mismatch')
    spec=profile(t);robots=[]
    for root,yaw in zip(spec['roots'],spec['yaw_deg']):
        kwargs=dict(file=cfg['robot_asset'],requires_jac_and_IK=True,
                    pos=(root[0],root[1],t['table_top_m']),euler=(0,0,yaw))
        if spec['importer']=='URDF':kwargs.update(fixed=True,links_to_keep=[spec['tool_link']])
        robots.append(scene.add_entity(getattr(gs.morphs,spec['importer'])(**kwargs),material=rigid))
    asset=Path(cfg.get('garment_asset',ROOT/'assets/garment.obj'))
    source_min=min(float(line.split()[3]) for line in asset.read_text().splitlines() if line.startswith('v '))
    dz=work_surface_height(t)+t['spawn_clearance_m']-source_min
    cloth=scene.add_entity(gs.morphs.Mesh(file=str(asset),pos=(0,0,dz)),
        material=gs.materials.PBD.Cloth(rho=cfg['areal_density_kg_m2'],static_friction=cfg.get('static_friction',.5),kinetic_friction=cfg.get('kinetic_friction',.5),
            stretch_compliance=cfg['stretch_compliance'],bending_compliance=cfg['bending_compliance'],
            stretch_relaxation=cfg.get('stretch_relaxation',.3),bending_relaxation=cfg.get('bending_relaxation',.1),air_resistance=cfg.get('air_resistance',0.)),
        surface=gs.surfaces.Default(color=(.85,.18,.35,1.),double_sided=True))
    if before_build is not None:before_build(scene)
    scene.build()
    if 'table_static_friction' in cfg or 'table_kinetic_friction' in cfg:
        if not hasattr(scene.sim.coupler,'set_pbd_friction_pair'):
            raise RuntimeError('Pair friction requires the pinned TeleMovo contact patch; see docs/setup.zh-CN.md')
        for support in [table,*supports]:
            if len(support.geoms)!=1:raise ValueError('Each work surface requires exactly one collision geom')
            scene.sim.coupler.set_pbd_friction_pair(int(support.geoms[0].idx),
                cfg['table_static_friction'],cfg['table_kinetic_friction'])
    if 'finger_static_friction' in cfg:
        for robot in robots:
            pads=[g for g in robot.geoms if g.link.name in spec['finger_links']]
            if len(pads)!=2:raise ValueError('Expected exactly two collision pads per robot')
            for pad in pads:scene.sim.coupler.set_pbd_friction_pair(int(pad.idx),
                cfg['finger_static_friction'],cfg['finger_kinetic_friction'])
    return scene,table,robots,cloth,dz


class TeleopControl:
    def __init__(self,robots,cloth,cfg,dt):
        self.cfg=cfg;self.dt=dt;self.robots=robots;self.cloth=cloth
        self.lock=threading.RLock();self.owner=None;self.latest=None;self.received=0.;self.seq=-1
        self.pending_reset=False;self.error=None;self.accepted=0;self.rejected=0;self.reset_count=0
        self.arms=[];self.spec=profile(cfg)
        self.birth=array(cloth.get_particles_pos())
        for side,robot in zip(SIDES,robots):
            ids=[int(robot.get_joint(n).dofs_idx_local[0]) for n in self.spec['arm_joints']]
            fingers=[int(robot.get_joint(n).dofs_idx_local[0]) for n in self.spec['finger_joints']]
            lo,hi=map(array,robot.get_dofs_limit());q=array(robot.get_dofs_position()).reshape(-1)
            # This pinned Genesis version exposes DOF deflections qpos-qpos0,
            # but get_dofs_limit returns absolute MJCF generalized-coordinate limits.
            absolute=array(robot.get_qpos()).reshape(-1)
            if absolute.shape!=q.shape:raise ValueError('Expected fixed-base scalar robot joints')
            reference=absolute-q;lo=lo-reference;hi=hi-reference
            if 'initial_arm_qpos' in cfg:
                initial=np.asarray(cfg['initial_arm_qpos'][SIDES.index(side)],dtype=float)
                if initial.shape!=(len(ids),) or not np.isfinite(initial).all():raise ValueError('Invalid initial arm posture')
                q[ids]=initial-reference[ids]
                if np.any(q[ids]<lo[ids]) or np.any(q[ids]>hi[ids]):raise ValueError('Initial posture exceeds model limits')
            q[fingers]=hi[fingers]
            robot.set_dofs_position(q);robot.zero_all_dofs_velocity()
            robot.set_dofs_kp(np.asarray(cfg['arm_kp']),ids);robot.set_dofs_kv(np.asarray(cfg['arm_kv']),ids)
            effort=np.asarray(cfg['arm_force_nm']);robot.set_dofs_force_range(-effort,effort,ids)
            robot.set_dofs_kp(cfg.get('finger_kp',400.),fingers);robot.set_dofs_kv(cfg.get('finger_kv',20.),fingers)
            robot.set_dofs_force_range(-cfg['finger_force_n'],cfg['finger_force_n'],fingers)
            robot.control_dofs_position(q)
            self.arms.append(dict(side=side,robot=robot,ids=ids,fingers=fingers,lo=lo,hi=hi,home=q.copy(),
                command=q.copy(),hand=robot.get_link(self.spec['tool_link']),anchor=None,previous=None,release=True,enabled=False,
                limited=False,error=None,reference_qpos=reference,target=None,target_q=None))

    def ee(self,a):
        p=array(a['hand'].get_pos(relative=False)).reshape(3)
        wxyz=array(a['hand'].get_quat(relative=False)).reshape(4);q=wxyz[[1,2,3,0]]
        return p+qmatrix(q)@np.asarray(self.cfg['tcp_local_m']),q

    def release(self,owner):
        with self.lock:
            if self.owner==owner:self.latest=None;self.received=0.;self.owner=None

    def submit(self,owner,d):
        with self.lock:
            now=time.monotonic()
            if self.owner not in (None,owner) and now-self.received<self.cfg['input_timeout_s']:
                self.rejected+=1;return False
            kind=d.get('type')
            if kind not in ('xr','reset','hold'):raise ValueError('Unknown control message')
            if kind=='hold':
                if self.owner==owner:self.latest=None;self.received=0.
                return True
            if kind=='reset':
                if self.latest and any(h['grip'] for h in self.latest['hands'].values()):
                    raise ValueError('Release both grips before reset')
                self.pending_reset=True;return True
            if d.get('version')!=1 or type(d.get('sequence')) is not int or d['sequence']<0:raise ValueError('Invalid XR sequence/version')
            if self.owner==owner and d['sequence']<=self.seq:self.rejected+=1;return False
            hands=d.get('hands')
            rotation_mode=d.get('rotation_mode','free');input_frame=d.get('input_frame','view')
            if rotation_mode not in ('free','locked') or input_frame not in ('view','table'):
                raise ValueError('Invalid control mode')
            if not isinstance(hands,dict) or set(hands)!=set(SIDES):raise ValueError('Both hands required')
            normalized={}
            for side,h in hands.items():
                if type(h.get('valid')) is not bool or type(h.get('grip')) is not bool:raise ValueError('Invalid tracking flags')
                p=np.asarray(h.get('pose'),dtype=float)
                if p.shape!=(7,) or not np.isfinite(p).all() or np.linalg.norm(p[3:])<1e-8:raise ValueError('Invalid pose')
                trigger=h.get('trigger')
                if type(trigger) not in (int,float) or not math.isfinite(trigger) or not 0<=trigger<=1:raise ValueError('Invalid trigger')
                p[3:]/=np.linalg.norm(p[3:]);normalized[side]=dict(h,pose=p)
            if self.owner!=owner or now-self.received>self.cfg['input_timeout_s']:
                for a in self.arms:a['release']=True;a['anchor']=None;a['previous']=None
            if self.latest and (rotation_mode!=self.latest['rotation_mode'] or input_frame!=self.latest['input_frame']) and any(h['grip'] for h in normalized.values()):
                raise ValueError('Release both grips before changing control mode')
            self.owner=owner;self.latest={'hands':normalized,'rotation_mode':rotation_mode,'input_frame':input_frame};self.received=now;self.seq=d['sequence'];self.accepted+=1
            # Latch release even if input is faster than the physics control tick.
            for a in self.arms:
                if not normalized[a['side']]['grip']:a['release']=False;a['anchor']=None;a['previous']=None
            return True

    def reset(self):
        self.cloth.set_particles_pos(self.birth.copy());self.cloth.set_particles_vel(np.zeros_like(self.birth))
        for a in self.arms:
            a['robot'].set_dofs_position(a['home']);a['robot'].zero_all_dofs_velocity()
            a['command']=a['home'].copy();a['robot'].control_dofs_position(a['command'])
            a.update(anchor=None,previous=None,release=True,enabled=False,error=None,target=None,target_q=None)
        self.latest=None;self.received=0.;self.pending_reset=False;self.reset_count+=1

    def advance(self):
        with self.lock:
            if self.pending_reset:self.reset()
            fresh=self.latest is not None and time.monotonic()-self.received<=self.cfg['input_timeout_s']
            for a in self.arms:
                robot=a['robot'];q=array(robot.get_dofs_position()).reshape(-1);ids=a['ids'];f=a['fingers']
                if not np.isfinite(q).all():raise RuntimeError('Nonfinite robot joints')
                if np.max(np.maximum(a['lo']-q,q-a['hi']))>.003:
                    raise RuntimeError('Robot joint limit exceeded: '+json.dumps(dict(side=a['side'],q=q.tolist(),lo=a['lo'].tolist(),hi=a['hi'].tolist())))
                h=self.latest['hands'][a['side']] if fresh else None
                valid=bool(h and h['valid']);enabled=valid and h['grip'] and not a['release']
                if not valid:
                    a['release']=True;a['anchor']=None;a['previous']=None
                    a['error']='Tracking invalid: show controller' if fresh else 'Input stale: release grip'
                elif not h['grip']:a['error']=None
                if not enabled:
                    if a['enabled']:a['command'][ids]=q[ids]
                    a['anchor']=None;a['previous']=None
                    a['target']=None;a['target_q']=None
                else:
                    pose=h['pose'];p,quat=self.ee(a)
                    if a['anchor'] is None:a['anchor']=(pose.copy(),p.copy(),quat.copy())
                    if a['previous'] is not None and (np.linalg.norm(pose[:3]-a['previous'][:3])>self.cfg['tracking_jump_m'] or np.linalg.norm(rotvec(qmul(pose[3:],qinv(a['previous'][3:]))))>self.cfg['tracking_jump_rad']):
                        a['error']='Tracking jump: release grip';enabled=False
                    ref,ep,eq=a['anchor'];target=ep+(pose[:3]-ref[:3])*self.cfg['translation_scale']
                    target_q=eq if self.latest['rotation_mode']=='locked' else qmul(qmul(pose[3:],qinv(ref[3:])),eq)
                    a['target']=target.copy();a['target_q']=target_q.copy()
                    error=np.r_[target-p,rotvec(qmul(target_q,qinv(quat)))]
                    if np.any(target<self.cfg['workspace_lower_m']) or np.any(target>self.cfg['workspace_upper_m']):
                        a['error']='Target outside workspace: release grip';enabled=False
                    if np.linalg.norm(error[:3])>self.cfg['following_position_limit_m'] or np.linalg.norm(error[3:])>self.cfg['following_rotation_limit_rad']:
                        a['error']='Following error: release grip';enabled=False
                    if enabled:
                        jac=array(robot.get_jacobian(a['hand'],local_point=self.cfg['tcp_local_m'])).reshape(6,-1)[:,ids]
                        dq=jac.T@np.linalg.solve(jac@jac.T+self.cfg['dls_damping']**2*np.eye(6),error)
                        cap=self.cfg['joint_velocity_rad_s']*self.dt
                        goal=np.clip(q[ids]+np.clip(dq,-cap,cap),a['lo'][ids],a['hi'][ids])
                        a['limited']=bool(np.any(np.abs(dq)>cap));a['command'][ids]=goal;a['previous']=pose.copy();a['error']=None
                    else:
                        a['command'][ids]=q[ids];a['release']=True;a['anchor']=None;a['previous']=None
                if valid and not a['release']:
                    goal=a['lo'][f]+(1-h['trigger'])*(a['hi'][f]-a['lo'][f])
                    cap=self.cfg['finger_velocity_m_s']*self.dt
                    a['command'][f]+=np.clip(goal-a['command'][f],-cap,cap)
                elif not valid:a['command'][f]=q[f]
                a['enabled']=bool(enabled);robot.control_dofs_position(a['command'])

    def snapshot(self):
        with self.lock:
            return dict(input_age_ms=(time.monotonic()-self.received)*1000 if self.received else None,
                accepted=self.accepted,rejected=self.rejected,reset_count=self.reset_count,
                rotation_mode=self.latest['rotation_mode'] if self.latest else None,
                input_frame=self.latest['input_frame'] if self.latest else None,
                arms={a['side']:dict(enabled=a['enabled'],require_release=a['release'],limited=a['limited'],error=a['error'],
                    target_position_m=a['target'].tolist() if a['target'] is not None else None,
                    target_quat_xyzw=a['target_q'].tolist() if a['target_q'] is not None else None) for a in self.arms})
