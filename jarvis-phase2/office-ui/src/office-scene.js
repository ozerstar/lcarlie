import {canopyTree,herbPlanter} from './green-spaces.js';
import {DEFAULT_VIEW,departmentsForView,viewTitle} from './office-views.js';
import { brandFor,brandPlaque,brandRug,featherFlag,managerSuite,buildRetail } from './brand-spaces.js';
import { RoomWorkspace } from './room-workspace.js';
import { familyName } from './labels.js';
import * as THREE from 'three';
import { OfficeLife } from './office-life.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { palette,box,cylinder,plant,sign,desk,avatar,batchStatic,material,sofa,meetingTable,artwork,pendant } from './office-assets.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { SSAOPass } from 'three/addons/postprocessing/SSAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';

const STATUS_COLORS = { good: 0x7dc99e, waiting: 0xe0b56b, problem: 0xe7817c, unknown: 0x8292a9 };
const COLS = 8;
const MAX_VISIBLE_MEMBERS = 17;
const ROOM_W = 12;
const ROOM_D = 11.6;
const COL_STEP = 14;
const ROW_STEP = 13.5;

function statusKind(value) {
  const s = String(value || '').toLocaleUpperCase('tr-TR');
  if (s === 'KONUŞTU') return 'good';
  if (s === 'VERİ YOK' || s === 'İŞLEM HATASI' || s === 'İŞLEV YAZILMADI') return 'problem';
  if (s === 'GİRDİ BEKLER' || s === 'ARAŞTIRMA GEREKİR') return 'waiting';
  return 'unknown';
}

function mat(color, options = {}) { return new THREE.MeshStandardMaterial({ color, roughness: .82, metalness: .08, ...options }); }

