import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

export const material=(color,options={})=>new THREE.MeshStandardMaterial({color,roughness:.75,metalness:.04,...options});
export function box(parent,w,h,d,mat,x=0,y=0,z=0,round=0){
 const m=new THREE.Mesh(round?new RoundedBoxGeometry(w,h,d,3,round):new THREE.BoxGeometry(w,h,d),mat);
 m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;m.userData.static=true;parent.add(m);return m;
}
export function cylinder(parent,r,h,mat,x,y,z){const m=new THREE.Mesh(new THREE.CylinderGeometry(r,r,h,32),mat);m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;m.userData.static=true;parent.add(m);return m;}
function textile(base,kind){
 const c=document.createElement('canvas');c.width=c.height=256;const ctx=c.getContext('2d');ctx.fillStyle=base;ctx.fillRect(0,0,256,256);
 let seed=42;const rand=()=>{seed=(seed*16807)%2147483647;return seed/2147483647;};
 for(let i=0;i<14000;i++){ctx.fillStyle=rand()>.5?'rgba(255,255,255,.08)':'rgba(0,0,0,.08)';ctx.fillRect(rand()*256,rand()*256,kind==='fabric'?1:2,kind==='fabric'?3:1);}
 if(kind==='fabric'){ctx.strokeStyle='rgba(28,32,32,.07)';for(let i=0;i<256;i+=4){ctx.beginPath();ctx.moveTo(i,0);ctx.lineTo(i,256);ctx.stroke();}}
 const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.set(3,3);return t;
}
export function palette(){
 const c=document.createElement('canvas');c.width=c.height=256;const ctx=c.getContext('2d');ctx.fillStyle='#9e7753';ctx.fillRect(0,0,256,256);
 for(let i=0;i<120;i++){ctx.strokeStyle=i%2?'rgba(65,39,23,.08)':'rgba(255,238,211,.12)';ctx.lineWidth=1+(i%3);ctx.beginPath();ctx.moveTo(0,i*2.15);ctx.bezierCurveTo(60,i*2.15+3,170,i*2.15-2,256,i*2.15+1);ctx.stroke();}
 const texture=new THREE.CanvasTexture(c);texture.colorSpace=THREE.SRGBColorSpace;texture.wrapS=texture.wrapT=THREE.RepeatWrapping;texture.repeat.set(2,1);
 return {wood:material(0xffffff,{map:texture}),ivory:material(0xe9e4db,{roughness:.62}),stone:material(0xffffff,{map:textile('#b4b5ad','stone'),roughness:.8}),metal:material(0x25343b,{metalness:.65,roughness:.35}),fabric:material(0xffffff,{map:textile('#697e73','fabric'),roughness:.96}),carpet:material(0xffffff,{map:textile('#888d86','fabric'),roughness:1}),clay:material(0xcaa786),lamp:material(0xffe7bb,{emissive:0xffd695,emissiveIntensity:2}),dark:material(0x293a43),leaf:material(0x4d7356),brass:material(0xb99b62,{metalness:.65,roughness:.35}),glass:new THREE.MeshPhysicalMaterial({color:0xc8dfdb,transparent:true,opacity:.19,depthWrite:false,roughness:.06,metalness:.05,clearcoat:1,side:THREE.DoubleSide}),screen:material(0x132a36,{emissive:0x457f91,emissiveIntensity:.35}),paper:material(0xf1eee6)};
}
export function plant(parent,p,x,z,scale=1){
 const g=new THREE.Group();g.position.set(x,.12,z);g.scale.setScalar(scale);parent.add(g);
 cylinder(g,.23,.42,p.ivory,0,.21,0);cylinder(g,.2,.02,p.dark,0,.43,0);cylinder(g,.017,.92,p.wood,0,.86,0);
 const leafMaterial=p.leaf.clone();leafMaterial.side=THREE.DoubleSide;leafMaterial.roughness=.7;
 for(let i=0;i<11;i++){
  const shape=new THREE.Shape();shape.moveTo(0,0);shape.bezierCurveTo(-.2,.15,-.24,.4,0,.59);shape.bezierCurveTo(.22,.38,.2,.14,0,0);
  const geo=new THREE.ShapeGeometry(shape,8);const pos=geo.attributes.position;for(let j=0;j<pos.count;j++)pos.setZ(j,Math.sin(pos.getY(j)*5)*.075);geo.computeVertexNormals();
  const leaf=new THREE.Mesh(geo,leafMaterial);const a=i*2.399;leaf.position.set(Math.sin(a)*.05,.58+i*.065,Math.cos(a)*.05);leaf.rotation.set(.5+Math.cos(a)*.45,a,.4+Math.sin(a)*.4);leaf.scale.setScalar(.7+(i%3)*.1);leaf.userData.static=true;leaf.castShadow=true;g.add(leaf);
 }return g;
}
export function sign(parent,text,x,y,z,w=3.5,color='#e9e4d9'){
 const c=document.createElement('canvas');c.width=768;c.height=128;const ctx=c.getContext('2d');ctx.fillStyle='#1e3038';ctx.fillRect(0,0,768,128);ctx.fillStyle=color;ctx.font='500 40px Segoe UI, sans-serif';ctx.textAlign='center';ctx.fillText(text,384,80,720);
 const tex=new THREE.CanvasTexture(c);tex.colorSpace=THREE.SRGBColorSpace;
 const m=new THREE.Mesh(new THREE.PlaneGeometry(w,w/6),new THREE.MeshBasicMaterial({map:tex,side:THREE.DoubleSide}));m.position.set(x,y,z);parent.add(m);return m;
}
export function sofa(parent,p,x,z,rotation=0){
 const g=new THREE.Group();g.position.set(x,0,z);g.rotation.y=rotation;parent.add(g);
 box(g,2.55,.24,.9,p.dark,0,.32,0,.1);
 for(let i=0;i<3;i++){box(g,.73,.2,.72,p.fabric,(i-1)*.76,.53,.04,.09);const back=box(g,.73,.54,.17,p.fabric,(i-1)*.76,.79,-.34,.075);back.rotation.x=-.1;}
 for(const x of [-1.22,1.22])box(g,.18,.48,.92,p.fabric,x,.63,0,.07);
 for(const x of [-.95,.95])for(const z of [-.28,.28])box(g,.07,.23,.07,p.metal,x,.12,z);
 const cushion=box(g,.31,.32,.12,p.clay,-.92,.77,-.12,.07);cushion.rotation.z=.18;
 return g;
}
export function desk(parent,p,x,z){
 const g=new THREE.Group();g.position.set(x,.14,z);parent.add(g);
 box(g,1.4,.08,.73,p.wood,0,.72,0,.035);for(const dx of [-.59,.59]){box(g,.045,.69,.5,p.metal,dx,.35,0);}
 box(g,.62,.4,.055,p.metal,0,1.04,.14,.018);const screen=box(g,.56,.33,.012,p.screen,0,1.045,.106);screen.userData.static=false;box(g,.05,.16,.05,p.metal,0,.8,.14);box(g,.25,.025,.17,p.metal,0,.77,.13);
 box(g,.45,.018,.16,p.dark,-.04,.77,-.19,.015);box(g,.07,.025,.1,p.ivory,.33,.78,-.17,.015);box(g,.19,.015,.24,p.paper,-.47,.77,-.1);cylinder(g,.045,.11,p.ivory,.48,.82,.15);
 // Task chair, five-spoke base, armrests and upholstered mesh back.
 box(g,.47,.1,.43,p.dark,0,.45,-.67,.06);box(g,.45,.47,.08,p.dark,0,.72,-.89,.05);cylinder(g,.035,.3,p.metal,0,.25,-.67);
 for(let i=0;i<5;i++){const b=box(g,.035,.035,.42,p.metal,0,.12,-.67);b.rotation.y=i*Math.PI*2/5;}
 for(const dx of [-.28,.28]){box(g,.04,.23,.04,p.metal,dx,.55,-.66);box(g,.08,.045,.34,p.dark,dx,.67,-.66,.02);}
 return {screen,chairZ:z-.67,group:g};
}
export function avatar(index=0,seated=false,executive=false){
 const g=new THREE.Group(),shirt=material(executive?0x202d3d:[0x778a8e,0xc4b49b,0x686d63,0x9e857d,0x39494e,0x897c6c][index%6]),skin=material([0xcda17e,0xdfb99c,0x98694e,0xb98762][index%4]),pants=material(0x343d41),hair=material([0x302924,0x594131,0x272522][index%3]);
 const mesh=(parent,geo,mat,x,y,z,sx=1,sy=1,sz=1)=>{const m=new THREE.Mesh(geo,mat);m.position.set(x,y,z);m.scale.set(sx,sy,sz);m.castShadow=true;parent.add(m);return m;};
 const torso=mesh(g,new THREE.CylinderGeometry(.17,.155,.46,20),shirt,0,seated?.92:1.08,0,1.1,1,.7);
 mesh(g,new THREE.SphereGeometry(.18,16,10),shirt,0,seated?1.12:1.28,0,1.17,.46,.68);
 mesh(g,new THREE.CylinderGeometry(.053,.065,.1,12),skin,0,seated?1.21:1.37,0);
 const head=new THREE.Group();head.position.y=seated?1.36:1.52;g.add(head);
 mesh(head,new THREE.SphereGeometry(.145,24,16),skin,0,0,0,.88,1.18,.91);
 mesh(head,new THREE.SphereGeometry(.147,24,16,0,Math.PI*2,0,Math.PI*.56),hair,0,.016,-.007,.91,1.15,.95);
 if(index%3===1)mesh(head,new THREE.SphereGeometry(.14,16,10),hair,0,-.09,-.075,.95,1.3,.55);
 mesh(head,new THREE.SphereGeometry(.025,10,8),skin,0,-.015,.127,.7,1,1);
 for(const side of [-1,1]){mesh(head,new THREE.SphereGeometry(.028,10,8),skin,side*.13,-.015,0,.6,1,.65);mesh(head,new THREE.SphereGeometry(.009,8,6),hair,side*.047,.018,.121,1,.65,.6);}
 const collar=box(g,.115,.055,.12,material(0xe1ddd4),0,seated?1.145:1.305,.045,.016);collar.userData.static=false;
 if(executive){
  const front=seated?.98:1.14;const white=material(0xf0ece5),tie=material(0x926747);
  const shirtFront=box(g,.11,.32,.025,white,0,front,.125,.01);shirtFront.userData.static=false;
  const necktie=box(g,.035,.23,.02,tie,0,front+.02,.15);necktie.userData.static=false;
  for(const side of [-1,1]){const lapel=box(g,.075,.25,.025,shirt,side*.085,front+.04,.14,.01);lapel.rotation.z=side*.3;lapel.userData.static=false;}
 }
 const arms=[],legs=[];
 for(const side of [-1,1]){
  const arm=new THREE.Group();arm.position.set(side*.225,seated?1.09:1.25,0);g.add(arm);
  mesh(arm,new THREE.CapsuleGeometry(.061,.16,5,10),shirt,0,-.105,0);
  const lower=new THREE.Group();lower.position.y=-.245;arm.add(lower);mesh(lower,new THREE.CapsuleGeometry(.043,.15,5,10),shirt,0,-.09,0);mesh(lower,new THREE.SphereGeometry(.052,12,8),skin,0,-.215,.015,.8,1.2,.6);
  if(seated){arm.rotation.x=-.42;lower.rotation.x=-1;}arms.push(arm);
  const leg=new THREE.Group();leg.position.set(side*.105,seated?.67:.84,0);g.add(leg);
  mesh(leg,new THREE.CapsuleGeometry(.073,.24,5,10),pants,0,-.16,0);
  const calf=new THREE.Group();calf.position.y=-.35;leg.add(calf);mesh(calf,new THREE.CapsuleGeometry(.055,.25,5,10),pants,0,-.17,0);mesh(calf,new THREE.SphereGeometry(1,12,8),pants,0,-.35,.055,.073,.055,.14);
  if(seated){leg.rotation.x=-Math.PI/2;calf.rotation.x=Math.PI/2;}legs.push(leg);
 }
 head.traverse(n=>{if(n.isMesh)n.userData.static=true;});batchStatic(head);
 g.traverse(n=>{if(n.isMesh){n.userData.static=false;n.castShadow=true;}});
 // Distant avatars use one coloured mesh. The articulated rig is retained nearby.
 g.updateMatrixWorld(true);const pieces=[];
 g.traverse(m=>{if(!m.isMesh)return;const geometry=m.geometry.index?m.geometry.toNonIndexed():m.geometry.clone();geometry.applyMatrix4(m.matrixWorld);const color=m.material.color,colors=new Float32Array(geometry.attributes.position.count*3);for(let i=0;i<colors.length;i+=3){colors[i]=color.r;colors[i+1]=color.g;colors[i+2]=color.b;}geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));pieces.push(geometry);});
 const simple=new THREE.Mesh(mergeGeometries(pieces),new THREE.MeshStandardMaterial({vertexColors:true,roughness:.85}));simple.castShadow=true;pieces.forEach(geo=>geo.dispose());
 const lod=new THREE.LOD();lod.addLevel(g,0);lod.addLevel(simple,24);
 return {group:lod,rig:g,body:torso,head,arms,legs,seated};
}

