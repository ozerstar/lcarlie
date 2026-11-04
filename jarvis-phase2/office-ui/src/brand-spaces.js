import * as THREE from 'three';
import {box,cylinder,plant,sofa,sign,material,pendant} from './office-assets.js';
const files={lcarlie:['lcarlie.png',3824/530],goril:['goril.jpg',600/191],tecdynasty:['tecdynasty.jpg',815/180]};
const textures=new Map();
function texture(brand){if(!textures.has(brand)){const t=new THREE.TextureLoader().load('/office/brands/'+files[brand][0]);t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=4;textures.set(brand,t);}return textures.get(brand);}
export function brandFor(department){return ['TASARIM','YAYIN','ART','CONTENT','COPY','CREATIVE_STRAT','UGC'].includes(department.kod)?'goril':['TEKNOLOJI','WEB','AI_OPS','SECURITY'].includes(department.kod)?'tecdynasty':'lcarlie';}
export function brandPlaque(parent,p,brand,x,y,z,width=3){const ratio=files[brand][1],h=width/ratio;box(parent,width+.18,h+.2,.055,p.ivory,x,y,z-.035,.02);const mesh=new THREE.Mesh(new THREE.PlaneGeometry(width,h),new THREE.MeshBasicMaterial({map:texture(brand),transparent:true,side:THREE.DoubleSide}));mesh.position.set(x,y,z);parent.add(mesh);return mesh;}
export function brandRug(parent,p,brand,x,z,width=3.8,depth=2){box(parent,width,.022,depth,p.fabric,x,.2,z,.1);const patch=new THREE.Mesh(new THREE.PlaneGeometry(width*.74,width*.74/files[brand][1]),new THREE.MeshBasicMaterial({map:texture(brand),transparent:true}));patch.position.set(x,.216,z);patch.rotation.x=-Math.PI/2;parent.add(patch); // logo is laid flat, with original proportions
}
export function featherFlag(parent,p,brand,x,z){
 const g=new THREE.Group();g.position.set(x,.18,z);parent.add(g);cylinder(g,.32,.08,p.metal,0,.04,0);cylinder(g,.025,3.7,p.metal,0,1.86,0);
 const shape=new THREE.Shape();shape.moveTo(.05,.5);shape.lineTo(.05,3.7);shape.bezierCurveTo(.8,3.7,1.1,3.25,1.1,2.5);shape.lineTo(.95,.65);shape.quadraticCurveTo(.4,.9,.05,.5);
 const cloth=new THREE.Mesh(new THREE.ShapeGeometry(shape,18),material(brand==='tecdynasty'?0x0c172d:0xf2efe7,{side:THREE.DoubleSide,roughness:.9}));g.add(cloth);
 const logo=new THREE.Mesh(new THREE.PlaneGeometry(.83,.83/files[brand][1]),new THREE.MeshBasicMaterial({map:texture(brand),transparent:true,side:THREE.DoubleSide}));logo.rotation.z=Math.PI/2;logo.position.set(.56,2.2,.012);g.add(logo);
 const base=cloth.geometry.attributes.position;cloth.userData.waveBase=Array.from(base.array);cloth.userData.flag=true;return cloth;
}
export function managerSuite(parent,p,department){
 const brand=brandFor(department);
 box(parent,3.3,.035,3.65,p.wood,-4.05,.19,-3.77);
 // Glass front has an actual open doorway on the right.
 box(parent,.06,2.55,3.7,p.glass,-2.38,1.48,-3.77);
 box(parent,2.15,2.55,.06,p.glass,-4.6,1.48,-1.92);
 for(const x of [-5.68,-3.52,-2.38])box(parent,.035,2.65,.06,p.metal,x,1.48,-1.92);
 box(parent,3.35,.04,.07,p.metal,-4.05,2.83,-1.92);
 box(parent,.07,.04,3.7,p.metal,-2.38,2.83,-3.77);
 brandPlaque(parent,p,brand,-4.05,2.22,-5.52,2.4);
 sign(parent,'BİRİM YÖNETİCİSİ',-4.05,1.62,-5.5,2.25);
 plant(parent,p,-5.22,-2.35,.8);
 // Visitor bench and executive desk details.
 box(parent,1.12,.17,.46,p.fabric,-4.25,.57,-2.28,.06);
 box(parent,1.12,.37,.09,p.fabric,-4.25,.78,-2.5,.04);
 return {x:-4.05,z:-3.55};
}
export function buildRetail(parent,p,items=[],onLoad=()=>{}){
 let cursor=0;const available=items.filter(i=>i.image);const textureMap=new Map();
 function products(parent,p,x,z,count=5,base=1.34){
  const amount=Math.min(count,3);if(!available.length){sign(parent,'Ürün kartları yüklenince gösterilir',x,base+.4,z+.13,1.6);return;}
  for(let i=0;i<amount;i++){
   const product=available[(cursor++)%available.length],px=x+(i-(amount-1)/2)*.58;
   box(parent,.49,.035,.28,p.ivory,px,base+.02,z);
   let texture=textureMap.get(product.id);if(!texture){texture=new THREE.TextureLoader().load(product.image,t=>{t.colorSpace=THREE.SRGBColorSpace;onLoad();},undefined,()=>onLoad());texture.colorSpace=THREE.SRGBColorSpace;textureMap.set(product.id,texture);}
   const mesh=new THREE.Mesh(new THREE.PlaneGeometry(.48,.78),new THREE.MeshBasicMaterial({map:texture,side:THREE.DoubleSide}));mesh.position.set(px,base+.44,z);mesh.userData.product=product.id;mesh.userData.static=false;parent.add(mesh);
  }
 }
 const places=[{key:'showroom',name:'Ürün sergi alanı',x:-13},{key:'store',name:'L’carlie mağazası',x:0},{key:'stand',name:'L’carlie tanıtım standı',x:13}];
 for(const a of places){
  const g=new THREE.Group();g.position.set(a.x,0,0);parent.add(g);box(g,11.7,.22,13,p.ivory,0,0,0,.05);box(g,11.2,.025,12.5,p.carpet,0,.13,0);
  box(g,11.7,3.1,.18,p.ivory,0,1.65,-6.25);for(const x of [-5.7,5.7]){box(g,.06,2.6,12.6,p.glass,x,1.5,0);box(g,.04,.05,12.6,p.brass,x,2.83,0);}
  brandPlaque(g,p,'lcarlie',0,2.65,-6.12,5.2);sign(g,a.name.toLocaleUpperCase('tr-TR'),0,1.9,-6.1,5.7);brandRug(g,p,'lcarlie',0,4.5,5.2,2.2);
  featherFlag(g,p,'lcarlie',-4.6,4.5);plant(g,p,4.6,4.7,1.7);pendant(g,p,0,-1,5);
  if(a.key==='showroom'){
   for(const [x,z,h] of [[-3,-3,1.05],[0,-2.3,.85],[3,-3,1.05],[-2,1,.9],[2,1,.9]]){box(g,2,.18,1.2,p.ivory,x,h,z,.05);box(g,1.3,h-.2,.7,p.wood,x,(h-.2)/2+.16,z);const row=new THREE.Group();row.position.set(x,h+.09,z);g.add(row);products(row,p,0,0,4,0);}
   sofa(g,p,-3.4,3.1,Math.PI);sofa(g,p,3.4,3.1,Math.PI);sign(g,'ÜRÜNLERİ KEŞFEDİN',0,1.3,-.3,3);
  }else if(a.key==='store'){
   for(const x of [-3.8,3.8])for(const z of [-3.7,-.8,2.1]){box(g,1.7,1.1,1,p.wood,x,.7,z,.035);box(g,1.85,.08,1.1,p.ivory,x,1.3,z);products(g,p,x,z,4);}
   box(g,3.2,1.05,.95,p.wood,0,.68,-4.7,.04);box(g,3.4,.08,1.1,p.ivory,0,1.25,-4.7);box(g,.43,.38,.05,p.metal,.6,1.49,-4.7);brandPlaque(g,p,'lcarlie',0,.72,-4.19,2.5);
   sign(g,'KASA VE DANIŞMA',0,1.65,-5.9,3);
  }else{
   for(const x of [-3.6,3.6])box(g,.16,3.6,.16,p.brass,x,1.95,-2.6);box(g,7.4,.65,.22,p.ivory,0,3.45,-2.6);brandPlaque(g,p,'lcarlie',0,3.46,-2.46,4.3);
   box(g,5,1.12,1.5,p.wood,0,.72,0,.12);box(g,5.2,.08,1.65,p.ivory,0,1.32,0,.07);brandPlaque(g,p,'lcarlie',0,.8,.79,3.4);products(g,p,0,0,7);
   for(const x of [-3.5,3.5]){cylinder(g,.52,.08,p.ivory,x,.91,1.8);cylinder(g,.09,.75,p.brass,x,.5,1.8);}
   sign(g,'ÜRÜN TANITIMI VE DENEYİM',0,1.2,-4.2,4.6);
  }
 }
 return places;
}
