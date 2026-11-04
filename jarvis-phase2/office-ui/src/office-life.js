import {furnishGreenCommons} from './green-spaces.js';
import {brandPlaque,brandRug} from './brand-spaces.js';
import * as THREE from 'three';
import {box,cylinder,plant,sofa,sign,avatar,material} from './office-assets.js';

// Ambient actors have no roster identity and cannot affect operational status.
export class OfficeLife {
 constructor(parent,width,south,p){
  this.group=new THREE.Group();parent.add(this.group);this.time=0;this.enabled=false;this.visitors=[];this.south=south;this.width=width;
  this.locations=[-Math.min(width*.28,19),0,Math.min(width*.28,19)];this.moving=new THREE.Group();this.group.add(this.moving);
  const [wc,cafe,terrace]=this.locations;const zoneW=Math.min(width*.28,14);
  this.colliders=[{minX:wc-2.7,maxX:wc+2.7,minZ:south-3.6,maxZ:south-1.1},{minX:cafe-2.2,maxX:cafe+2.2,minZ:south-3.2,maxZ:south-2},{minX:cafe-1,maxX:cafe+1,minZ:south-.5,maxZ:south+1.5}];
  box(this.group,width-3,.16,9,p.ivory,0,.02,south);
  box(this.group,zoneW,.04,7,p.wood,terrace,.13,south);
  // WC: only the public entrance is visible, never an interior or a person inside.
  box(this.group,5,2.35,2,p.stone,wc,1.2,south-2.4,.04);
  this.door=new THREE.Group();this.door.position.set(wc-.55,.15,south-1.37);this.group.add(this.door);
  const door=box(this.door,1.1,2,.07,p.wood,.55,1,0);door.userData.static=false;
  const handle=box(this.door,.05,.17,.07,p.brass,.95,.93,.07);handle.userData.static=false;
  sign(this.group,'TUVALET',wc,2.16,south-1.32,1);
  this.wcLight=new THREE.Mesh(new THREE.SphereGeometry(.055,8,6),material(0x75c9aa,{emissive:0x75c9aa,emissiveIntensity:.8}));this.wcLight.position.set(wc+.8,1.8,south-1.32);this.group.add(this.wcLight);
  plant(this.group,p,wc-2.2,south-.9,1.2);
  // Coffee counter, espresso machine, shelves, lounge seating and low tables.
  box(this.group,5.4,2.6,.16,p.ivory,cafe,1.4,south-3.1);
  for(let i=0;i<30;i++)box(this.group,.065,2.4,.08,p.wood,cafe-2.45+i*.165,1.35,south-2.96);
  box(this.group,4,.98,.82,p.wood,cafe,.55,south-2.6,.04);box(this.group,4.2,.1,.94,p.ivory,cafe,1.08,south-2.6,.03);
  box(this.group,.7,.6,.48,p.metal,cafe-1.2,1.43,south-2.6,.05);box(this.group,.48,.2,.08,p.brass,cafe-1.2,1.4,south-2.32);
  for(let i=0;i<4;i++)cylinder(this.group,.07,.12,p.ivory,cafe-.5+i*.22,1.2,south-2.5);
  brandPlaque(this.group,p,'lcarlie',cafe,2.2,south-2.85,3.6);
  brandRug(this.group,p,'lcarlie',cafe,south+2.5,3,1.1);
  box(this.group,5.6,.025,3.3,p.carpet,cafe,.15,south+.5,.14);
  sofa(this.group,p,cafe-2.5,south+.5,Math.PI/2);sofa(this.group,p,cafe+2.5,south+.5,-Math.PI/2);
  cylinder(this.group,.8,.08,p.wood,cafe,.52,south+.5);cylinder(this.group,.15,.5,p.metal,cafe,.25,south+.5);
  box(this.group,.3,.025,.4,p.paper,cafe-.2,.58,south+.5);plant(this.group,p,cafe+3.8,south-2.8,1.3);
  // Open-air terrace, slatted decking and a dedicated smoking point.
  for(let i=0;i<Math.floor(zoneW/.4);i++)box(this.group,.018,.018,7,p.dark,terrace-zoneW/2+.25+i*.4,.16,south);
  box(this.group,zoneW,1.1,.05,p.glass,terrace,.7,south+3.5);box(this.group,zoneW,.045,.07,p.metal,terrace,1.26,south+3.5);
  for(const x of [-zoneW/2,zoneW/2]){box(this.group,.045,1.2,7,p.glass,terrace+x,.7,south);plant(this.group,p,terrace+x*.8,south+2.5,1.5);}
  sofa(this.group,p,terrace+1,south+1.5,Math.PI);cylinder(this.group,.18,.88,p.metal,terrace-1.7,.58,south+.8);
  sign(this.group,'TERAS',terrace,1.42,south+3.45,1.8);
  this.colliders.push(...furnishGreenCommons(this.group,p,this.locations,south,zoneW));
  this.puffs=[];
  for(let i=0;i<6;i++){const m=new THREE.Mesh(new THREE.SphereGeometry(.1,6,5),material(0xd1d5d1,{transparent:true,opacity:0,depthWrite:false}));this.moving.add(m);this.puffs.push(m);}
  for(let i=0;i<6;i++){
   const actor=avatar(i+2);this.moving.add(actor.group);const zone=i%3;const destination=new THREE.Vector3(this.locations[zone]+(zone===0?(i<3?-.18:.18):zone===1?(i<3?-1.2:1.2):(i<3?-1.2:-2.4)),.15,south+(zone===0?-1:zone===1?-1.35:1));
   const start=new THREE.Vector3(this.locations[(zone+1)%3]+(i<3?-1:1),.15,south+2.8);
   const points=[start,new THREE.Vector3(destination.x,.15,start.z),destination];
   const prop=zone===2?box(actor.arms[1],.025,.025,.17,p.paper,0,-.43,.06):cylinder(actor.arms[1],.055,.11,p.ivory,0,-.44,.04);prop.userData.static=false;prop.visible=false;
   this.visitors.push({...actor,zone,points,phase:i*10,prop});
  }
  this.setEnabled(false);
 }
 setEnabled(enabled){this.enabled=Boolean(enabled);this.moving.visible=this.enabled;}
 update(delta){
  if(!this.enabled)return;this.time+=delta;let occupied=false;let opening=false;
  for(const v of this.visitors){
   const t=(this.time+v.phase)%84;const outgoing=t>=58;const travel=t<24||outgoing;const u=t<24?t/24:outgoing?1-(t-58)/26:1;
   const a=v.points[0],b=v.points[1],c=v.points[2];const l1=a.distanceTo(b),l2=b.distanceTo(c),distance=THREE.MathUtils.clamp(u,0,1)*(l1+l2);
   const from=distance<l1?a:b,to=distance<l1?b:c;const ratio=distance<l1?distance/l1:(distance-l1)/l2;v.group.position.lerpVectors(from,to,ratio);
   const direction=to.clone().sub(from).multiplyScalar(outgoing?-1:1);if(travel)v.group.rotation.y=Math.atan2(direction.x,direction.z);else v.group.rotation.y=v.zone===2?0:Math.PI;
   const stride=travel?Math.sin(this.time*7.5+v.phase)*.4:0;v.legs[0].rotation.x=stride;v.legs[1].rotation.x=-stride;v.arms[0].rotation.x=-stride*.65;v.arms[1].rotation.x=stride*.65;
   v.group.position.y=.15+(travel?Math.abs(Math.sin(this.time*7.5+v.phase))*.025:0);v.head.rotation.y=travel?0:Math.sin(this.time*.8+v.phase)*.12;
   v.prop.visible=!travel&&v.zone!==0;
   if(!travel&&v.zone!==0){const sip=(Math.sin((t-24)*.6)+1)/2;v.arms[1].rotation.x=-.7-sip*.9;v.arms[1].rotation.z=-.12;v.head.rotation.x=sip*.045;}
   v.group.visible=!(v.zone===0&&t>25&&t<56);
   if(v.zone===0){occupied ||= t>25&&t<56;opening ||= (t>22&&t<26)||(t>55&&t<59);}
   // Small, restrained gag: a colleague notices a wobbling cup and steadies it.
   if(v.zone===1&&!travel&&t>40&&t<43){v.prop.rotation.z=Math.sin((t-40)*10)*.18;v.head.rotation.x=.12;}else v.prop.rotation.z=0;
  }
  this.door.rotation.y=THREE.MathUtils.damp(this.door.rotation.y,opening?-1.15:0,6,delta);
  this.wcLight.material.color.setHex(occupied?0xd99470:0x75c9aa);
  const smoker=this.visitors.find(v=>v.zone===2&&v.prop.visible&&v.group.visible);
  this.puffs.forEach((p,i)=>{p.visible=Boolean(smoker);if(!smoker)return;const age=(this.time*.35+i/6)%1;p.position.copy(smoker.group.position).add(new THREE.Vector3(.23+age*.35,1.35+age*.9,age*.15));p.scale.setScalar(.25+age*1.5);p.material.opacity=.075*(1-age);});
 }
}
