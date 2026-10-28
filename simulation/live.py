"""Genesis PBD live state and explicitly selected simulation teleoperation."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from configuration import load_config
import signal
import struct
import threading
import time
import traceback
import uuid
ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=1800)
    parser.add_argument('--teleop',action='store_true');parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--config-dir',type=Path,default=ROOT.parent/'configs/franka')
    parser.add_argument('--port',type=int,choices=[9740,9742],default=9740)
    args=parser.parse_args()
    root=args.config_dir.resolve()
    out=root/'outputs'/('teleop-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
    out.mkdir(parents=True,exist_ok=False)
    cache=ROOT.parent/'outputs/cache'
    for key,name in {'GS_CACHE_FILE_PATH':'genesis','XDG_CACHE_HOME':'xdg','TMPDIR':'tmp','NUMBA_CACHE_DIR':'numba','MPLCONFIGDIR':'matplotlib'}.items():
        p=cache/name;p.mkdir(parents=True,exist_ok=True);os.environ[key]=str(p)
    os.environ['PYOPENGL_PLATFORM']='egl'
    cfg,tcfg=load_config(root)
    status=dict(status='initializing',read_only=not args.teleop,output=str(out),config=cfg,teleop_config=tcfg,
        source_hashes={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['live.py','teleop_control.py','robot_profiles.py']},
        config_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['teleop_config.json','config.json']})
    def publish():
        p=out/'status.tmp';p.write_text(json.dumps(status,indent=2));p.replace(out/'status.json')
    publish();stopped=threading.Event()
    for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,lambda *_:stopped.set())
    try:
        import numpy as np
        import torch
        import genesis as gs
        from teleop_control import build,TeleopControl,array,qmatrix,rotvec,qmul,qinv,work_surface_height,work_surface_bounds,support_valid_fraction
        from websockets.sync.server import serve
        from websockets.exceptions import ConnectionClosed
        gs.init(backend=gs.gpu,seed=1,logging_level='warning')
        platforms=[]
        scene,table,robots,cloth,dz=build(cfg,tcfg,platform_entities=platforms)
        top=work_surface_height(tcfg);support_lo,support_hi=work_surface_bounds(tcfg)
        decimation=round(1/(tcfg['control_hz_sim']*cfg['dt']))
        assert abs(decimation*cfg['dt']*tcfg['control_hz_sim']-1)<1e-8
        control=TeleopControl(robots,cloth,tcfg,decimation*cfg['dt'])
        # Compile first-use Jacobian kernels while disarmed, never during a live grip.
        for a in control.arms:
            a['robot'].get_jacobian(a['hand'],local_point=tcfg['tcp_local_m'])
        torch.cuda.synchronize()
        def step(n,inject=None):
            for i in range(n):
                if i%decimation==0:
                    if inject:inject(i*cfg['dt'])
                    control.advance()
                scene.step()
        step(100)
        status.update(particle_count=cloth.n_particles,spawn_translation_z_m=dz,
                      initial_min_z_m=float(control.birth[...,2].min()),work_surface_top_m=top,
                      platform_collision_bounds_m=[array(entity.geoms[0].get_AABB()).tolist() for entity in platforms])
        if args.self_test:
            report=dict(status='running',spawn_min_z_m=status['initial_min_z_m'],phases=[],
                robot_type=tcfg.get('robot_type','franka'),tools=dict(link=control.spec['tool_link'],tcp_local_m=tcfg['tcp_local_m']),
                joint_bounds=[dict(side=a['side'],lo=a['lo'].tolist(),hi=a['hi'].tolist()) for a in control.arms])
            def evidence():
                (out/'diagnostics.json').write_text(json.dumps(report,indent=2))
            evidence();start=time.perf_counter()
            settle=[]
            for second in range(tcfg['static_validation_sim_s']):
                step(round(1/cfg['dt']));p=array(cloth.get_particles_pos()).reshape(-1,3)
                row=dict(sim_s=second+1,bounds_m=[p.min(0).tolist(),p.max(0).tolist()],
                    fraction_above_table=float(np.mean(p[:,2]>=tcfg['table_top_m']-.005)),
                    fraction_above_surface=float(np.mean(p[:,2]>=top-.005)),
                    support_valid_fraction=support_valid_fraction(p,tcfg),
                    fraction_on_surface=float(np.mean(np.all((p[:,:2]>=support_lo)&(p[:,:2]<=support_hi),axis=1))),
                    fraction_on_table=float(np.mean((np.abs(p[:,0])<.7)&(np.abs(p[:,1])<.55))),
                    arm_joints=[array(r.get_dofs_position()).tolist() for r in robots])
                settle.append(row)
                if not np.isfinite(p).all() or row['support_valid_fraction']<.999 or row['fraction_on_table']<.999:
                    report.update(status='failed',failure='Cloth left work surface during idle',settle=settle);evidence()
                    raise RuntimeError(report['failure'])
                if second%10==0:print('STATIC_CHECK',second+1,row['bounds_m'],flush=True)
            report['settle']=settle;report['idle_rtf']=tcfg['static_validation_sim_s']/(time.perf_counter()-start);evidence()
            counter=[0]
            def packet(side=None,delta=(0,0,0),rotation=0.,trigger=0.,rotation_mode='free'):
                counter[0]+=1;hands={}
                for name in ['left','right']:
                    active=name==side
                    hands[name]=dict(valid=True,grip=active,trigger=trigger if name==side else 0.,
                        pose=list(delta if active else (0,0,0))+[0,0,float(np.sin(rotation/2)) if active else 0.,float(np.cos(rotation/2)) if active else 1.])
                control.submit('self-test',dict(type='xr',version=1,sequence=counter[0],hands=hands,
                    rotation_mode=rotation_mode,input_frame='table'))
            def qpositions():return [array(r.get_dofs_position()) for r in robots]
            for arm_index,side in enumerate(['left','right']):
                step(10,lambda _:packet())
                a=control.arms[arm_index];before=[control.ee(x)[0] for x in control.arms]
                # First grip packet latches a reference, followed by a 12mm target delta.
                step(round(2/cfg['dt']),lambda t:packet(side,(.024*min(t,1.),0,0)))
                after=[control.ee(x)[0] for x in control.arms];move=after[arm_index]-before[arm_index]
                other=float(np.linalg.norm(after[1-arm_index]-before[1-arm_index]))
                row=dict(phase=side+'_translation',before_m=[x.tolist() for x in before],after_m=[x.tolist() for x in after],actual_delta_m=move.tolist(),inactive_drift_m=other,control=control.snapshot())
                report['phases'].append(row);evidence()
                if not .004<move[0]<.025 or other>.006:raise RuntimeError('Direction or inactive-arm check failed')
                for axis,label in [(1,'forward'),(2,'up')]:
                    step(10,lambda _:packet())
                    before=[control.ee(x)[0] for x in control.arms]
                    def axis_packet(t):
                        delta=[0.,0.,0.];delta[axis]=.024*min(t,1.);packet(side,delta)
                    step(round(2/cfg['dt']),axis_packet)
                    after=[control.ee(x)[0] for x in control.arms];delta=after[arm_index]-before[arm_index]
                    drift=float(np.linalg.norm(after[1-arm_index]-before[1-arm_index]))
                    report['phases'].append(dict(phase=side+'_'+label,actual_delta_m=delta.tolist(),inactive_drift_m=drift));evidence()
                    if not .004<delta[axis]<.025 or drift>.006:raise RuntimeError('Axis direction or inactive-arm check failed')
                step(10,lambda _:packet())
                initial_q=control.ee(a)[1]
                step(round(1.5/cfg['dt']),lambda t:packet(side,(.024,0,0),.05*min(t,1.)))
                rotation=float(np.linalg.norm(rotvec(qmul(control.ee(a)[1],qinv(initial_q)))))
                report['phases'].append(dict(phase=side+'_rotation',actual_rotation_rad=rotation));evidence()
                if not .012<rotation<.15:raise RuntimeError('Wrist rotation check failed')
                step(10,lambda _:packet(rotation_mode='locked'))
                # Establish a fixed-controller baseline first; retain the absolute
                # tracking error separately from additional controller-induced rotation.
                step(round(2/cfg['dt']),lambda _:packet(side,rotation_mode='locked'))
                locked_q=control.ee(a)[1];locked_target=a['target_q'].copy()
                step(round(2/cfg['dt']),lambda t:packet(side,rotation=.1*min(t,1.),rotation_mode='locked'))
                locked_error=float(np.linalg.norm(rotvec(qmul(control.ee(a)[1],qinv(locked_q)))))
                target_change=float(np.linalg.norm(rotvec(qmul(a['target_q'],qinv(locked_target)))))
                absolute_error=float(np.linalg.norm(rotvec(qmul(control.ee(a)[1],qinv(locked_target)))))
                report['phases'].append(dict(phase=side+'_orientation_lock',actual_rotation_rad=locked_error,
                    target_rotation_change_rad=target_change,absolute_tracking_error_rad=absolute_error,
                    protocol='fixed-controller baseline, then rotate controller 0.1 rad; existing absolute servo error reported separately'));evidence()
                if target_change>1e-6:raise RuntimeError('Locked target changed with controller orientation')
                if locked_error>.01:raise RuntimeError('Locked orientation drift exceeded 0.01 rad')
                step(10,lambda _:packet())
                # Trigger test with released grip, matching the operator contract.
                def fingers(t,trigger):
                    packet();d=control.latest['hands'][side];d['trigger']=trigger
                step(round(2/cfg['dt']),lambda t:fingers(t,0.))
                opened=array(a['robot'].get_dofs_position())[a['fingers']]
                step(round(2/cfg['dt']),lambda t:fingers(t,1.))
                closed=array(a['robot'].get_dofs_position())[a['fingers']]
                step(round(2/cfg['dt']),lambda t:fingers(t,0.))
                reopened=array(a['robot'].get_dofs_position())[a['fingers']]
                row=dict(phase=side+'_gripper',opened=opened.tolist(),closed=closed.tolist(),reopened=reopened.tolist())
                report['phases'].append(row);evidence()
                if np.min(opened-closed)<.015 or np.max(np.abs(reopened-opened))>.004:raise RuntimeError('Actual finger open/close check failed')
            packet('left');control.advance();control.release('self-test')
            before=qpositions();step(round(.5/cfg['dt']));after=qpositions()
            report['disconnect_joint_drift_rad']=[float(np.max(np.abs(x-y))) for x,y in zip(after,before)]
            if max(report['disconnect_joint_drift_rad'])>.02:raise RuntimeError('Disconnect hold failed')
            control.reset();p=array(cloth.get_particles_pos());assert np.max(np.abs(p-control.birth))<1e-6
            report.update(status='passed',reset_passed=True,final_control=control.snapshot());evidence()
            status.update(status='self_test_passed',diagnostics=str(out/'diagnostics.json'));publish();print('SELF_TEST_PASS',out,flush=True);return
        # Shape geometry is static; every robot link receives a live pose index.
        def enc(a,dtype):return base64.b64encode(np.asarray(a,dtype=dtype).tobytes()).decode()
        def mesh(name,p,f,color,pose_index=-1):
            p=np.asarray(p,dtype='<f4').reshape(-1,3);f=np.asarray(f,dtype='<u4').reshape(-1,3)
            assert np.isfinite(p).all() and len(f) and f.max()<len(p)
            return dict(name=name,positions=enc(p,'<f4'),indices=enc(f,'<u4'),color=color,
                        vertex_count=len(p),triangle_count=len(f),pose_index=pose_index)
        meshes=[mesh('floor',[[-3,-3,0],[3,-3,0],[3,3,0],[-3,3,0]],[[0,1,2],[0,2,3]],[.18,.23,.29]),
                mesh('table',array(table.get_vverts()),np.concatenate([g.init_vfaces for g in table.vgeoms]),[.44,.27,.15])]
        for name,entity in zip(['platform_top','platform_pillar'],platforms):
            meshes.append(mesh(name,array(entity.get_vverts()),np.concatenate([g.init_vfaces for g in entity.vgeoms]),[.62,.46,.29]))
        pose_count=0
        def robot_poses():
            return np.concatenate([np.concatenate([array(r.get_links_pos(relative=False)),array(r.get_links_quat(relative=False))[:,[1,2,3,0]]],axis=1) for r in robots]).astype('<f4')
        initial_poses=robot_poses()
        for ri,r in enumerate(robots):
            v=array(r.get_vverts()).reshape(-1,3);offset=0;groups={};link_ids={id(link):i for i,link in enumerate(r.links)}
            for g in r.vgeoms:
                li=link_ids[id(g.link)];pose=initial_poses[pose_count+li];local=(v[offset:offset+g.n_vverts]-pose[:3])@qmatrix(pose[3:])
                group=groups.setdefault(li,{'v':[],'f':[],'n':0});group['v'].append(local)
                group['f'].append(np.asarray(g.init_vfaces)+group['n']);group['n']+=g.n_vverts;offset+=g.n_vverts
            for li,group in groups.items():meshes.append(mesh('robot'+str(ri)+'_'+str(li),np.concatenate(group['v']),np.concatenate(group['f']),[.83,.85,.87],pose_count+li))
            pose_count+=len(r.links)
        p=array(cloth.get_particles_pos()).reshape(-1,3);faces=np.asarray(cloth._mesh.faces)
        assert len(cloth._mesh.verts)==len(p)
        meshes.append(mesh('cloth',p,faces,[.85,.18,.35]))
        tools=[];offset=0
        for arm,robot in zip(control.arms,robots):
            tools.append(dict(side=arm['side'],pose_index=offset+list(robot.links).index(arm['hand']),tcp_local_m=tcfg['tcp_local_m']))
            offset+=len(robot.links)
        geometry=dict(type='geometry',version=2,coordinates='Z-up metres',meshes=meshes,
            particle_count=len(p),pose_count=pose_count,initial_poses=initial_poses.tolist(),state_hz_target=20,
            physics_dt=cfg['dt'],simulation='Genesis PBD',teleop_available=args.teleop,
            robot_type=tcfg.get('robot_type','franka'),robot_label=control.spec['label'],tools=tools,
            translation_scale=tcfg['translation_scale'])
        geometry['work_surface_top_m']=top;geometry['platform']=tcfg.get('platform')
        (out/'geometry.json').write_text(json.dumps(geometry));condition=threading.Condition();latest=[0,None]
        def handler(ws):
            owner=uuid.uuid4().hex;can_control=args.teleop and ws.request.path=='/control'
            ws.send(json.dumps(dict(geometry,read_only=not can_control)))
            done=threading.Event()
            def receive():
                try:
                    while not done.is_set():
                        data=ws.recv()
                        if not can_control:ws.close(1008,'Read-only state endpoint');return
                        try:
                            if not isinstance(data,str) or len(data)>4096:raise ValueError('Invalid control size')
                            control.submit(owner,json.loads(data))
                        except (ValueError,TypeError,KeyError) as e:
                            ws.close(1008,str(e));return
                except ConnectionClosed:pass
                finally:done.set();control.release(owner)
            receiver=threading.Thread(target=receive,daemon=True);receiver.start();previous=-1
            try:
                while not stopped.is_set() and not done.is_set():
                    with condition:
                        condition.wait_for(lambda:latest[0]!=previous or stopped.is_set(),timeout=.1);seq,packet=latest
                    if packet is not None and seq!=previous:
                        ws.send(packet);ws.send(json.dumps(dict(type='control',**control.snapshot())));previous=seq
            except ConnectionClosed:pass
            finally:done.set();control.release(owner);ws.close();receiver.join(timeout=2)
        server=serve(handler,'127.0.0.1',args.port,max_size=4096,max_queue=1,compression=None,close_timeout=2)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        status.update(status='ready',pose_count=pose_count,geometry_bytes=len(json.dumps(geometry)));publish();print('GENESIS_TELEOP_READY',out,flush=True)
        start=time.perf_counter();window=start;ws_steps=0;ws_packets=0;steps=0;seq=0;rtf=0.;hz=0.;next_packet=start;next_stats=start+2
        try:
            while not stopped.is_set() and time.perf_counter()-start<args.seconds:
                ahead=start+steps*cfg['dt']-time.perf_counter()
                if ahead>0:stopped.wait(ahead)
                if stopped.is_set():break
                if steps%decimation==0:control.advance()
                scene.step();steps+=1;ws_steps+=1;now=time.perf_counter()
                if now>=next_packet:
                    p=array(cloth.get_particles_pos()).astype('<f4').reshape(-1,3);poses=robot_poses()
                    if not np.isfinite(p).all() or not np.isfinite(poses).all():raise RuntimeError('Nonfinite scene state')
                    seq+=1;packet=struct.pack('<4sIddddII',b'GSV2',seq,steps*cfg['dt'],time.time(),rtf,hz,len(p),len(poses))+p.tobytes()+poses.tobytes()
                    with condition:latest[:]=[seq,packet];condition.notify_all()
                    ws_packets+=1;next_packet=now+.05
                if now>=next_stats:
                    duration=now-window;rtf=ws_steps*cfg['dt']/duration;hz=ws_packets/duration
                    status.update(steps=steps,sim_s=steps*cfg['dt'],wall_s=now-start,physics_rtf=rtf,state_hz=hz,control=control.snapshot(),
                        cloth_bounds_m=[p.min(0).tolist(),p.max(0).tolist()],cloth_above_table=float(np.mean(p[:,2]>=tcfg['table_top_m']-.005)),
                        cloth_above_surface=float(np.mean(p[:,2]>=top-.005)),cloth_support_valid=support_valid_fraction(p,tcfg))
                    publish();print('GENESIS_TELEOP_STATS',json.dumps(status),flush=True);next_stats=now+2;window=now;ws_steps=0;ws_packets=0
        finally:
            stopped.set()
            with condition:condition.notify_all()
            server.shutdown();thread.join(timeout=5)
        status.update(status='stopped');publish()
    except BaseException as e:
        diagnostic=out/'diagnostics.json'
        if diagnostic.exists():
            failed=json.loads(diagnostic.read_text());failed.update(status='failed',failure=str(e));diagnostic.write_text(json.dumps(failed,indent=2))
        status.update(status='failed',error=str(e),traceback=traceback.format_exc());publish();raise


if __name__=='__main__':main()