export function meetingChair(parent,p,x,z,rotation=0){
 const g=new THREE.Group();g.position.set(x,.16,z);g.rotation.y=rotation;parent.add(g);
 box(g,.53,.12,.52,p.fabric,0,.43,0,.07);box(g,.54,.48,.1,p.fabric,0,.7,-.23,.055);
 for(const dx of [-.2,.2])for(const dz of [-.18,.18]){const leg=box(g,.035,.39,.035,p.metal,dx,.2,dz);leg.rotation.z=dx*.2;}
 return g;
}
export function meetingTable(parent,p,x,z){
 cylinder(parent,1.05,.09,p.wood,x,.89,z);cylinder(parent,.3,.73,p.metal,x,.5,z);
 for(let i=0;i<4;i++){const a=i*Math.PI/2;meetingChair(parent,p,x+Math.sin(a)*1.35,z+Math.cos(a)*1.35,a+Math.PI);}
 box(parent,.3,.02,.4,p.paper,x-.2,.95,z);cylinder(parent,.06,.14,p.ivory,x+.35,1,z+.3);
}
export function artwork(parent,p,x,y,z,w=2.4){
 box(parent,w+.1,w*.62+.1,.08,p.metal,x,y,z);
 const c=document.createElement('canvas');c.width=512;c.height=320;const ctx=c.getContext('2d');ctx.fillStyle='#d9d0bd';ctx.fillRect(0,0,512,320);
 ctx.fillStyle='#384e49';ctx.beginPath();ctx.arc(185,160,125,0,Math.PI*2);ctx.fill();ctx.fillStyle='#aa7c58';ctx.fillRect(260,50,115,230);ctx.strokeStyle='#e8deca';ctx.lineWidth=12;ctx.beginPath();ctx.arc(260,160,80,0,Math.PI*2);ctx.stroke();
 const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;const m=new THREE.Mesh(new THREE.PlaneGeometry(w,w*.62),new THREE.MeshStandardMaterial({map:t,roughness:.9}));m.position.set(x,y,z+.046);parent.add(m);
}
export function pendant(parent,p,x,z,length=2){
 box(parent,length,.09,.17,p.metal,x,3.05,z,.035);box(parent,length-.1,.02,.1,p.lamp,x,2.99,z);
 for(const dx of [-length*.35,length*.35])cylinder(parent,.008,.5,p.metal,x+dx,3.35,z);
}
export function batchStatic(root){
 root.updateMatrixWorld(true);const groups=new Map();const inverse=new THREE.Matrix4().copy(root.matrixWorld).invert();
 root.traverse(m=>{if(!m.isMesh||!m.userData.static||m.material.transparent)return;const list=groups.get(m.material)||[];list.push(m);groups.set(m.material,list);});
 for(const [mat,meshes] of groups){if(meshes.length<2)continue;const geometries=meshes.map(m=>{const g=m.geometry.clone().toNonIndexed();g.applyMatrix4(new THREE.Matrix4().multiplyMatrices(inverse,m.matrixWorld));return g;});const merged=mergeGeometries(geometries);if(merged){const m=new THREE.Mesh(merged,mat);m.castShadow=true;m.receiveShadow=true;root.add(m);for(const old of meshes){old.removeFromParent();old.geometry.dispose();}}for(const g of geometries)g.dispose();}
}
