'use strict';
// Explicit teleop mode uses only simulation XR/hold/reset messages; default /state stays read-only.
const canvas=document.getElementById('scene'), statusEl=document.getElementById('status');
const enter=document.getElementById('enter'), recenter=document.getElementById('recenter');
const gl=canvas.getContext('webgl2',{antialias:true,alpha:false,xrCompatible:true});
const meshes=[];
const teleopRequested=new URLSearchParams(location.search).get('teleop')==='1';
let poses=[],controlStatus=null,inputSequence=0,nextInput=0,canControl=false;
if(teleopRequested){document.getElementById('heading').textContent='TeleMovo · 双臂布料 · PICO 遥操';document.getElementById('instructions').textContent='先松开双 Grip 校准，再按住对应 Grip 移动；Trigger 开合夹爪。松开 Grip 保位，断连停止跟随。本入口不录制。';document.getElementById('hint').textContent='左手控制左臂，右手控制右臂；先小幅移动，确认方向再靠近衣物。';document.getElementById('mode').href='/';document.getElementById('mode').textContent='切换到只读';enter.textContent='进入 VR 遥操';document.getElementById('reset').hidden=false;}
let cloth=null,ws=null,session=null,reference=null,anchorInverse=null,xrSupported=false;
let received=0,lastPacket=0,sequence=0,rtf=0,stateHz=0,simTime=0,frameCounter=0,displayFps=0;
let fpsEpoch=performance.now(),lastUi=0,lastHud=0,lastError='',connection='connecting',controllerCount=0;
let showHud=false;
const frameSelect=document.getElementById('inputFrame'),rotationSelect=document.getElementById('rotationMode');
const guidanceToggle=document.getElementById('guidance'),lessonSelect=document.getElementById('lesson');
let tableInputInverse=null,toolFrames=[],robotLabel='',translationScale=.5,gripsDown=false;
let guideProgram,guideVAO,guideBuffer,guideCount=0,coachProgram,coachTexture,coachVAO,lastCoach=0;
window.__genesisViewStats={readOnly:true,ready:false};
function fail(e){lastError=String(e?.message||e);statusEl.className='error';statusEl.textContent=lastError;console.error(e);}
window.addEventListener('error',e=>fail(e.message));
window.addEventListener('unhandledrejection',e=>fail(e.reason));
function mul(a,b){const c=new Float32Array(16);for(let j=0;j<4;j++)for(let i=0;i<4;i++)for(let k=0;k<4;k++)c[j*4+i]+=a[k*4+i]*b[j*4+k];return c;}
function inverseRigid(m){const a=new Float32Array([m[0],m[4],m[8],0,m[1],m[5],m[9],0,m[2],m[6],m[10],0,0,0,0,1]);for(let i=0;i<3;i++)a[12+i]=-(a[i]*m[12]+a[4+i]*m[13]+a[8+i]*m[14]);return a;}
function norm(v){const n=Math.hypot(...v);return v.map(x=>x/n);}
function cross(a,b){return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}
function cameraWorld(eye,target){const z=norm(eye.map((x,i)=>x-target[i])),x=norm(cross([0,1,0],z)),y=cross(z,x);return new Float32Array([...x,0,...y,0,...z,0,...eye,1]);}
function perspective(aspect){const f=1/Math.tan(Math.PI/6),n=.02,z=30;return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(z+n)/(n-z),-1,0,0,2*z*n/(n-z),0]);}
const simToXR=new Float32Array([1,0,0,0,0,0,-1,0,0,1,0,0,0,0,0,1]);
const desired=cameraWorld([0,1.75,.95],[0,.900,.05]),desiredInverse=inverseRigid(desired);