export class OfficeScene {
  constructor(container, onSelect, onWalkChange = () => {}) {
    this.container = container;
    this.onSelect = onSelect;
    this.onWalkChange = onWalkChange;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xd9ddd9);
    this.scene.fog = new THREE.Fog(0xd9ddd9, 120, 230);
    this.camera = new THREE.PerspectiveCamera(38, 1, .1, 250);
    this.camera.position.set(42, 49, 53);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.lowQuality=window.innerWidth<750;this.quality='auto';this.renderer.setPixelRatio(this.lowQuality?1:Math.min(window.devicePixelRatio || 1, 1.25));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.08;
    this.renderer.shadowMap.enabled = !this.lowQuality;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.append(this.renderer.domElement);
    const environment=new RoomEnvironment();const pmrem=new THREE.PMREMGenerator(this.renderer);this.environmentMap=pmrem.fromScene(environment,.04);this.scene.environment=this.environmentMap.texture;this.scene.environmentIntensity=.45;environment.dispose();pmrem.dispose();
    this.composer=new EffectComposer(this.renderer);this.composer.addPass(new RenderPass(this.scene,this.camera));this.ao=new SSAOPass(this.scene,this.camera,512,512,16);this.ao.kernelRadius=.65;this.ao.minDistance=.0005;this.ao.maxDistance=.018;this.composer.addPass(this.ao);this.composer.addPass(new OutputPass());
    this.viewKey=DEFAULT_VIEW;
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.needsRender=true;this.controls.addEventListener("change",()=>{this.needsRender=true;});
    this.controls.dampingFactor = .085;
    this.controls.minDistance = 12;
    this.controls.maxDistance = 125;
    this.controls.maxPolarAngle = Math.PI / 2.18;
    this.controls.target.set(0, 0, 0);
    this.controls.update();
    this.walkControls = new PointerLockControls(this.camera, this.renderer.domElement);
    this.walkKeys = new Set();
    this.walking = false;
    this.walkControls.addEventListener('lock', () => {
      this.walking = true; this.controls.enabled = false; this.onWalkChange(true);
    });
    this.walkControls.addEventListener('unlock', () => {
      this.walking = false; this.controls.enabled = true; this.walkKeys.clear();
      if (this.beforeWalk) {
        this.camera.position.copy(this.beforeWalk.position);
        this.controls.target.copy(this.beforeWalk.target);
        this.controls.update();
      }
      this.onWalkChange(false);
    });
    window.addEventListener('keydown', (event) => {
      if (!this.walking) return;
      if (['KeyW','KeyA','KeyS','KeyD','ShiftLeft','ShiftRight'].includes(event.code)) {
        this.walkKeys.add(event.code); event.preventDefault();
      }
      if (event.code === 'KeyE') { this.selectCenter(); event.preventDefault(); }
    });
    window.addEventListener('keyup', (event) => this.walkKeys.delete(event.code));
    this.ambient=new THREE.HemisphereLight(0xe7ecf2, 0x70766b, 1.35);this.scene.add(this.ambient);
    const sun = this.sun = new THREE.DirectionalLight(0xffe4c5, 2.65);
    sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);sun.shadow.bias=-.0004;sun.shadow.normalBias=.04;
    Object.assign(sun.shadow.camera,{left:-65,right:65,top:65,bottom:-65,near:1,far:180});
    sun.position.set(-22, 35, 18); this.scene.add(sun);
    const rim = this.rim = new THREE.DirectionalLight(0xb4d9e5, .7);
    rim.position.set(25, 22, -20); this.scene.add(rim);
    this.rooms = new THREE.Group(); this.scene.add(this.rooms);
    this.clickables = [];
    this.memberObjects = new Map();
    this.roomObjects = new Map();
    this.roomStripes = new Map();
    this.people = []; this.workspaces = new Map();
    this.visuals = new Map();
    this.liveMarkers = new Map();
    this.monitors = new Map();
    this.colliders = [];
    this.detailed = [];
    this.characterTemplate = null;
    this.characterAnimations = [];
    this.motionPreference=window.matchMedia('(prefers-reduced-motion: reduce)');
    this.reducedMotion=this.motionPreference.matches;
    this.motionPreference.addEventListener('change',e=>{this.reducedMotion=e.matches;this.setOfficeLife(this.lifeRequested);});
    this.overlay = document.getElementById('sceneOverlay');
    this.labels = new Map();
    this.raycaster = new THREE.Raycaster();this.raycaster.layers.enable(1);
    this.pointer = new THREE.Vector2();
    this.mouseDown = null;
    this.renderer.domElement.addEventListener('pointerdown', (e) => { this.mouseDown = [e.clientX, e.clientY]; });
    this.renderer.domElement.addEventListener('pointerup', (e) => this.handleClick(e));
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
    this.running = true;
    this.lastFrame = performance.now();
    this.animate();
  }

  resize() {
    if(this.quality==='auto'){const low=window.innerWidth<750;if(low!==this.lowQuality){this.lowQuality=low;this.renderer.setPixelRatio(low?1:Math.min(window.devicePixelRatio||1,1.25));this.renderer.shadowMap.enabled=!low;}}
    this.container.dataset.quality=this.lowQuality?'low':'high';
    const w = Math.max(1, this.container.clientWidth), h = Math.max(1, this.container.clientHeight);
    this.needsRender=true;
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix(); this.renderer.setSize(w, h, false);this.composer?.setSize(w,h);
    if (!this.hasResized) { this.hasResized = true; this.resetCamera(); }
  }

  animate() {
    if (!this.running) return;
    requestAnimationFrame(() => this.animate());
    if(document.hidden||this.suspended){this.lastFrame=performance.now();return;}
    const frame = performance.now();
    const delta = Math.min((frame - this.lastFrame) / 1000, .06);
    this.lastFrame = frame;
    this.camera.updateMatrixWorld();this.animFrustum ||= new THREE.Frustum();this.animFrustum.setFromProjectionMatrix(new THREE.Matrix4().multiplyMatrices(this.camera.projectionMatrix,this.camera.matrixWorldInverse));
    const close=o=>{if(!o)return false;const point=o.getWorldPosition(new THREE.Vector3());return this.animFrustum.containsPoint(point)&&this.camera.position.distanceTo(point)<(this.lowQuality?25:42);};
    if (this.walking) this.moveWalker(delta);
    else this.controls.update();
    let activeAnimation=false;
    if (!this.reducedMotion && !document.hidden) {
      for (const item of this.detailed) item.mixer.update(delta);
      if(this.officeLife&&this.animFrustum.containsPoint(new THREE.Vector3(0,1,this.officeLife.south))&&this.camera.position.distanceTo(new THREE.Vector3(0,1,this.officeLife.south))<50){this.officeLife.update(delta);activeAnimation=true;}
      this.workspaces.forEach(w=>{if(close(w.group)){w.update(delta,Boolean(this.lifeRequested));if(w.mode!=='rest')activeAnimation=true;}});
      if(this.lifeRequested)for(const flag of this.flags||[]){if(!close(flag))continue;activeAnimation=true;const pos=flag.geometry.attributes.position,base=flag.userData.waveBase;for(let i=0;i<pos.count;i++)pos.setZ(i,base[i*3+2]+Math.sin(frame*.0018+base[i*3+1]*2)*.045*base[i*3]);pos.needsUpdate=true;flag.geometry.computeVertexNormals();}
    }
    if (!this.reducedMotion && !document.hidden && this.lifeRequested) {
      const now = performance.now() * .001;
      for (const person of this.people) {
        if (!person.rig.visible || !close(person.group)) continue;activeAnimation=true;
        person.head.rotation.y = Math.sin(now*.55+person.phase)*.065;
        person.head.rotation.x = .08+Math.sin(now*.9+person.phase)*.025;
        person.arms.forEach((arm,i)=>{arm.rotation.x=-.45+Math.sin(now*5+person.phase+i)*.025;});
      }
      this.liveMarkers.forEach((ring) => {
        if (ring.visible) ring.scale.setScalar(1 + Math.sin(now * 3) * .13);
      });
    }
    const moving=this.lifeRequested&&!this.reducedMotion&&activeAnimation;
    if(!this.needsRender&&!moving&&!this.walking)return;
    if(frame-(this.lastRendered||0)<(this.lowQuality?50:33))return;this.lastRendered=frame;this.needsRender=false;
    if(!this.lowQuality&&this.visibleCount<=8&&this.container.clientWidth>650)this.composer.render();else this.renderer.render(this.scene,this.camera);
    this.positionLabels();
  }

  positionLabels() {
    if (!this.overlay) return;
    const canvas = this.renderer.domElement.getBoundingClientRect(), overlay = this.overlay.getBoundingClientRect();
    const width = canvas.width, height = canvas.height;
    const occupied=[];
    const ordered=[...this.labels].sort(([a],[b])=>a===this.selectedDepartment?-1:b===this.selectedDepartment?1:0);
    for (const [code, label] of ordered) {
      const room = this.roomObjects.get(code);
      if (!room) continue;
      const position = room.localToWorld(new THREE.Vector3(0, 2.85, -ROOM_D/2+.4)).project(this.camera);
      label.style.left = `${canvas.left-overlay.left+(position.x + 1) * width / 2}px`;
      label.style.top = `${canvas.top-overlay.top+(1 - position.y) * height / 2}px`;
      const x=(position.x+1)*width/2, y=(1-position.y)*height/2;
      label.classList.add('wide');const lw=154,lh=label.offsetHeight||52;const rect={x:x-lw/2,y:y-lh/2,w:lw,h:lh+8};
      const collision=occupied.some(r=>rect.x<r.x+r.w && rect.x+rect.w>r.x && rect.y<r.y+r.h && rect.y+rect.h>r.y);
      label.hidden = collision || position.z > 1 || position.z < -1 || position.x < -.95 || position.x > .95 || position.y < -.95 || position.y > .95;
      if(!label.hidden)occupied.push(rect);
    }
  }

  handleClick(event) {
    if (this.walking) return;
    if (!this.mouseDown || Math.hypot(event.clientX - this.mouseDown[0], event.clientY - this.mouseDown[1]) > 5) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObjects(this.clickables, false)[0];
    if (hit?.object.userData.product){this.onProductSelect?.(hit.object.userData.product);return;}
    if (hit) {this.onSelect(hit.object.userData.department, hit.object.userData.member || null);if(hit.object.userData.usage)this.onFurnitureUse?.(hit.object.userData.department,hit.object.userData.usage); }
  }

  setOfficeLife(enabled) {
    this.needsRender=true;
    this.lifeRequested=Boolean(enabled);
    this.lifeEnabled = this.lifeRequested && !this.reducedMotion;
    this.officeLife?.setEnabled(this.lifeEnabled);
    this.workspaces.forEach(w=>w.update(0,this.lifeEnabled));
  }

  resetCamera() {
    if (this.walking) this.walkControls.unlock();
    const radius = this.mapRadius || 62;
    const fov = THREE.MathUtils.degToRad(this.camera.fov / 2);
    const angle = Math.min(fov, Math.atan(Math.tan(fov) * this.camera.aspect));
    const distance = radius / Math.sin(angle) * 1.08;
    this.controls.maxDistance = Math.max(125, distance * 1.5);
    this.camera.far = Math.max(250, distance + radius * 3);
    this.camera.updateProjectionMatrix();
    this.camera.position.copy(new THREE.Vector3(.55,.8,.75).normalize().multiplyScalar(distance));
    this.scene.fog.near = distance + radius;
    this.scene.fog.far = distance + radius * 3;
    this.controls.target.set(0, 0, this.floorBounds ? 2.85+(this.floorBounds.maxZ-this.floorBounds.minZ)*.1 : 2.85);
    const direction = new THREE.Vector3(this.visibleCount<=8?.65:.55,this.visibleCount<=8?.62:.8,1).normalize();
    if (this.floorBounds) {
      const corners=[];
      for (const x of [-this.floorBounds.halfW-1,this.floorBounds.halfW+1])
        for(const z of [this.floorBounds.minZ-1,this.floorBounds.maxZ+1])
          for(const y of [0,3])corners.push(new THREE.Vector3(x,y,z));
      let low=10, high=distance;
      for(let i=0;i<24;i++){
        const mid=(low+high)/2;
        this.camera.position.copy(this.controls.target).addScaledVector(direction,mid);
        this.camera.lookAt(this.controls.target);this.camera.updateMatrixWorld();
        const fits=corners.every(c=>{const p=c.clone().project(this.camera);return Math.abs(p.x)<.9 && Math.abs(p.y)<.85 && p.z<1;});
        if(fits)high=mid;else low=mid;
      }
      this.camera.position.copy(this.controls.target).addScaledVector(direction,high*(this.visibleCount<=8?.88:1));
    }
    this.controls.update();
  }

  focus(code) {
    this.ensureDepartment(code);
    if (this.walking) { this.showDetailedDepartment(code); return; }
    const target = this.roomObjects.get(code)?.position;
    if (!target) return;
    const offset = new THREE.Vector3(9, 10, 13);
    this.controls.target.copy(target);
    this.camera.position.copy(target).add(offset);
    this.controls.update();
    this.showDetailedDepartment(code);
  }

  startWalk(code) {
    if(code)this.ensureDepartment(code);
    if (this.walking) return;
    this.beforeWalk = { position: this.camera.position.clone(), target: this.controls.target.clone() };
    const room = this.roomObjects.get(code);
    if (room) {
      this.camera.position.set(room.position.x, 1.75, room.position.z + 3.4);
      this.camera.lookAt(room.position.x, 1.4, room.position.z - 2);
      this.showDetailedDepartment(code);
    } else {
      this.camera.position.set(0, 1.75, this.floorBounds?.maxZ - 3 || 15);
      this.camera.lookAt(0, 1.5, 0);
    }
    this.walkControls.lock();
  }

  stopWalk() { if (this.walking) this.walkControls.unlock(); }

  moveWalker(delta) {
    const speed = this.walkKeys.has('ShiftLeft') || this.walkKeys.has('ShiftRight') ? 9 : 5.2;
    const forward = Number(this.walkKeys.has('KeyW')) - Number(this.walkKeys.has('KeyS'));
    const sideways = Number(this.walkKeys.has('KeyD')) - Number(this.walkKeys.has('KeyA'));
    const oldX = this.camera.position.x, oldZ = this.camera.position.z;
    const normalized=1/Math.max(1,Math.hypot(forward,sideways));
    if (forward) this.walkControls.moveForward(forward * speed * delta * normalized);
    if (sideways) this.walkControls.moveRight(sideways * speed * delta * normalized);
    this.camera.position.y = 1.75;
    if (this.floorBounds) {
      this.camera.position.x = THREE.MathUtils.clamp(this.camera.position.x, -this.floorBounds.halfW, this.floorBounds.halfW);
      this.camera.position.z = THREE.MathUtils.clamp(this.camera.position.z, this.floorBounds.minZ, this.floorBounds.maxZ);
    }
    if (this.colliders.some((box) => this.camera.position.x > box.minX && this.camera.position.x < box.maxX
        && this.camera.position.z > box.minZ && this.camera.position.z < box.maxZ)) {
      this.camera.position.x = oldX; this.camera.position.z = oldZ;
    }
  }

  selectCenter() {
    this.raycaster.setFromCamera(new THREE.Vector2(0, 0), this.camera);
    const hit = this.raycaster.intersectObjects(this.clickables, false)[0];
    if (hit && hit.distance < 12){if(hit.object.userData.product)this.onProductSelect?.(hit.object.userData.product);else if(hit.object.userData.usage==='board')this.onFurnitureUse?.(hit.object.userData.department,'board');else this.onSelect(hit.object.userData.department, hit.object.userData.member || null);}
  }

  clear() {
    this.clearDetailed();
    this.rooms.traverse((node) => {
      if (node.geometry) node.geometry.dispose();
      if (node.material) {
        for (const m of Array.isArray(node.material) ? node.material : [node.material]) {
          if (m.map) m.map.dispose();
          m.dispose();
        }
      }
    });
    this.rooms.clear(); this.workspaces.clear(); this.officeLife=null; this.flags=[]; this.roomLights=[]; this.clickables = []; this.memberObjects.clear(); this.roomObjects.clear(); this.roomStripes.clear(); this.people = []; this.visuals.clear(); this.liveMarkers.clear(); this.monitors.clear(); this.colliders = [];
    this.characterTemplate = null; this.characterAnimations = [];
    this.overlay?.replaceChildren(); this.labels.clear();
  }

  renderDepartments(departments) {
    this.needsRender=true;
    this.allDepartments=departments;
    this.buildView();
  }
  setView(key){this.viewKey=key;this.buildView();}
  ensureDepartment(code){
    if(this.roomObjects.has(code))return;
    const department=this.allDepartments?.find(d=>d.kod===code);
    if(department){this.viewKey='family:'+department.aile;this.buildView();}
  }
  buildView(){
    if(this.walking)this.stopWalk();
    if(this.viewKey==='showcase'){this.buildRetailView();return;}
    const departments=departmentsForView(this.allDepartments||[],this.viewKey);
    this.visibleCount=departments.length;
    const select=document.getElementById('floorSelect');if(select)select.value=this.viewKey;
    const title=viewTitle(this.viewKey);
    document.getElementById('sceneTitle').textContent=title;
    document.getElementById('sceneSubtitle').textContent=departments.length+' birim · birime tıklayarak ekibi inceleyin';
    const context=document.getElementById('floorContext');if(context)context.textContent=title+' · '+departments.length+' birim görünümde';
    this.clear();
    const columns = Math.min(COLS, Math.max(2, Math.ceil(Math.sqrt(departments.length))));
    const rows = Math.ceil(departments.length / columns);
    const width = columns * COL_STEP + 5, depth = (rows-1) * ROW_STEP + ROOM_D + 20.5;
    this.palette=palette();
    const half=Math.max(width,depth)*.65;Object.assign(this.sun.shadow.camera,{left:-half,right:half,top:half,bottom:-half});this.sun.shadow.camera.updateProjectionMatrix();
    this.mapRadius = Math.hypot(width, depth) / 2;
    this.floorBounds = { halfW: width / 2 - 1, minZ: -depth / 2 + 2.85, maxZ: depth / 2 + 2.85 };
    const floor = new THREE.Mesh(new THREE.BoxGeometry(width, .36, depth), this.palette.stone);
    floor.position.set(0, -.28, 2.85);floor.receiveShadow=true; this.rooms.add(floor);
    const floorEdge = new THREE.Mesh(new THREE.BoxGeometry(width + .3, .17, depth + .3), this.palette.dark);
    floorEdge.position.set(0, -.54, 2.85); this.rooms.add(floorEdge);

    const pathMaterial = this.palette.ivory;
    for (let row = 0; row < rows - 1; row++) {
      const corridor = new THREE.Mesh(new THREE.BoxGeometry(width - 1.5, .015, ROW_STEP - ROOM_D - .28), pathMaterial);
      corridor.position.set(0, .005, (row - (rows - 1) / 2) * ROW_STEP + 1.6 + ROW_STEP / 2);
      this.rooms.add(corridor);
    }
    for (let col = 0; col < columns - 1; col++) {
      const corridor = new THREE.Mesh(new THREE.BoxGeometry(COL_STEP - ROOM_W - .28, .015, rows * ROW_STEP + 1), pathMaterial);
      corridor.position.set((col - (columns - 1) / 2) * COL_STEP + COL_STEP / 2, .008, 1.6);
      this.rooms.add(corridor);
    }

    this.officeLife = new OfficeLife(this.rooms, width, this.floorBounds.maxZ - 4.6, this.palette);
    this.officeLife.setEnabled(Boolean(this.lifeEnabled));
    this.colliders.push(...this.officeLife.colliders);
    departments.forEach((d, i) => {
      const col = i % columns, row = Math.floor(i / columns);
      const x = (col - (columns - 1) / 2) * COL_STEP;
      const z = (row - (rows - 1) / 2) * ROW_STEP + 1.6;
      this.makeRoom(d, x, z);
      if (this.overlay) {
        const label = document.createElement('button');
        label.className = 'scene-label'; label.type = 'button';
        label.title = `${d.ad || d.kod} · ${d.kadro?.length || 0} kişi`;
        const name = document.createElement('strong'); name.textContent = d.ad || 'Birim adı tanımlanmamış';
        const count=document.createElement('small');count.textContent = d.kadro.length > MAX_VISIBLE_MEMBERS ? `${MAX_VISIBLE_MEMBERS} / ${d.kadro.length} sahnede` : `${d.kadro.length} üye`;
        label.append(name,count);
        label.addEventListener('click', (event) => { event.stopPropagation(); this.onSelect(d.kod, null); });
        this.overlay.append(label); this.labels.set(d.kod, label);
      }
    });

    // Reception is original procedural geometry; no external model download is needed.
    const receptionZ=-((rows-1)/2)*ROW_STEP-6.8;
    box(this.rooms,12,.18,5,this.palette.wood,0,.02,receptionZ);
    box(this.rooms,5,1.05,.8,this.palette.ivory,0,.65,receptionZ);
    box(this.rooms,5.3,.08,1,this.palette.wood,0,1.2,receptionZ);
    brandPlaque(this.rooms,this.palette,'lcarlie',0,1.9,receptionZ+.46,5.6);
    brandRug(this.rooms,this.palette,'lcarlie',0,receptionZ+1.7,5.8,2);
    this.flags.push(featherFlag(this.rooms,this.palette,'lcarlie',-5.3,receptionZ+1));
    plant(this.rooms,this.palette,-4.3,receptionZ,1.7);plant(this.rooms,this.palette,4.3,receptionZ,1.7);
    // The architectural shell ties the rooms into one continuous workplace.
    const backZ=this.floorBounds.minZ+.8;
    box(this.rooms,width-2,2.9,.22,this.palette.ivory,0,1.34,backZ);
    for(let i=0;i<Math.floor(width/2);i++){const x=-width/2+1.8+i*2;box(this.rooms,1.75,2,.05,this.palette.glass,x,1.7,backZ+.14);box(this.rooms,.035,2.4,.07,this.palette.metal,x-.9,1.55,backZ+.18);}
    const ground=new THREE.Mesh(new THREE.PlaneGeometry(width*5,depth*5),material(0xc9ceca,{roughness:1}));ground.rotation.x=-Math.PI/2;ground.position.y=-.67;ground.receiveShadow=true;this.ground=ground;this.rooms.add(ground);
    // Green borders sit outside the working aisles and preserve the full-floor view.
    for(const side of [-1,1])for(let zi=0;zi<rows;zi+=2){const tz=(zi-(rows-1)/2)*ROW_STEP+1.6;this.colliders.push(canopyTree(this.rooms,this.palette,side*(width/2-1.15),tz,.72));}
    herbPlanter(this.rooms,this.palette,0,receptionZ-1.25,7);
    batchStatic(this.rooms);
    this.resetCamera();
    this.updateLive(this.activeMembers||{});
    this.setLighting(this.lightMode||'day');
  }

  makeRoom(department, x, z) {
    const group=new THREE.Group();group.position.set(x,0,z);this.rooms.add(group);this.roomObjects.set(department.kod,group);
    const p=this.palette,accent=STATUS_COLORS[departmentStatus(department)];
    if(this.visibleCount<=8){const light=new THREE.PointLight(0xffce91,1,12,2);light.position.set(0,2.65,0);group.add(light);this.roomLights.push(light);}
    box(group,ROOM_W-.25,.23,ROOM_D-.25,p.ivory,0,.02,0,.05);
    const familyHash=[...(department.aile||'')].reduce((n,c)=>n+c.charCodeAt(0),0);
    const carpet=p.carpet.clone();carpet.color.setHex([0xd2d8ce,0xc4d1cc,0xd8d0bf,0xc6cbd2][familyHash%4]);
    box(group,ROOM_W-.65,.035,ROOM_D-.65,carpet,0,.16,0);
    // Three-quarter-height cutaway walls keep desks visible without losing architecture.
    box(group,ROOM_W-.3,2.6,.18,p.ivory,0,1.44,-ROOM_D/2+.18);
    box(group,ROOM_W-.35,.07,.26,p.dark,0,2.77,-ROOM_D/2+.18);
    box(group,.1,1.8,ROOM_D-.3,p.glass,-ROOM_W/2+.16,1.18,0);
    for(const dz of [-ROOM_D/2+.2,-.8,ROOM_D/2-.2])box(group,.05,2.55,.05,p.metal,-ROOM_W/2+.16,1.45,dz);
    box(group,.05,.045,ROOM_D-.3,p.metal,-ROOM_W/2+.16,2.75,0);
    // Individual glass executive suite, original brand identity and work zones.
    const executiveSeat=managerSuite(group,p,department),brand=brandFor(department);
    brandRug(group,p,brand,3.1,4.35,3.6,1.8);
    if(brand!=='lcarlie')this.flags.push(featherFlag(group,p,brand,5.1,2.8));
    this.colliders.push({minX:x-2.45,maxX:x-2.3,minZ:z-5.65,maxZ:z-1.88},{minX:x-5.7,maxX:x-3.5,minZ:z-1.99,maxZ:z-1.85});
    // The digital planning board replaces the decorative rear picture.
    pendant(group,p,-1,-.6,2.7);
    this.colliders.push({minX:x-ROOM_W/2,maxX:x+ROOM_W/2,minZ:z-ROOM_D/2-.15,maxZ:z-ROOM_D/2+.35});
    this.colliders.push({minX:x-ROOM_W/2-.15,maxX:x-ROOM_W/2+.35,minZ:z-ROOM_D/2,maxZ:z+ROOM_D/2});
    const stripe=box(group,1.6,.07,.09,material(accent,{emissive:accent,emissiveIntensity:.15}),0,.25,ROOM_D/2-.13);stripe.userData.static=false;this.roomStripes.set(department.kod,stripe);
    plant(group,p,ROOM_W/2-.65,-ROOM_D/2+.8,1.1);
    brandPlaque(group,p,brand,2.55,2.3,-5.5,1.45);
    const hitbox=new THREE.Mesh(new THREE.BoxGeometry(ROOM_W-.2,.1,ROOM_D-.2),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false}));hitbox.layers.set(1);hitbox.position.y=.2;hitbox.userData.department=department.kod;group.add(hitbox);this.clickables.push(hitbox);
    const members=department.kadro||[],cols=members.length<=8?2:4,count=Math.min(members.length,MAX_VISIBLE_MEMBERS),rows=Math.ceil(count/cols);
    if(count<=8){meetingTable(group,p,2.8,.8);sofa(group,p,2.8,3.25,Math.PI);plant(group,p,5,-2.2,1.35);box(group,3,.018,1.6,p.fabric,2.8,.19,3.2,.08); }
    if(count>8)pendant(group,p,2,1.7,2.7);
    if(department.kod==='PRODUCT'){for(let i=0;i<7;i++){cylinder(group,.065,.24+i%3*.05,i%2?p.ivory:p.clay,-3.4+i*.18,1.13,-3.8);}}
    const workspace=new RoomWorkspace(group,p,department,count>8);this.workspaces.set(department.kod,workspace);if(this.operations)workspace.setWork(this.operations.items.filter(i=>i.department===department.kod));this.clickables.push(...workspace.hits);
    let staffIndex=0;
    members.slice(0,MAX_VISIBLE_MEMBERS).forEach((person,i)=>{
      const j=person.sorumlu_mu?0:staffIndex++,r=Math.floor(j/cols);
      const px=person.sorumlu_mu?executiveSeat.x:count<=8?[-3.7,-1.8][j%2]:[-3.65,-1.75,.15,2.05][j%4];
      const pz=person.sorumlu_mu?executiveSeat.z:count<=8?-.2+r*1.5:-.7+r*(count>18?.85:1.3);
      const reverse=false;
      const furniture=desk(group,p,px,pz);if(reverse){furniture.group.rotation.y=Math.PI;furniture.chairZ=pz+.67;}this.monitors.set(person.key,furniture.screen);
      this.colliders.push({minX:x+px-.78,maxX:x+px+.78,minZ:z+pz-.4,maxZ:z+pz+.45});
      const human=avatar(i+familyHash,true,Boolean(person.sorumlu_mu));human.group.position.set(px,.14,furniture.chairZ);if(reverse)human.group.rotation.y=Math.PI;group.add(human.group);
      human.body.userData={department:department.kod,member:person.key};this.memberObjects.set(person.key,human.body);this.people.push({...human,phase:i*1.31+x*.17+z*.11});
      const personHitbox=new THREE.Mesh(new THREE.BoxGeometry(.65,1.6,.6),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false}));personHitbox.layers.set(1);personHitbox.position.set(px,.95,furniture.chairZ);personHitbox.userData={department:department.kod,member:person.key};group.add(personHitbox);this.clickables.push(personHitbox);
      const ring=new THREE.Mesh(new THREE.TorusGeometry(.36,.025,5,20),material(person.sorumlu_mu?0xd8b978:STATUS_COLORS[statusKind(person.status)]));ring.rotation.x=Math.PI/2;ring.position.set(px,.22,furniture.chairZ);group.add(ring);
      const liveRing=new THREE.Mesh(new THREE.TorusGeometry(.43,.035,5,20),material(0x73d5b3,{emissive:0x73d5b3,emissiveIntensity:.7}));liveRing.rotation.x=Math.PI/2;liveRing.position.set(px,.24,furniture.chairZ);liveRing.visible=false;group.add(liveRing);this.liveMarkers.set(person.key,liveRing);
      this.visuals.set(person.key,{...human,statusRing:ring,department:department.kod});
    });
    if(!members.length){
      // Vacant departments retain a furnished planning area, without fabricated staff.
      box(group,2.6,.09,1.25,p.wood,0,.85,.4,.06);for(const dx of [-1,1])box(group,.07,.7,.7,p.metal,dx,.45,.4);
      box(group,1.8,1.05,.06,p.ivory,0,1.45,-2.8);for(const dx of [-.65,.65])box(group,.04,1.2,.04,p.metal,dx,.7,-2.8);
      sign(group,'KADRO TANIMLI DEĞİL',0,1.5,-2.75,1.7);
    }
  }

  buildRetailView(){
    this.clear();this.visibleCount=3;this.palette=palette();this.mapRadius=25;
    this.floorBounds={halfW:20,minZ:-8,maxZ:9};
    box(this.rooms,40,.35,18,this.palette.stone,0,-.25,0);
    this.retailPlaces=buildRetail(this.rooms,this.palette,this.operations?.products||[],()=>this.needsRender=true);
    this.rooms.traverse(n=>{if(n.userData.product)this.clickables.push(n);});
    this.rooms.traverse(n=>{if(n.userData.flag)this.flags.push(n);});
    const ground=new THREE.Mesh(new THREE.PlaneGeometry(150,150),material(0xc9ceca));ground.rotation.x=-Math.PI/2;ground.position.y=-.5;this.rooms.add(ground);this.ground=ground;
    batchStatic(this.rooms);this.resetCamera();this.setLighting(this.lightMode||'day');
    const select=document.getElementById('floorSelect');if(select)select.value='showcase';
    document.getElementById('floorContext').textContent='Ürün sergi alanı · Mağaza · Tanıtım standı';
    document.getElementById('sceneTitle').textContent='L’carlie deneyim alanları';
    document.getElementById('sceneSubtitle').textContent='Katalog fotoğrafına tıklayın: kaynaklı fiyat, stok ve maliyet kartı';
  }
  setSuspended(value){this.suspended=Boolean(value);this.needsRender=true;}
  setQuality(mode){this.quality=mode;this.lowQuality=mode==='low'||(mode==='auto'&&window.innerWidth<750);this.renderer.setPixelRatio(this.lowQuality?1:Math.min(window.devicePixelRatio||1,1.25));this.renderer.shadowMap.enabled=!this.lowQuality;this.resize();this.needsRender=true;}
  setOperations(data){this.operations=data;this.workspaces.forEach((w,code)=>w.setWork(data.items.filter(i=>i.department===code)));if(this.viewKey==='showcase'){const position=this.camera.position.clone(),target=this.controls.target.clone();this.buildRetailView();this.camera.position.copy(position);this.controls.target.copy(target);this.controls.update();}this.needsRender=true;}
  focusRetail(key){if(this.viewKey!=='showcase'){this.viewKey='showcase';this.buildView();}const place=this.retailPlaces.find(p=>p.key===key);if(!place)return;this.controls.target.set(place.x,.8,0);this.camera.position.set(place.x+9,10,15);this.controls.update();}

  useFurniture(code,mode){
    this.ensureDepartment(code);this.workspaces.forEach((w,k)=>w.start(k===code?mode:'rest'));
    this.focus(code);this.workspaces.get(code)?.update(0,this.lifeEnabled);
  }

  selectMember(key) {
    this.visuals.forEach((visual,memberKey)=>visual.statusRing.scale.setScalar(memberKey===key?1.35:1));
  }

  clearDetailed() { this.detailed=[]; }
  showDetailedDepartment(code) { this.selectedDepartment=code; }
  focusLounge(zone=null){
    if(!this.officeLife){this.viewKey="center";this.buildView();}
    if(this.walking)this.stopWalk();
    const z=this.officeLife?.south||0;
    const x=zone===null?0:this.officeLife.locations[zone];
    this.controls.target.set(x,.7,z);this.camera.position.set(x+8,zone===null?27:9,z+(zone===null?37:13));this.controls.update();
  }
  setLighting(mode){
    this.needsRender=true;
    this.lightMode=mode;const night=mode==='night';this.ambient.intensity=night?.28:1.15;this.sun.intensity=night?.3:2.5;this.scene.environmentIntensity=night?.15:.4;
    this.roomLights?.forEach(light=>light.intensity=night?20:1);this.ground?.material.color.setHex(night?0x283542:0xc9ceca);
    if(this.palette)this.palette.lamp.emissiveIntensity=night?3:1;
    this.rim.intensity=night?1.1:.7;this.sun.color.setHex(night?0xffb67c:0xffead0);
    this.renderer.toneMappingExposure=night?1.1:1.0;this.scene.background.setHex(night?0x111c25:0xd9ddd9);
    this.scene.fog.color.copy(this.scene.background);
  }

  updateStatuses(departments) {
    this.allDepartments=departments;
    for (const d of departments) {
      const stripe = this.roomStripes.get(d.kod);
      if (stripe) {
        const color = STATUS_COLORS[departmentStatus(d)];
        stripe.material.color.setHex(color); stripe.material.emissive.setHex(color);
      }
      for (const m of d.kadro || []) {
        const avatar = this.memberObjects.get(m.key);
        if (avatar && !m.sorumlu_mu) {
          const color = STATUS_COLORS[statusKind(m.status)];
          this.visuals.get(m.key)?.statusRing.material.color.setHex(color);
        }
      }
    }
  }

  updateLive(active) {
    this.needsRender=true;
    this.activeMembers=active;
    this.liveMarkers.forEach((ring, key) => { ring.visible = Boolean(active[key]); });
    this.monitors.forEach((monitor, key) => {
      monitor.material.emissive.setHex(active[key] ? 0x55e1ad : 0x336d82);
      monitor.material.emissiveIntensity = active[key] ? .9 : .25;
    });
  }
}

export function departmentStatus(department) {
  const statuses = (department.kadro || []).map((m) => statusKind(m.status));
  if (statuses.includes('good')) return 'good';
  if (statuses.includes('problem')) return 'problem';
  if (statuses.includes('waiting')) return 'waiting';
  return 'unknown';
}

export { statusKind };
