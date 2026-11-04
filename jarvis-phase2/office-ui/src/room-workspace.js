import * as THREE from 'three';
import {box,cylinder,avatar,meetingChair} from './office-assets.js';

// A demonstration of furniture use, never a fabricated employee task.
export class RoomWorkspace {
 constructor(parent,p,department,large=false){
  this.department=department;this.large=large;this.mode='rest';this.time=0;this.hits=[];
  this.group=new THREE.Group();parent.add(this.group);
  box(this.group,2.85,1.58,.13,p.metal,.35,1.83,-5.38,.05);
  const canvas=document.createElement('canvas');canvas.width=512;canvas.height=288;this.canvas=canvas;this.context=canvas.getContext('2d');this.context.scale(.5,.5);
  const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;this.texture=texture;
  this.board=new THREE.Mesh(new THREE.PlaneGeometry(2.66,1.4),new THREE.MeshBasicMaterial({map:texture}));this.board.position.set(.35,1.83,-5.303);this.group.add(this.board);
  this.hit(this.board,'board');box(this.group,2.4,.045,.14,p.metal,.35,1.02,-5.25);
  for(let i=0;i<3;i++)cylinder(this.group,.015,.12,[p.clay,p.leaf,p.ivory][i],-.55+i*.15,1.1,-5.22);
  // Two cabinets, open shelves, folders and a movable door.
  box(this.group,1.45,2.12,.5,p.wood,4.45,1.26,-5.23,.03);
  box(this.group,1.31,1.94,.04,p.dark,4.45,1.26,-4.95);
  for(const y of [.48,.94,1.42,1.9,2.3])box(this.group,1.39,.045,.5,p.wood,4.45,y,-5.22);
  for(let row=0;row<3;row++)for(let j=0;j<6;j++){box(this.group,.11,.32,.27,j%2?p.ivory:p.fabric,3.94+j*.17,.68+row*.48,-5.08);box(this.group,.06,.08,.008,p.paper,3.94+j*.17,.72+row*.48,-4.94);}
  this.door=new THREE.Group();this.door.position.set(3.72,1.28,-4.93);this.group.add(this.door);
  box(this.door,.7,2.02,.045,p.ivory,.35,0,0,.025);box(this.door,.025,.24,.06,p.brass,.61,0,.045);
  this.door.traverse(o=>{if(o.isMesh){o.userData.static=false;this.hit(o,'storage');}});
  if(large){
   box(this.group,2.35,.08,.68,p.wood,0,.89,4.65,.06);
   for(const x of [-.85,.85])box(this.group,.07,.72,.5,p.metal,x,.49,4.65);
   meetingChair(this.group,p,-1.65,4.65,Math.PI/2);meetingChair(this.group,p,1.65,4.65,-Math.PI/2);
  }
  // A clickable agenda on the meeting table.
  this.tableCenter=new THREE.Vector3(large?0:2.8,.95,large?4.65:.8);
  const pad=box(this.group,.43,.035,.32,p.dark,...this.tableCenter.toArray(),.02);this.hit(pad,'meeting');
  for(const x of [-.62,.62]){cylinder(this.group,.065,.18,p.glass,this.tableCenter.x+x,1.02,this.tableCenter.z);}
  this.actor=null;this.partner=null;
  this.drawBoard();
 }
 hit(mesh,usage){mesh.userData.static=false;mesh.userData.department=this.department.kod;mesh.userData.usage=usage;this.hits.push(mesh);}
 setWork(items){this.items=items;this.drawBoard();}
 drawBoard(){const c=this.context;c.fillStyle='#122b31';c.fillRect(0,0,1024,576);c.fillStyle='#b7d4c1';c.font='500 29px Segoe UI';c.fillText('BİRİM ÇALIŞMA TAHTASI',54,66);c.fillStyle='#f0f3e9';c.font='600 42px Segoe UI';c.fillText(this.department.ad,54,133,915);c.font='27px Segoe UI';c.fillStyle='#c8d8d1';c.fillText((this.department.kadro||[]).length+' kayıtlı ekip üyesi',54,187);const open=(this.items||[]).filter(i=>i.status!=='resolved');const cards=[open.length+' açık takip',open.filter(i=>!i.owner).length+' sorumlu eksik',open.filter(i=>i.overdue).length+' geciken'];cards.forEach((s,i)=>{const x=54+i*311;c.fillStyle=this.mode==='board'&&i===Math.floor(this.time/2)%3?'#506f59':'#27434a';c.fillRect(x,239,285,137);c.fillStyle='#e4eee5';c.font='27px Segoe UI';c.fillText(s,x+18,292,250);c.fillStyle='#91b7a0';c.fillRect(x+18,326,220,5);});c.font='24px Segoe UI';c.fillStyle='#b3c6bd';c.fillText(this.items?'Gerçek işleri açmak için tahtaya tıklayın':'İş kayıtları henüz yüklenmedi',54,464);c.fillText(open[0]?.title||'Bu birime atanmış açık takip bulunmuyor',54,507,915);this.texture.needsUpdate=true;}
 start(mode){this.mode=mode;this.time=0;if(!this.actor&&mode!=='rest'){this.actor=avatar(17,false);this.partner=avatar(21,true);this.group.add(this.actor.group,this.partner.group);}if(!this.actor)return;this.actor.group.visible=mode!=='rest';this.partner.group.visible=mode==='meeting';this.drawBoard();this.update(0,true);}
 update(delta,enabled){
  if(!this.actor)return;
  if(!enabled){this.actor.group.visible=false;this.partner.group.visible=false;this.door.rotation.y=0;return;}
  this.actor.group.visible=this.mode!=='rest';this.partner.group.visible=this.mode==='meeting';if(this.mode==='rest')return;
  const before=Math.floor(this.time/2);this.time+=delta;const t=this.time%18;
  const endpoint=this.mode==='board'?new THREE.Vector3(.9,.14,-4.5):this.mode==='storage'?new THREE.Vector3(4.45,.14,-4.4):new THREE.Vector3(this.large?0:2.8,.14,this.large?3.8:2.25);
  const start=new THREE.Vector3(5.1,.14,4.1),corner=new THREE.Vector3(5.1,.14,endpoint.z);
  const progress=t<5?t/5:t>14?(18-t)/4:1;
  const route=progress<.7?start.clone().lerp(corner,progress/.7):corner.clone().lerp(endpoint,(progress-.7)/.3);
  const moving=progress<1;this.actor.group.position.copy(route);this.actor.group.rotation.y=Math.PI;
  this.actor.legs.forEach((leg,i)=>leg.rotation.x=moving?Math.sin(this.time*7+i*Math.PI)*.28:0);
  this.actor.arms.forEach((arm,i)=>{arm.rotation.x=moving?Math.sin(this.time*7+i*Math.PI)*.18: i===1?-.8+Math.sin(this.time*2)*.15:-.2;});
  this.door.rotation.y=this.mode==='storage'&&!moving?Math.sin(Math.min((t-5)/2,1)*Math.PI/2)*1.4:0;
  this.partner.group.position.set(this.large?1.65:4.15,.14,this.large?4.65:.8);this.partner.group.rotation.y=-Math.PI/2;this.partner.head.rotation.y=Math.sin(this.time)*.09;
  if(this.mode==='board'&&Math.floor(this.time/2)!==before)this.drawBoard();
 }
}