function poseMatrix(p){const [x,y,z,a,b,c,d]=p;return new Float32Array([1-2*(b*b+c*c),2*(a*b+c*d),2*(a*c-b*d),0,2*(a*b-c*d),1-2*(a*a+c*c),2*(b*c+a*d),0,2*(a*c+b*d),2*(b*c-a*d),1-2*(a*a+b*b),0,x,y,z,1]);}
function matrixQuat(m){const tr=m[0]+m[5]+m[10];let x,y,z,w,s;if(tr>0){s=Math.sqrt(tr+1)*2;w=s/4;x=(m[6]-m[9])/s;y=(m[8]-m[2])/s;z=(m[1]-m[4])/s;}else if(m[0]>m[5]&&m[0]>m[10]){s=Math.sqrt(1+m[0]-m[5]-m[10])*2;w=(m[6]-m[9])/s;x=s/4;y=(m[4]+m[1])/s;z=(m[8]+m[2])/s;}else if(m[5]>m[10]){s=Math.sqrt(1+m[5]-m[0]-m[10])*2;w=(m[8]-m[2])/s;x=(m[4]+m[1])/s;y=s/4;z=(m[9]+m[6])/s;}else{s=Math.sqrt(1+m[10]-m[0]-m[5])*2;w=(m[1]-m[4])/s;x=(m[8]+m[2])/s;y=(m[9]+m[6])/s;z=s/4;}return[x,y,z,w];}
function yawFrame(m){
 const length=Math.hypot(m[8],m[10]);if(length<1e-4)throw Error('请自然看向前方后重新校准');
 const x=m[8]/length,z=m[10]/length;
 return new Float32Array([z,0,-x,0,0,1,0,0,x,0,z,0,m[12],m[13],m[14],1]);
}
function mapInputToSim(viewerPose,mode){return mul(inverseRigid(simToXR),inverseRigid(mode==='table'?yawFrame(viewerPose):mul(viewerPose,desiredInverse)));}
function point(m,p){return [m[0]*p[0]+m[4]*p[1]+m[8]*p[2]+m[12],m[1]*p[0]+m[5]*p[1]+m[9]*p[2]+m[13],m[2]*p[0]+m[6]*p[1]+m[10]*p[2]+m[14]];}
function command(data){if(canControl&&ws&&ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify(data));}
function sendInput(frame,now){
 if(!canControl||!anchorInverse||now<nextInput)return;nextInput+=1000/60;if(nextInput<now)nextInput=now+1000/60;
 const hands={left:{pose:[0,0,0,0,0,0,1],valid:false,grip:false,trigger:0},right:{pose:[0,0,0,0,0,0,1],valid:false,grip:false,trigger:0}};
 const toSim=frameSelect.value==='table'?tableInputInverse:mul(inverseRigid(simToXR),inverseRigid(anchorInverse));
 for(const input of session.inputSources){if(!hands[input.handedness]||!input.gripSpace)continue;const p=frame.getPose(input.gripSpace,reference),g=input.gamepad;if(!p||p.emulatedPosition||!g||g.mapping!=='xr-standard')continue;
 const m=mul(toSim,p.transform.matrix);hands[input.handedness]={pose:[m[12],m[13],m[14],...matrixQuat(m)],valid:true,grip:(g.buttons[1]?.value||0)>=.5,trigger:Math.max(0,Math.min(1,g.buttons[0]?.value||0))};}
 gripsDown=Object.values(hands).some(h=>h.grip);
 frameSelect.disabled=gripsDown;rotationSelect.disabled=gripsDown;
 command({type:'xr',version:1,sequence:++inputSequence,hands,rotation_mode:rotationSelect.value,input_frame:frameSelect.value});
}

