"""Isolated cloth/contact calibration; no particle attachments or success fallback."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from configuration import load_config
import time
import traceback

ROOT=Path(__file__).resolve().parent


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--profile',choices=['baseline','contact','damped','soft_bend'],required=True)
    ap.add_argument('--config-dir',type=Path,default=ROOT.parent/'configs/franka')
    ap.add_argument('--tag',required=True)
    ap.add_argument('--idle-seconds',type=int,default=30)
    ap.add_argument('--bend-relaxation',type=float,choices=[.02,.005,.002,.001],default=None)
    ap.add_argument('--stretch-iterations',type=int,choices=[6,12,24],default=None)
    ap.add_argument('--bimanual-fold',action='store_true')
    ap.add_argument('--grasp-only',action='store_true',help='Only validate lift, release, reset and reach; no fold claim')
    ap.add_argument('--contact-probe',action='store_true',help='Read native rigid contacts after settle, then exit without a grasp claim')
    ap.add_argument('--record-video',action='store_true')
    ap.add_argument('--grasp-xy',type=float,nargs=2,default=None)
    ap.add_argument('--table-static-friction',type=float,default=None)
    ap.add_argument('--table-kinetic-friction',type=float,default=None)
    ap.add_argument('--finger-static-friction',type=float,default=None)
    ap.add_argument('--finger-kinetic-friction',type=float,default=None)
    ap.add_argument('--grasp-height-m',type=float,default=None,
                    help='Explicit diagnostic TCP target height above work surface; default uses raised crease')
    args=ap.parse_args()
    if not args.tag.replace('-','').replace('_','').isalnum():ap.error('simple tag required')
    if args.grasp_only and args.bimanual_fold:ap.error('Select grasp-only or bimanual-fold')
    if (args.finger_static_friction is None)!=(args.finger_kinetic_friction is None):
        ap.error('Both finger friction coefficients must be specified together')
    if args.finger_static_friction is not None and (not math.isfinite(args.finger_static_friction)
            or not math.isfinite(args.finger_kinetic_friction)
            or not 0<=args.finger_kinetic_friction<=args.finger_static_friction):
        ap.error('Require finite finger static >= kinetic >= 0')
    if (args.table_static_friction is None)!=(args.table_kinetic_friction is None):
        ap.error('Both table friction coefficients must be specified together')
    if args.table_static_friction is not None and (not math.isfinite(args.table_static_friction)
            or not math.isfinite(args.table_kinetic_friction)
            or not 0<=args.table_kinetic_friction<=args.table_static_friction):
        ap.error('Require finite table static >= kinetic >= 0')
    root=args.config_dir.resolve()
    out=root/'outputs'/args.tag;out.mkdir(exist_ok=False,parents=True)
    for key,name in {'GS_CACHE_FILE_PATH':'genesis','XDG_CACHE_HOME':'xdg','TMPDIR':'tmp','NUMBA_CACHE_DIR':'numba','MPLCONFIGDIR':'matplotlib'}.items():
        p=ROOT.parent/'outputs/cache-material'/name;p.mkdir(parents=True,exist_ok=True);os.environ[key]=str(p)
    os.environ['PYOPENGL_PLATFORM']='egl'
    cfg,_=load_config(root)
    # Baseline values are explicit even after a selected profile is deployed.
    cfg.update(static_friction=.5,kinetic_friction=.5,rigid_friction=.5,
               stretch_relaxation=.3,bending_relaxation=.1,air_resistance=0.)
    if args.profile in ('damped','soft_bend'):
        cfg.update(air_resistance=1e-4,static_friction=.8,kinetic_friction=.6,rigid_friction=.8)
    if args.profile=='soft_bend':cfg['bending_relaxation']=.02
    if args.bend_relaxation is not None:cfg['bending_relaxation']=args.bend_relaxation
    if args.stretch_iterations is not None:cfg['stretch_iterations']=args.stretch_iterations
    if args.finger_static_friction is not None:
        cfg.update(finger_static_friction=args.finger_static_friction,finger_kinetic_friction=args.finger_kinetic_friction)
    if args.table_static_friction is not None:
        cfg.update(table_static_friction=args.table_static_friction,table_kinetic_friction=args.table_kinetic_friction)
    result=dict(status='initializing',profile=args.profile,config=cfg,phases=[],gates={},
                grasp_height_above_table_m=args.grasp_height_m,
                fixed_grasp_xy_m=args.grasp_xy,
                record_video=args.record_video,
                timing_scope='physics, control and state readback; excludes video only when record_video=false',
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitations=['Calibration is not a validated real cloth material model',
                             'No adhesion, attachment, particle pinning, or automatic cloth rescue'])
    def publish():
        (out/'result.json').write_text(json.dumps(result,indent=2))
    publish()
    (out/'validator-source.py').write_bytes(Path(__file__).read_bytes())
    try:
        import genesis as gs
        import numpy as np
        import torch
        from teleop_control import build,TeleopControl,array,qmatrix,rotvec,qmul,qinv,work_surface_height,work_surface_bounds,support_valid_fraction
        gs.init(backend=gs.gpu,seed=1,logging_level='warning')
        result['genesis_source']=gs.__file__
        contact_source=Path(gs.__file__).parent/'engine/couplers/legacy_coupler.py'
        result['contact_sha256']=hashlib.sha256(contact_source.read_bytes()).hexdigest()
        (out/'coupler-source.py').write_bytes(contact_source.read_bytes())
        tcfg=json.loads((root/'teleop_config.json').read_text())
        result['teleop_config']=tcfg
        for name in ['config.json','teleop_config.json','teleop_control.py']:
            (out/('input-'+name)).write_bytes(((ROOT if name.endswith('.py') else root)/name).read_bytes())
        cameras=[]
        top=work_surface_height(tcfg);support_lo,support_hi=work_surface_bounds(tcfg)
        result['work_surface_top_m']=top
        def add_cameras(scene):
            cameras.append(scene.add_camera(res=(640,480),pos=(0,-.95,1.75),lookat=(0,-.05,top+.115),
                                            fov=75,near=.01,GUI=False))
            cameras.append(scene.add_camera(res=(640,480),pos=(-.1,-.42,top+.295),lookat=(-.1,-.08,top+.055),
                                            fov=55,near=.01,GUI=False))
        platforms=[]
        scene,table,robots,cloth,dz=build(cfg,tcfg,before_build=add_cameras if args.record_video else None,
                                       platform_entities=platforms)
        result['platform_collision_bounds_m']=[array(entity.geoms[0].get_AABB()).tolist() for entity in platforms]
        if args.table_static_friction is not None:
            pairs=scene.sim.coupler.pbd_friction_pair_mu.to_numpy()
            enabled=scene.sim.coupler.pbd_friction_pair_enabled.to_numpy()
            result['registered_pairs']=[dict(geom_idx=int(i),coefficients=pairs[i].tolist()) for i in np.where(enabled)[0]]
        control=TeleopControl(robots,cloth,tcfg,.02)
        for a in control.arms:a['robot'].get_jacobian(a['hand'],local_point=tcfg['tcp_local_m'])
        # Save actual solver particles throughout, not fabricated folded states.
        frames=[];times=[];labels=[];step_count=0;quality=dict(max_edge_ratio=1.,max_p99_edge_ratio=1.,max_tcp_error_m=0.)
        faces=np.asarray(cloth._mesh.faces)
        edges=np.unique(np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
        rest=array(cloth.get_particles_pos()).reshape(-1,3)
        rest_lengths=np.linalg.norm(rest[edges[:,0]]-rest[edges[:,1]],axis=1)
        def sample(label):
            p=array(cloth.get_particles_pos()).reshape(-1,3)
            v=array(cloth.get_particles_vel()).reshape(-1,3)
            if not np.isfinite(p).all() or not np.isfinite(v).all():raise RuntimeError('Nonfinite cloth state')
            frames.append(p);times.append(step_count*cfg['dt']);labels.append(label)
            ratios=np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1)/np.maximum(rest_lengths,1e-9)
            quality['max_edge_ratio']=max(quality['max_edge_ratio'],float(ratios.max()))
            quality['max_p99_edge_ratio']=max(quality['max_p99_edge_ratio'],float(np.percentile(ratios,99)))
            return dict(sim_s=times[-1],bounds_m=[p.min(0).tolist(),p.max(0).tolist()],
                        com_m=p.mean(0).tolist(),speed_p99_m_s=float(np.percentile(np.linalg.norm(v,axis=1),99)),
                        above_table_fraction=float(np.mean(p[:,2]>=tcfg['table_top_m']-.005)),
                        above_surface_fraction=float(np.mean(p[:,2]>=top-.005)),
                        support_valid_fraction=support_valid_fraction(p,tcfg),
                        on_surface_fraction=float(np.mean(np.all((p[:,:2]>=support_lo)&(p[:,:2]<=support_hi),axis=1))),
                        on_table_fraction=float(np.mean((abs(p[:,0])<.7)&(abs(p[:,1])<.55))),
                        edge_stretch_p95=float(np.percentile(np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1)/np.maximum(rest_lengths,1e-9),95)))
        def run(seconds,label,act=None):
            nonlocal step_count
            start=time.perf_counter();n=round(seconds/cfg['dt'])
            for k in range(n):
                if act and k%5==0:act(k*cfg['dt'])
                scene.step();step_count+=1
                if k%25==0:sample(label)
            torch.cuda.synchronize();wall=time.perf_counter()-start
            row=sample(label);row.update(phase=label,wall_s=wall,rtf=n*cfg['dt']/wall)
            result['phases'].append(row);publish();print('PHASE',json.dumps(row),flush=True)
            return row
        run(5,'settle')
        if args.contact_probe:
            result['rigid_contact_probe']=[]
            for arm in control.arms:
                contacts=arm['robot'].get_contacts();pairs=[]
                for ga,gb,force in zip(array(contacts['geom_a']).reshape(-1),array(contacts['geom_b']).reshape(-1),array(contacts['force_a']).reshape(-1,3)):
                    pairs.append(dict(geom_a=int(ga),geom_b=int(gb),link_a=arm['robot']._solver.geoms[int(ga)].link.name,
                        link_b=arm['robot']._solver.geoms[int(gb)].link.name,force_norm_n=float(np.linalg.norm(force))))
                result['rigid_contact_probe'].append(dict(side=arm['side'],actual_qpos=array(arm['robot'].get_qpos()).reshape(-1).tolist(),
                    command_deflection=arm['command'].tolist(),tcp=control.ee(arm)[0].tolist(),contacts=pairs))
            result.update(status='complete',deployable=False,diagnostic_only=True);publish();return
        p0=array(cloth.get_particles_pos()).reshape(-1,3)
        idle=run(args.idle_seconds,'idle')
        p1=array(cloth.get_particles_pos()).reshape(-1,3)
        drift=float(np.linalg.norm((p1-p0).mean(0)))
        result['gates']['idle']=dict(passed=idle['support_valid_fraction']>.999 and idle['on_table_fraction']>.999 and drift<.02,
                                          com_drift_m=drift,limit_m=.02)
        # Known initial velocity is an isolated impulse experiment, never a grasp aid.
        vel=np.zeros_like(p1);vel[:,0]=.2;cloth.set_particles_vel(vel)
        run(2,'slide_impulse')
        ps=array(cloth.get_particles_pos()).reshape(-1,3)
        slide=float(np.linalg.norm((ps-p1).mean(0)[:2]))
        result['gates']['slide']=dict(passed=slide<.08,displacement_m=slide,limit_m=.08)
        cloth.set_particles_vel(np.zeros_like(ps))
        run(3,'slide_settle')
        # These are independent experiments: retain the failed sliding trace, then
        # explicitly reset the whole scene before the separate jaw test.
        control.reset();result['reset_between_independent_tests']=True
        reset_error=float(np.max(np.abs(array(cloth.get_particles_pos())-control.birth)))
        result['gates']['reset']=dict(passed=reset_error<1e-6,maximum_node_position_error_m=reset_error)
        run(5,'grasp_trial_reset_settle')
        a=control.arms[0];robot=a['robot'];ids=a['ids'];f=a['fingers']
        home_p,home_q=control.ee(a)
        result['home_tcp']=dict(pos=home_p.tolist(),quat_xyzw=home_q.tolist())
        def move(target,trigger,duration,label,quat=None,side=0):
            a=control.arms[side];robot=a['robot'];ids=a['ids'];f=a['fingers']
            startp,startq=control.ee(a);target=np.asarray(target);goalq=home_q if quat is None else quat
            def command(elapsed):
                frac=min(1.,elapsed/(duration*.7));desired=startp+(target-startp)*frac
                p,q=control.ee(a);err=np.r_[desired-p,rotvec(qmul(goalq,qinv(q)))]
                jac=array(robot.get_jacobian(a['hand'],local_point=tcfg['tcp_local_m'])).reshape(6,-1)[:,ids]
                dq=jac.T@np.linalg.solve(jac@jac.T+tcfg['dls_damping']**2*np.eye(6),err)
                current=array(robot.get_dofs_position()).reshape(-1)
                goal=current.copy();goal[ids]=np.clip(current[ids]+np.clip(dq,-.016,.016),a['lo'][ids],a['hi'][ids])
                fingergoal=a['lo'][f]+(1-trigger)*(a['hi'][f]-a['lo'][f])
                # Integrate the commanded finger position as in live teleoperation.
                # Basing each command on measured position would slow the servo and
                # leave a timed close/open trial only partially completed.
                goal[f]=a['command'][f]+np.clip(fingergoal-a['command'][f],-.0005,.0005)
                a['command']=goal.copy()
                robot.control_dofs_position(goal)
            row=run(duration,label,command);p,q=control.ee(a)
            row['tcp_m']=p.tolist();row['tcp_error_m']=float(np.linalg.norm(target-p));row['fingers']=array(robot.get_dofs_position()).reshape(-1)[f].tolist();publish()
            row['actual_arm_qpos']=array(robot.get_qpos()).reshape(-1)[ids].tolist()
            row['jacobian_singular_values']=np.linalg.svd(array(robot.get_jacobian(a['hand'],local_point=tcfg['tcp_local_m'])).reshape(6,-1)[:,ids],compute_uv=False).tolist()
            publish()
            quality['max_tcp_error_m']=max(quality['max_tcp_error_m'],row['tcp_error_m'])
            if label in ('descend','close','lift','release'):
                row['finger_collision_bounds']=[dict(link=g.link.name,bounds_m=array(g.get_AABB()).tolist())
                                                for g in robot.geoms if g.link.name in control.spec['finger_links']]
                publish()
            return p
        # Choose a raised crease near the left arm; actual Panda jaws only.
        p=array(cloth.get_particles_pos()).reshape(-1,3)
        near=np.where((p[:,0]<-.03)&(p[:,0]>-.28)&(p[:,1]>-.28)&(p[:,1]<-.03))[0]
        if not len(near):raise RuntimeError('No reachable left garment patch')
        ix=near[np.argmax(p[near,2])];patch=p[ix].copy()
        if args.grasp_xy is not None:
            nearest=np.argmin(np.linalg.norm(p[:,:2]-args.grasp_xy,axis=1))
            patch=np.array([*args.grasp_xy,float(p[nearest,2])])
        result['grasp_patch_m']=patch.tolist()
        hover=patch+np.array([0,0,.10]);touch=patch+np.array([0,0,.003])
        if args.grasp_xy is not None:hover[2]=top+.12
        if args.grasp_height_m is not None:touch[2]=top+args.grasp_height_m
        if args.record_video:
            cameras[1].set_pose(pos=(float(patch[0]),float(patch[1]-.34),top+.295),
                                lookat=(float(patch[0]),float(patch[1]),top+.055))
            result['video']=dict(fps=10,clock='simulation seconds, not wall-clock performance',
                                 start_sim_s=step_count*cfg['dt'],files=['wide.mp4','closeup.mp4'],
                                 phases_s={'approach':[0,5],'descend':[5,8],'close':[8,11],
                                           'lift':[11,15],'release':[15,18],'release_settle':[18,23]})
            for camera,name in zip(cameras,result['video']['files']):
                camera.start_recording(save_to_filename=str(out/name),fps=10)
            publish()
        move(hover,0.,5,'approach')
        move(touch,0.,3,'descend')
        move(touch,1.,3,'close')
        before=array(cloth.get_particles_pos()).reshape(-1,3)
        lift=touch+np.array([0,0,.12]);move(lift,1.,4,'lift')
        held=array(cloth.get_particles_pos()).reshape(-1,3)
        raised=int(np.sum(held[:,2]>top+.06))
        finger_deflection=array(robot.get_dofs_position()).reshape(-1)[f]
        result['gates']['grasp']=dict(passed=raised>=30,raised_nodes=raised,minimum_nodes=30,
                                           fingers_at_lift=finger_deflection.tolist())
        # Negative control: no node may remain bound when real jaws open.
        move(lift,0.,3,'release');release=run(5,'release_settle')
        open_error=float(np.max(np.abs(array(robot.get_dofs_position()).reshape(-1)[f]-a['hi'][f])))
        result['gates']['release']=dict(passed=release['bounds_m'][1][2]<top+.08,
                                              max_z_m=release['bounds_m'][1][2],finger_open_error_m=open_error)
        result['gates']['release']['passed'] &= (open_error<.002 and release['support_valid_fraction']>.999
                                                 and release['on_table_fraction']>.999)
        # A full fold is attempted only if physical lift succeeded; never fake success.
        result['fold_status']='not_attempted_grasp_failed'
        if result['gates']['grasp']['passed'] and args.bimanual_fold:
            control.reset();run(5,'bimanual_trial_reset_settle')
            initial=array(cloth.get_particles_pos()).reshape(-1,3)
            anchor=np.array([.08,-.20,top+.018]);anchor_hover=anchor.copy();anchor_hover[2]=top+.12
            move(anchor_hover,0.,8,'right_approach',side=1)
            move(anchor,0.,3,'right_descend',side=1);move(anchor,1.,3,'right_close',side=1)
            move(hover,0.,5,'left_approach');move(touch,0.,3,'left_descend');move(touch,1.,3,'left_close')
            move(lift,1.,4,'left_fold_lift');cross=lift.copy();cross[0]=.12
            move(cross,1.,5,'left_fold_cross');cross[2]=top+.025
            move(cross,1.,3,'left_fold_lower');move(cross,0.,3,'left_fold_release')
            cross[2]=top+.18;move(cross,0.,6,'left_retreat')
            move(anchor,0.,3,'right_release',side=1);anchor_hover[2]=top+.18
            move(anchor_hover,0.,6,'right_retreat',side=1);run(10,'bimanual_fold_settle')
            final=array(cloth.get_particles_pos()).reshape(-1,3)
            body=(initial[:,0]<-.02)&(initial[:,0]>-.18)&(initial[:,1]>-.28)&(initial[:,1]<-.03)
            if body.sum()<100:raise RuntimeError('Insufficient left torso nodes for fold evaluation')
            target=initial[body,:2].copy();target[:,0]*=-1
            matched=np.linalg.norm(final[body,:2]-target,axis=1)<.04
            transferred=final[body,0]>-.01
            result['fold_quality']=dict(scope='left torso half reflected across x=0, sleeves not scored',
                scored_nodes=int(body.sum()),fraction_within_4cm=float(matched.mean()),
                transferred_fraction=float(transferred.mean()),all_above_table=bool(np.all(final[:,2]>top-.005)))
            result['gates']['fold']=dict(passed=bool(matched.mean()>.7 and transferred.mean()>.7 and np.all(final[:,2]>top-.005)))
            result['fold_status']='body_half_fold_gate_passed_needs_video_review' if result['gates']['fold']['passed'] else 'body_half_fold_gate_failed'
        elif result['gates']['grasp']['passed'] and not args.grasp_only:
            # Reuse a physical pinch at the same patch after returning, then cross the garment midline.
            move(hover,0.,4,'fold_approach');move(touch,0.,3,'fold_descend');move(touch,1.,3,'fold_close')
            move(lift,1.,4,'fold_lift');opposite=lift.copy();opposite[0]=max(.08,-patch[0])
            move(opposite,1.,4,'fold_cross');opposite[2]=top+.025
            move(opposite,1.,3,'fold_lower');move(opposite,0.,3,'fold_open');opposite[2]+=.15
            move(opposite,0.,3,'fold_retreat');run(10,'fold_settle')
            result['fold_status']='attempted_requires_visual_quality_review'
        if args.record_video:
            for camera in cameras:camera.stop_recording()
        result['status']='complete';publish()
        result['gates']['strain']=dict(passed=max(row['edge_stretch_p95'] for row in result['phases'])<1.2,
                                            maximum_phase_p95=max(row['edge_stretch_p95'] for row in result['phases']),limit=1.2)
        result['quality']=quality
        result['gates']['reach']=dict(passed=quality['max_tcp_error_m']<.025,
                                     maximum_tcp_error_m=quality['max_tcp_error_m'],limit_m=.025)
        if args.grasp_only:result['fold_status']='not_tested_grasp_only_no_fold_claim'
        if args.bimanual_fold:
            result['gates']['local_strain']=dict(passed=quality['max_edge_ratio']<1.25 and quality['max_p99_edge_ratio']<1.1,**quality)
            result['gates']['reach']=dict(passed=quality['max_tcp_error_m']<.025)
            if 'fold' not in result['gates']:result['gates']['fold']=dict(passed=False,reason='No stable initial grasp')
        result['deployable']=all(g['passed'] for g in result['gates'].values());publish()
        np.savez_compressed(out/'trajectory.npz',positions=np.asarray(frames),sim_time_s=np.asarray(times),phase=np.asarray(labels),faces=faces)
        print('RESULT',json.dumps(result),flush=True)
    except BaseException as e:
        if 'frames' in locals() and frames:
            np.savez_compressed(out/'trajectory.npz',positions=np.asarray(frames),sim_time_s=np.asarray(times),phase=np.asarray(labels),faces=faces)
        result.update(status='failed',error=str(e),traceback=traceback.format_exc());publish();raise


if __name__=='__main__':main()
