import * as THREE from 'three';
import {box,cylinder,plant,sofa,meetingChair,material,sign} from './office-assets.js';

function leafGeometry(){const shape=new THREE.Shape();shape.moveTo(0,0);shape.bezierCurveTo(-.17,.1,-.13,.37,0,.51);shape.bezierCurveTo(.13,.37,.17,.1,0,0);const geometry=new THREE.ShapeGeometry(shape,5);const position=geometry.attributes.position;for(let i=0;i<position.count;i++)position.setZ(i,Math.sin(position.getY(i)*6)*.045);geometry.computeVertexNormals();return geometry;}
export function canopyTree(parent,p,x,z,scale=1){
 const g=new THREE.Group();g.position.set(x,.16,z);g.scale.setScalar(scale);parent.add(g);
 box(g,1.1,.6,1.1,p.stone,0,.3,0,.1);box(g,.96,.018,.96,p.dark,0,.61,0,.08);
 cylinder(g,.09,2.15,p.wood,0,1.56,0);
 for(let i=0;i<5;i++){const a=i*2.399;const b=cylinder(g,.035,.85,p.wood,Math.cos(a)*.17,2.2+i*.09,Math.sin(a)*.17);b.rotation.z=Math.cos(a)*.48;b.rotation.x=Math.sin(a)*.48;}
 const foliage=p.canopyLeaf||(p.canopyLeaf=material(0xffffff,{roughness:.95,side:THREE.DoubleSide}));
 const leaves=new THREE.InstancedMesh(leafGeometry(),foliage,520);const transform=new THREE.Object3D();const shades=[0x587c4d,0x77935d,0x466b43,0x63865b];
 let seed=431;const random=()=>{seed=(seed*16807)%2147483647;return seed/2147483647;};
 for(let i=0;i<520;i++){const angle=i*2.399,vertical=random()*2-1,radius=Math.sqrt(1-vertical*vertical)*(.35+random()*.7);transform.position.set(Math.cos(angle)*radius,2.75+vertical*.65,Math.sin(angle)*radius);transform.rotation.set(random()*Math.PI,angle,random()*Math.PI);transform.scale.setScalar(.65+random()*.65);transform.updateMatrix();leaves.setMatrixAt(i,transform.matrix);leaves.setColorAt(i,new THREE.Color(shades[i%4]));}
 leaves.castShadow=true;leaves.receiveShadow=true;g.add(leaves);
 return {minX:x-.6*scale,maxX:x+.6*scale,minZ:z-.6*scale,maxZ:z+.6*scale};
}
export function herbPlanter(parent,p,x,z,width=3){
 box(parent,width,.5,.65,p.wood,x,.4,z,.04);box(parent,width-.15,.025,.5,p.dark,x,.66,z);
 for(let i=0;i<Math.floor(width/.35);i++){const px=x-width/2+.2+i*.35;for(let j=0;j<4;j++){const leaf=new THREE.Mesh(leafGeometry(),j%2?p.leaf:(p.herbLeaf||(p.herbLeaf=material(0x81966b))));leaf.scale.set(.7,.8,.7);leaf.rotation.set(.3,j*1.7,.3);leaf.position.set(px+Math.sin(j*2)*.07,.67+Math.cos(i)*.02,z+Math.cos(j*2)*.08);leaf.userData.static=true;leaf.castShadow=true;parent.add(leaf);}}
}
function bistro(parent,p,x,z){
 cylinder(parent,.55,.07,p.ivory,x,.9,z);cylinder(parent,.065,.69,p.brass,x,.53,z);cylinder(parent,.3,.045,p.metal,x,.19,z);
 meetingChair(parent,p,x-.86,z,Math.PI/2);meetingChair(parent,p,x+.86,z,-Math.PI/2);
 cylinder(parent,.07,.13,p.ivory,x-.16,1.0,z);cylinder(parent,.09,.18,p.clay,x+.15,1.03,z);const stem=cylinder(parent,.018,.25,p.leaf,x+.15,1.23,z);stem.rotation.z=.3;
}
export function furnishGreenCommons(parent,p,locations,south,zoneW){
 const [wc,cafe,terrace]=locations;const colliders=[];
 // Café shelves and a concise Turkish menu complement the original branded bar.
 for(const y of [1.65,2.22]){box(parent,1.2,.05,.3,p.wood,cafe+1.45,y,south-2.72);for(let i=0;i<4;i++)cylinder(parent,.06,.13,i%2?p.ivory:p.clay,cafe+1.05+i*.23,y+.09,south-2.68);}
 sign(parent,'KAHVE  ·  BİTKİ ÇAYI  ·  SU',cafe,1.46,south-2.15,2.1);
 colliders.push(canopyTree(parent,p,cafe-4.35,south-1.5,.95),canopyTree(parent,p,cafe+4.35,south-1.5,.95));
 herbPlanter(parent,p,cafe,south+3.7,4.4);
 // Low book shelves, cushions and warm reading lamps in the shared lounge.
 for(const side of [-1,1]){box(parent,1,.63,.35,p.wood,cafe+side*3.35,.49,south+1.5,.03);for(let i=0;i<5;i++)box(parent,.1,.3,.2,i%2?p.paper:p.clay,cafe+side*3.35-.3+i*.14,.95,south+1.5);cylinder(parent,.025,1.8,p.brass,cafe+side*3.6,1.1,south+.35);cylinder(parent,.28,.17,p.lamp,cafe+side*3.6,2.04,south+.35);}
 // Outdoor timber pergola: open slats preserve daylight and sight lines.
 const gx=terrace+zoneW*.13,gz=south-1.25,pw=Math.min(5.2,zoneW*.6),pd=3.2;
 for(const dx of [-pw/2,pw/2])for(const dz of [-pd/2,pd/2]){box(parent,.12,3.15,.12,p.wood,gx+dx,1.75,gz+dz);colliders.push({minX:gx+dx-.1,maxX:gx+dx+.1,minZ:gz+dz-.1,maxZ:gz+dz+.1});}
 for(const dx of [-pw/2,pw/2])box(parent,.15,.16,pd+.35,p.wood,gx+dx,3.34,gz);
 for(let i=0;i<9;i++)box(parent,pw+.3,.085,.12,p.wood,gx,3.46,gz-pd/2+i*pd/8);
 for(let i=0;i<6;i++)cylinder(parent,.055,.09,p.lamp,gx-pw*.4+i*pw*.16,3.24,gz+pd/2);
 sofa(parent,p,gx,gz-.8);box(parent,1.5,.07,.65,p.wood,gx,.65,gz+.1,.06);for(const dx of [-.55,.55])box(parent,.055,.43,.45,p.metal,gx+dx,.4,gz+.1);
 box(parent,3.7,.025,2.55,p.fabric,gx,.18,gz,.1);
 bistro(parent,p,terrace-zoneW*.3,south-.25);
 colliders.push(canopyTree(parent,p,terrace-zoneW*.36,south-2.8,1.12),canopyTree(parent,p,terrace+zoneW*.36,south-2.8,1.08));
 herbPlanter(parent,p,terrace,south+3.25,Math.min(zoneW-2,7));
 sign(parent,'BİTKİ BAHÇESİ',terrace,1.2,south+3.27,2.6);
 // A green welcome corner beside the restroom entrance, clear of the doorway.
 plant(parent,p,wc+2.8,south-1.6,1.5);herbPlanter(parent,p,wc-1.3,south+3.6,3.2);
 return colliders;
}
