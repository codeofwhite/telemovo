// Execute the browser's actual pure coordinate functions without a DOM or GPU.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../viewer/viewer.js'),'utf8');
const start=source.indexOf('function mul('),end=source.indexOf('function command(');
assert(start>=0&&end>start);
const context={};vm.createContext(context);
vm.runInContext(source.slice(start,end)+'\nglobalThis.math={mul,poseMatrix,point,mapInputToSim,yawFrame};',context);
const {mul,poseMatrix,point,mapInputToSim}=context.math;
const rotation=(axis,angle)=>{const q=[0,0,0,Math.cos(angle/2)];q[axis]=Math.sin(angle/2);return poseMatrix([0,0,0,...q]);};
let cases=0;
for(const yaw of [0,.7,1.57])for(const pitch of [0,.4,-.35])for(const roll of [0,.2]){
 const heading=rotation(1,yaw),head=mul(mul(heading,rotation(0,pitch)),rotation(2,roll));
 head[12]=.3;head[13]=1.6;head[14]=-.2;
 const map=mapInputToSim(head,'table'),origin=[head[12],head[13],head[14]],base=point(map,origin);
 for(const [direction,expected] of [[[heading[0],0,heading[2]],[1,0,0]],[[0,1,0],[0,0,1]],[[-heading[8],0,-heading[10]],[0,1,0]]])for(const sign of [-1,1]){
  const target=origin.map((x,i)=>x+direction[i]*sign*.1),actual=point(map,target).map((x,i)=>x-base[i]);
  actual.forEach((x,i)=>assert(Math.abs(x-expected[i]*sign*.1)<1e-6));cases++;
 }
}
assert.throws(()=>mapInputToSim(rotation(0,Math.PI/2),'table'),/自然/);
console.log(`PASS: ${cases} table-frame movement cases; vertical-heading rejection`);