function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
function program(v,f){const p=gl.createProgram();gl.attachShader(p,shader(gl.VERTEX_SHADER,v));gl.attachShader(p,shader(gl.FRAGMENT_SHADER,f));gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));return p;}
function decode(text,Type){const s=atob(text),b=new Uint8Array(s.length);for(let i=0;i<s.length;i++)b[i]=s.charCodeAt(i);return new Type(b.buffer);}
let sceneProgram,hudProgram,controller,hudTexture,hudVAO;
function makeMesh(name,p,f,color,dynamic=false){
  if(!p.length||p.length%3||f.length%3||!Array.from(p).every(Number.isFinite))throw Error('Invalid mesh '+name);
  for(const i of f)if(i>=p.length/3)throw Error('Invalid triangle index '+name);
  const vao=gl.createVertexArray();gl.bindVertexArray(vao);
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,p,dynamic?gl.DYNAMIC_DRAW:gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,0,0);
  const ibo=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ibo);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,f,gl.STATIC_DRAW);
  return{name,vao,buffer,ibo,count:f.length,vertexCount:p.length/3,color};
}
function setup(){
  if(!gl)throw Error('浏览器不支持 WebGL2，无法绘制此场景');
  sceneProgram=program(`#version 300 es
    layout(location=0) in vec3 pos; uniform mat4 mvp; uniform mat4 model; out vec3 world;
    void main(){world=(model*vec4(pos,1.)).xyz;gl_Position=mvp*vec4(pos,1.);}`,`#version 300 es
    precision highp float; in vec3 world; uniform vec3 color; uniform bool checker; out vec4 frag;
    void main(){vec3 n=normalize(cross(dFdx(world),dFdy(world)));float light=.42+.58*abs(dot(n,normalize(vec3(.3,-.4,1.))));
    float c=checker?(mod(floor(world.x*4.)+floor(world.y*4.),2.)<1.?1.:.75):1.;frag=vec4(color*light*c,1.);}`);
  hudProgram=program(`#version 300 es
    layout(location=0) in vec2 xy;uniform mat4 projection;out vec2 uv;
    void main(){uv=xy*.5+.5;gl_Position=projection*vec4(xy.x*.48,.29+xy.y*.065,-.9,1.);}`,`#version 300 es
    precision mediump float;in vec2 uv;uniform sampler2D image;out vec4 frag;
    void main(){frag=texture(image,vec2(uv.x,1.-uv.y));}`);
  hudVAO=gl.createVertexArray();gl.bindVertexArray(hudVAO);const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,2,gl.FLOAT,false,0,0);
  hudTexture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,hudTexture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  const p=new Float32Array([-.018,-.018,-.02,.018,-.018,-.02,.018,.018,-.02,-.018,.018,-.02,-.018,-.018,-.12,.018,-.018,-.12,.018,.018,-.12,-.018,.018,-.12]);
  controller=makeMesh('controller',p,new Uint32Array([0,1,2,0,2,3,4,6,5,4,7,6,0,4,5,0,5,1,3,2,6,3,6,7,1,5,6,1,6,2,0,3,7,0,7,4]),[.2,.65,1]);
  gl.enable(gl.DEPTH_TEST);gl.disable(gl.CULL_FACE);gl.clearColor(.075,.11,.15,1);
}
function connect(){
  ws=new WebSocket(`wss://${location.host}/${teleopRequested?'control':'state'}`);ws.binaryType='arraybuffer';
  ws.onopen=()=>{connection='connected';};
  ws.onerror=()=>fail('状态连接失败，请检查 Genesis 服务和网关');
  ws.onclose=e=>{connection='closed';enter.disabled=true;fail(`状态连接已断开（${e.code}）。画面停止更新，请刷新页面重连。`);};
  ws.onmessage=e=>{try{
    if(typeof e.data==='string'){
      const data=JSON.parse(e.data);if(data.type==='control'){controlStatus=data;return;}if(data.type!=='geometry'||data.version!==2)throw Error('Unsupported scene protocol; refresh page');canControl=teleopRequested&&data.read_only===false;if(teleopRequested&&!canControl)throw Error('服务器未启用遥操模式');poses=data.initial_poses.map(poseMatrix);document.getElementById('reset').disabled=!canControl;
      if(!Array.isArray(data.tools)||data.tools.length!==2)throw Error('服务端尚未升级操作引导，请等待服务重启');
      toolFrames=data.tools;robotLabel=data.robot_label;translationScale=data.translation_scale;
      document.getElementById('heading').textContent=`TeleMovo ${robotLabel} · ${canControl?'PICO 遥操':'只读查看'}`;
      if(data.robot_type==='x5')document.getElementById('hint').textContent='X5 操作引导验证版：先练方向、旋转和开合；固定抓点夹布尚未通过。本入口不录制。';
      if(meshes.length)throw Error('Duplicate scene geometry');
      for(const m of data.meshes){const mesh=makeMesh(m.name,decode(m.positions,Float32Array),decode(m.indices,Uint32Array),m.color,m.name==='cloth');mesh.poseIndex=m.pose_index;meshes.push(mesh);if(m.name==='cloth')cloth=mesh;}
      if(!cloth||cloth.vertexCount!==data.particle_count)throw Error('Cloth topology mismatch');
    }else{
      if(!cloth)throw Error('State received before scene geometry');
      const d=new DataView(e.data);if(d.byteLength<48||d.getUint32(0,true)!==0x32565347)throw Error('Invalid state header');
      const n=d.getUint32(40,true),np=d.getUint32(44,true);if(n!==cloth.vertexCount||np!==poses.length||d.byteLength!==48+n*12+np*28)throw Error('State size mismatch');
      const all=new Float32Array(e.data,48),p=all.subarray(0,n*3);for(let i=0;i<np;i++)poses[i]=poseMatrix(all.subarray(n*3+i*7,n*3+i*7+7));for(const v of p)if(!Number.isFinite(v))throw Error('Nonfinite cloth state');
      gl.bindBuffer(gl.ARRAY_BUFFER,cloth.buffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,p);
      sequence=d.getUint32(4,true);simTime=d.getFloat64(8,true);rtf=d.getFloat64(24,true);stateHz=d.getFloat64(32,true);
      received++;lastPacket=performance.now();enter.disabled=!xrSupported||!!session;
    }
  }catch(error){fail(error);ws.close(1002,'Invalid scene data');}};
}
function draw(m,mvp,color=m.color){const model=m.poseIndex>=0?poses[m.poseIndex]:new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);gl.useProgram(sceneProgram);gl.bindVertexArray(m.vao);gl.uniformMatrix4fv(gl.getUniformLocation(sceneProgram,'model'),false,model);gl.uniformMatrix4fv(gl.getUniformLocation(sceneProgram,'mvp'),false,mul(mvp,model));gl.uniform3fv(gl.getUniformLocation(sceneProgram,'color'),color);gl.uniform1i(gl.getUniformLocation(sceneProgram,'checker'),m.name==='floor');gl.drawElements(gl.TRIANGLES,m.count,gl.UNSIGNED_INT,0);}
const hudCanvas=document.createElement('canvas');hudCanvas.width=1024;hudCanvas.height=128;const hud2d=hudCanvas.getContext('2d');
function updateUI(now){
  frameCounter++;if(now-fpsEpoch>=1000){displayFps=frameCounter*1000/(now-fpsEpoch);frameCounter=0;fpsEpoch=now;}
  if(now-lastUi<500)return;lastUi=now;
  const age=received?now-lastPacket:Infinity,stale=age>1000;
  window.__genesisViewStats={readOnly:!canControl,teleop:canControl,controlStatus,ready:received>0,meshes:meshes.length,clothVertices:cloth?.vertexCount||0,
    triangles:meshes.reduce((s,m)=>s+m.count/3,0),received,sequence,physicsRtf:rtf,stateHz,displayFps,simTime,
    ageMs:age,connection,xrActive:!!session,controllerCount,showHud,lastError,
    robotLabel,inputFrame:frameSelect.value,rotationMode:rotationSelect.value,guidance:guidanceToggle.checked,guideVertices:guideCount,tools:toolFrames.length};
  if(!lastError){statusEl.className=stale&&received?'error':'';statusEl.textContent=received?
    `${session?'VR绘制':'桌面绘制'} ${displayFps.toFixed(0)} FPS · 衣物状态 ${stateHz.toFixed(1)} Hz · 物理 ${rtf.toFixed(2)}×实时 · 距收包 ${age.toFixed(0)} ms\n${stale?'数据已停更，当前显示最后一帧。':'实时状态已收到。'} ${controlStatus?Object.entries(controlStatus.arms).map(([side,a])=>`${side}: ${a.error||(a.enabled?'跟随':a.require_release?'请松开Grip':'保持')}`).join(' · '):''} ${xrSupported?'可点击进入VR。':'请使用PICO浏览器进入VR；当前为桌面预览。'}`:'正在等待场景和第一帧实时状态…';}
}
function drawHUD(projection,now){
  if(now-lastHud>500){lastHud=now;const age=lastPacket?now-lastPacket:Infinity,stale=age>1000||connection!=='connected';
    hud2d.fillStyle=stale?'#6c2424':'#112b36';hud2d.fillRect(0,0,1024,128);hud2d.fillStyle='#efffff';hud2d.font='30px sans-serif';
    hud2d.fillText(`${canControl?'遥操':'只读查看'} · VR ${displayFps.toFixed(0)} FPS · 衣物 ${stateHz.toFixed(1)} Hz · 物理 ${rtf.toFixed(2)}×`,22,48);
    const fault=controlStatus?Object.entries(controlStatus.arms).filter(([side,a])=>a.error).map(([side,a])=>`${side}: ${a.error}`).join(' · '):'';
    hud2d.font='25px sans-serif';hud2d.fillText(fault|| (stale?'状态已断流，当前为最后一帧；退出VR刷新页面。':`${canControl?'Grip 移动 · Trigger 夹爪':'头部本地跟踪 · 双手柄仅显示'} · 距收包 ${age.toFixed(0)}ms`),22,96);
    gl.bindTexture(gl.TEXTURE_2D,hudTexture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,hudCanvas);
  }
  gl.disable(gl.DEPTH_TEST);gl.useProgram(hudProgram);gl.bindVertexArray(hudVAO);gl.uniformMatrix4fv(gl.getUniformLocation(hudProgram,'projection'),false,projection);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,hudTexture);gl.uniform1i(gl.getUniformLocation(hudProgram,'image'),0);gl.drawArrays(gl.TRIANGLES,0,6);gl.enable(gl.DEPTH_TEST);
}
const coachCanvas=document.createElement('canvas');coachCanvas.width=1024;coachCanvas.height=512;
const coach2d=coachCanvas.getContext('2d');
const coachModel=cameraWorld([.62,1.08,.08],[1.24,.41,-.79]);
function setupGuidance(){
 guideProgram=program(`#version 300 es
 layout(location=0) in vec3 p;layout(location=1) in vec3 c;uniform mat4 mvp;out vec3 color;
 void main(){color=c;gl_Position=mvp*vec4(p,1.);}`,`#version 300 es
 precision mediump float;in vec3 color;out vec4 frag;void main(){frag=vec4(color,1.);}`);
 guideVAO=gl.createVertexArray();gl.bindVertexArray(guideVAO);guideBuffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,guideBuffer);
 gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,24,0);
 gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,3,gl.FLOAT,false,24,12);
 coachProgram=program(`#version 300 es
 layout(location=0) in vec2 xy;uniform mat4 mvp;out vec2 uv;
 void main(){uv=xy*.5+.5;gl_Position=mvp*vec4(xy.x*.26,xy.y*.13,0.,1.);}`,`#version 300 es
 precision mediump float;in vec2 uv;uniform sampler2D image;out vec4 frag;
 void main(){frag=texture(image,vec2(uv.x,1.-uv.y));}`);
 coachTexture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,coachTexture);
 gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
 gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
}
function prepareGuides(){
 const vertices=[];const line=(a,b,c)=>vertices.push(...a,...c,...b,...c);
 function arrow(a,b,c){line(a,b,c);const d=b.map((v,i)=>v-a[i]),length=Math.hypot(...d);if(length<.003)return;
  const u=d.map(v=>v/length),v=norm(cross(u,Math.abs(u[2])<.9?[0,0,1]:[1,0,0]));
  const size=Math.min(.012,length*.3);for(const sign of [-1,1])line(b,b.map((x,i)=>x-size*u[i]+sign*size*.5*v[i]),c);
 }
 if(guidanceToggle.checked){
  const origin=[0,-.43,.90];for(const [d,c] of [[[.09,0,0],[1,.2,.2]],[[0,.09,0],[.2,1,.3]],[[0,0,.09],[.25,.55,1]]])arrow(origin,origin.map((v,i)=>v+d[i]),c);
  for(const tool of toolFrames){
   const model=poses[tool.pose_index];if(!model)continue;const actual=point(model,tool.tcp_local_m),color=tool.side==='left'?[.15,.65,1]:[1,.55,.12];
   for(const [d,c] of [[[.025,0,0],[1,.2,.2]],[[0,.025,0],[.2,1,.3]],[[0,0,.025],[.25,.55,1]]])arrow(actual,point(model,tool.tcp_local_m.map((v,i)=>v+d[i])),c);
   for(let k=0;k<20;k++){const a=k*Math.PI/10,b=(k+1)*Math.PI/10;line([actual[0]+.014*Math.cos(a),actual[1]+.014*Math.sin(a),actual[2]],[actual[0]+.014*Math.cos(b),actual[1]+.014*Math.sin(b),actual[2]],color);}
   const state=controlStatus?.arms?.[tool.side],target=state?.target_position_m,q=state?.target_quat_xyzw;
   if(target&&q){const tint=state.error?[1,.15,.15]:state.limited?[1,.85,.1]:color,m=poseMatrix([...target,...q]);arrow(actual,target,tint);
    for(const d of [[.045,0,0],[0,.045,0],[0,0,.045]])arrow(target,point(m,d),tint);
   }
  }
 }
 guideCount=vertices.length/6;gl.bindBuffer(gl.ARRAY_BUFFER,guideBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertices),gl.DYNAMIC_DRAW);
}
function drawGuides(mvp){if(!guideCount)return;gl.useProgram(guideProgram);gl.bindVertexArray(guideVAO);gl.uniformMatrix4fv(gl.getUniformLocation(guideProgram,'mvp'),false,mvp);gl.drawArrays(gl.LINES,0,guideCount);}
function armHint(side){const a=controlStatus?.arms?.[side];if(!a)return '等待控制状态';
 const e=a.error||'';if(e.startsWith('Tracking invalid'))return '手柄放到头显可见范围';
 if(e.startsWith('Tracking jump'))return '追踪跳变，请松开 Grip';
 if(e.startsWith('Following error'))return '跟随落后，请松 Grip 再握';
 if(e.startsWith('Target outside'))return '目标越界，请松 Grip 换手势';
 if(a.require_release||e.startsWith('Input stale'))return '先松开 Grip';
 return e||(a.enabled?(a.limited?'正在跟随，已限速':'正在跟随'):'保位；Grip 开始跟随');
}
function drawCoach(pv,now){
 if(!guidanceToggle.checked)return;
 if(now-lastCoach>200){lastCoach=now;
  coach2d.fillStyle='#102c3c';coach2d.fillRect(0,0,1024,512);coach2d.fillStyle='#effaff';coach2d.font='bold 42px sans-serif';
  coach2d.fillText(`${robotLabel} · 操作指南`,30,55);coach2d.font='34px sans-serif';
  const lessons=['按住 Grip 移动；松开换手势','Trigger 闭合；松开 Trigger 张开','先调夹爪朝向，再小步接近衣物','先练单臂，再分别找两侧抓点'];
  const rows=[lessons[Number(lessonSelect.value)],`${frameSelect.value==='table'?'桌面方向':'原俯视方向'} · ${rotationSelect.value==='locked'?'锁定朝向':'手腕跟随'}`,
   `手柄 10cm → 目标 ${(translationScale*10).toFixed(0)}cm`,
   '台边轴：红向右 · 绿向前 · 蓝向上',`左蓝：${armHint('left')}`,`右橙：${armHint('right')}`,'圆环实位 · 同色架目标 · 连线误差'];
  rows.forEach((text,i)=>coach2d.fillText(text,30,115+i*57));
  gl.bindTexture(gl.TEXTURE_2D,coachTexture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,coachCanvas);
 }
 gl.useProgram(coachProgram);gl.bindVertexArray(hudVAO);gl.uniformMatrix4fv(gl.getUniformLocation(coachProgram,'mvp'),false,mul(mul(pv,anchorInverse),coachModel));
 gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,coachTexture);gl.uniform1i(gl.getUniformLocation(coachProgram,'image'),0);gl.drawArrays(gl.TRIANGLES,0,6);
}
function desktopFrame(now){
  requestAnimationFrame(desktopFrame);if(session)return;
  const w=Math.round(canvas.clientWidth*devicePixelRatio),h=Math.round(canvas.clientHeight*devicePixelRatio);
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
  gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,w,h);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  const mvp=mul(mul(perspective(w/h),desiredInverse),simToXR);for(const m of meshes)draw(m,mvp);prepareGuides();drawGuides(mvp);updateUI(now);
}
function xrFrame(now,frame){
  if(!session)return;session.requestAnimationFrame(xrFrame);
  const pose=frame.getViewerPose(reference);if(!pose)return;
  if(!anchorInverse){
    try{const inputAnchor=mapInputToSim(pose.transform.matrix,'table');const viewAnchor=mul(pose.transform.matrix,desiredInverse);
      tableInputInverse=inputAnchor;anchorInverse=viewAnchor;
      if(lastError==='请自然看向前方后重新校准')lastError='';
    }catch(error){fail(error);command({type:'hold'});return;}
  }
  const layer=session.renderState.baseLayer;gl.bindFramebuffer(gl.FRAMEBUFFER,layer.framebuffer);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  const hands=[];for(const input of session.inputSources){if(input.gripSpace){const p=frame.getPose(input.gripSpace,reference);if(p)hands.push({matrix:p.transform.matrix,color:input.handedness==='left'?[.15,.65,1.]:[1.,.55,.12]});}}
  controllerCount=hands.length;sendInput(frame,now);prepareGuides();
  for(const view of pose.views){const vp=layer.getViewport(view);gl.viewport(vp.x,vp.y,vp.width,vp.height);
    const pv=mul(view.projectionMatrix,view.transform.inverse.matrix),mvp=mul(mul(pv,anchorInverse),simToXR);
    for(const m of meshes)draw(m,mvp);
    drawGuides(mvp);
    for(const hand of hands)draw(controller,mul(pv,hand.matrix),hand.color);
    drawCoach(pv,now);
    // Keep the healthy view unobstructed; still warn clearly if live state stops.
    if(showHud||connection!=='connected'||(lastPacket&&now-lastPacket>1000)||(canControl&&controlStatus&&Object.values(controlStatus.arms).some(a=>a.error)))drawHUD(view.projectionMatrix,now);
  }
  updateUI(now);
}
enter.onclick=async()=>{try{
  const s=await navigator.xr.requestSession('immersive-vr',{requiredFeatures:['local-floor']});
  await gl.makeXRCompatible();reference=await s.requestReferenceSpace('local-floor');
  s.updateRenderState({baseLayer:new XRWebGLLayer(s,gl,{alpha:false,depth:true,antialias:true}),depthNear:.02,depthFar:30});
  session=s;anchorInverse=null;tableInputInverse=null;lastHud=0;lastCoach=0;frameCounter=0;fpsEpoch=performance.now();enter.disabled=true;
  s.addEventListener('end',()=>{command({type:'hold'});session=null;reference=null;controllerCount=0;gripsDown=false;frameSelect.disabled=false;rotationSelect.disabled=false;enter.disabled=!xrSupported||connection!=='connected';});
  s.requestAnimationFrame(xrFrame);
}catch(error){fail(error);}};
recenter.onclick=()=>{command({type:'hold'});anchorInverse=null;tableInputInverse=null;};
for(const select of [frameSelect,rotationSelect])select.onchange=()=>{command({type:'hold'});lastCoach=0;};
lessonSelect.onchange=()=>{lastCoach=0;};guidanceToggle.onchange=()=>{lastCoach=0;};
document.getElementById('reset').onclick=()=>{command({type:'reset'});};
window.addEventListener('pagehide',()=>command({type:'hold'}));
document.getElementById('metrics').onclick=()=>{showHud=!showHud;document.getElementById('metrics').textContent=showHud?'隐藏 VR 指标':'显示 VR 指标';lastHud=0;};
try{
  setup();setupGuidance();connect();requestAnimationFrame(desktopFrame);
  if(navigator.xr)navigator.xr.isSessionSupported('immersive-vr').then(supported=>{xrSupported=supported;enter.disabled=!supported||received===0;});
}catch(error){fail(error);}
