import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';
import { clone as cloneSkeleton } from 'three/addons/utils/SkeletonUtils.js';

const STATUS_COLORS = { good: 0x7dc99e, waiting: 0xe0b56b, problem: 0xe7817c, unknown: 0x8292a9 };
const COLS = 8;
const ROOM_W = 7.7;
const ROOM_D = 6.9;
const COL_STEP = 9.8;
const ROW_STEP = 9.0;

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
    this.scene.background = new THREE.Color(0x0d1723);
    this.scene.fog = new THREE.Fog(0x0d1723, 120, 230);
    this.camera = new THREE.PerspectiveCamera(43, 1, .1, 250);
    this.camera.position.set(42, 49, 53);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.8));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.5;
    container.append(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
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
    this.scene.add(new THREE.HemisphereLight(0xc8e1ff, 0x324153, 3.3));
    const sun = new THREE.DirectionalLight(0xffe1ad, 3.7);
    sun.position.set(-18, 45, 18); this.scene.add(sun);
    const rim = new THREE.DirectionalLight(0x80b7ff, 1.5);
    rim.position.set(25, 22, -20); this.scene.add(rim);
    this.rooms = new THREE.Group(); this.scene.add(this.rooms);
    this.clickables = [];
    this.memberObjects = new Map();
    this.roomObjects = new Map();
    this.roomStripes = new Map();
    this.people = [];
    this.visuals = new Map();
    this.liveMarkers = new Map();
    this.monitors = new Map();
    this.colliders = [];
    this.detailed = [];
    this.characterTemplate = null;
    this.characterAnimations = [];
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.overlay = document.getElementById('sceneOverlay');
    this.labels = new Map();
    this.raycaster = new THREE.Raycaster();
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
    const w = Math.max(1, this.container.clientWidth), h = Math.max(1, this.container.clientHeight);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix(); this.renderer.setSize(w, h, false);
    if (!this.hasResized) { this.hasResized = true; this.resetCamera(); }
  }

  animate() {
    if (!this.running) return;
    requestAnimationFrame(() => this.animate());
    const frame = performance.now();
    const delta = Math.min((frame - this.lastFrame) / 1000, .06);
    this.lastFrame = frame;
    if (this.walking) this.moveWalker(delta);
    else this.controls.update();
    for (const item of this.detailed) item.mixer.update(delta);
    if (!this.reducedMotion) {
      const now = performance.now() * .001;
      for (const person of this.people) {
        if (!person.body.visible) continue;
        const movement = Math.sin(now * 1.5 + person.phase) * .018;
        person.body.position.y = person.bodyY + movement;
        person.head.position.y = person.headY + movement;
      }
      this.liveMarkers.forEach((ring) => {
        if (ring.visible) ring.scale.setScalar(1 + Math.sin(now * 3) * .13);
      });
    }
    this.renderer.render(this.scene, this.camera);
    this.positionLabels();
  }

  positionLabels() {
    if (!this.overlay) return;
    const width = this.container.clientWidth, height = this.container.clientHeight;
    for (const [code, label] of this.labels) {
      const room = this.roomObjects.get(code);
      if (!room) continue;
      const position = new THREE.Vector3(room.position.x, 1.2, room.position.z - 2.15).project(this.camera);
      label.style.left = `${(position.x + 1) * width / 2}px`;
      label.style.top = `${(1 - position.y) * height / 2}px`;
      label.hidden = position.z > 1 || position.x < -1.1 || position.x > 1.1 || position.y < -1.1 || position.y > 1.1;
    }
  }

  handleClick(event) {
    if (this.walking) return;
    if (!this.mouseDown || Math.hypot(event.clientX - this.mouseDown[0], event.clientY - this.mouseDown[1]) > 5) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObjects(this.clickables, false)[0];
    if (hit) this.onSelect(hit.object.userData.department, hit.object.userData.member || null);
  }

  resetCamera() {
    if (this.walking) this.walkControls.unlock();
    if (this.container.clientWidth < 700) this.camera.position.set(102, 118, 137);
    else this.camera.position.set(57, 68, 78);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  focus(code) {
    if (this.walking) { this.showDetailedDepartment(code); return; }
    const target = this.roomObjects.get(code)?.position;
    if (!target) return;
    const offset = new THREE.Vector3(13, 17, 20);
    this.controls.target.copy(target);
    this.camera.position.copy(target).add(offset);
    this.controls.update();
    this.showDetailedDepartment(code);
  }

  startWalk(code) {
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
    if (forward) this.walkControls.moveForward(forward * speed * delta);
    if (sideways) this.walkControls.moveRight(sideways * speed * delta);
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
    if (hit && hit.distance < 12) this.onSelect(hit.object.userData.department, hit.object.userData.member || null);
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
    this.rooms.clear(); this.clickables = []; this.memberObjects.clear(); this.roomObjects.clear(); this.roomStripes.clear(); this.people = []; this.visuals.clear(); this.liveMarkers.clear(); this.monitors.clear(); this.colliders = [];
    this.characterTemplate = null; this.characterAnimations = [];
    this.overlay?.replaceChildren(); this.labels.clear();
  }

  renderDepartments(departments) {
    this.clear();
    const columns = Math.min(COLS, Math.max(1, Math.ceil(Math.sqrt(departments.length * 1.5))));
    const rows = Math.ceil(departments.length / columns);
    const width = columns * COL_STEP + 5, depth = rows * ROW_STEP + 13;
    this.floorBounds = { halfW: width / 2 - 1, minZ: -depth / 2 - 4.2, maxZ: depth / 2 - 4.2 };
    const floor = new THREE.Mesh(new THREE.BoxGeometry(width, .36, depth), mat(0x192332));
    floor.position.set(0, -.28, -4.2); this.rooms.add(floor);
    const floorEdge = new THREE.Mesh(new THREE.BoxGeometry(width + .3, .17, depth + .3), mat(0xb3905b, { metalness: .5 }));
    floorEdge.position.set(0, -.54, -4.2); this.rooms.add(floorEdge);

    const pathMaterial = mat(0x314254, { metalness: .18 });
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

    departments.forEach((d, i) => {
      const col = i % columns, row = Math.floor(i / columns);
      const x = (col - (columns - 1) / 2) * COL_STEP;
      const z = (row - (rows - 1) / 2) * ROW_STEP + 1.6;
      this.makeRoom(d, x, z);
      if (this.overlay) {
        const label = document.createElement('button');
        label.className = 'scene-label'; label.type = 'button';
        label.title = `${d.ad || d.kod} · ${d.kadro?.length || 0} kişi`;
        const name = document.createElement('strong'); name.textContent = d.kod;
        label.append(name);
        label.addEventListener('click', (event) => { event.stopPropagation(); this.onSelect(d.kod, null); });
        this.overlay.append(label); this.labels.set(d.kod, label);
      }
    });

    // The source project's office is used as a small reception and leadership suite.
    // The procedural department floor accommodates Jarvis's complete roster.
    const loader = new GLTFLoader();
    const draco = new DRACOLoader();
    draco.setDecoderPath('/office/draco/');
    draco.setDecoderConfig({ type: 'js' });
    loader.setDRACOLoader(draco);
    loader.load('/office/office.glb', (gltf) => {
      const model = gltf.scene;
      model.scale.setScalar(.75);
      model.position.set(0, .04, -((rows - 1) / 2) * ROW_STEP - 8.5);
      model.traverse((o) => {
        if (!o.isMesh) return;
        if (o.name.toLowerCase().includes('navmesh')) o.visible = false;
        else if (!o.material?.map && o.material?.color) o.material.color.set(0x8d9ba8);
      });
      this.rooms.add(model);
    }, undefined, () => { /* The complete roster floor remains available. */ });

    loader.load('/office/character.glb', (gltf) => {
      this.characterTemplate = gltf.scene;
      this.characterAnimations = gltf.animations;
      if (this.selectedDepartment) this.showDetailedDepartment(this.selectedDepartment);
    }, undefined, () => { /* Low-poly colleagues remain interactive. */ });
  }

  makeRoom(department, x, z) {
    const group = new THREE.Group(); group.position.set(x, 0, z); this.rooms.add(group);
    this.roomObjects.set(department.kod, group);
    const status = departmentStatus(department);
    const accent = STATUS_COLORS[status];
    const base = new THREE.Mesh(new THREE.BoxGeometry(ROOM_W - .32, .22, ROOM_D - .34), mat(0x26374a));
    base.position.y = .03; group.add(base);
    const carpet = new THREE.Mesh(new THREE.PlaneGeometry(ROOM_W - .65, ROOM_D - .67), mat(0x263c4a, { side: THREE.DoubleSide }));
    carpet.rotation.x = -Math.PI / 2; carpet.position.y = .17; group.add(carpet);
    const north = new THREE.Mesh(new THREE.BoxGeometry(ROOM_W - .34, .46, .12), mat(0x4d6072));
    north.position.set(0, .38, -ROOM_D / 2 + .2); group.add(north);
    this.colliders.push({ minX: x - ROOM_W / 2 - .1, maxX: x + ROOM_W / 2 + .1,
      minZ: z - ROOM_D / 2 - .25, maxZ: z - ROOM_D / 2 + .5 });
    const west = new THREE.Mesh(new THREE.BoxGeometry(.12, .46, ROOM_D - .35), mat(0x4d6072));
    west.position.set(-ROOM_W / 2 + .2, .38, 0); group.add(west);
    this.colliders.push({ minX: x - ROOM_W / 2 - .25, maxX: x - ROOM_W / 2 + .5,
      minZ: z - ROOM_D / 2, maxZ: z + ROOM_D / 2 });
    const glass = new THREE.Mesh(new THREE.BoxGeometry(ROOM_W - .5, 1.24, .06), new THREE.MeshPhysicalMaterial({ color: 0x8fb2c4, transparent: true, opacity: .14, roughness: .08, metalness: .25, side: THREE.DoubleSide, depthWrite: false }));
    glass.position.set(0, .96, -ROOM_D / 2 + .2); group.add(glass);
    const wallTrim = new THREE.Mesh(new THREE.BoxGeometry(ROOM_W - .5, .05, .08), mat(0xb99c65, { metalness: .55 }));
    wallTrim.position.set(0, 1.62, -ROOM_D / 2 + .2); group.add(wallTrim);
    const stripe = new THREE.Mesh(new THREE.BoxGeometry(ROOM_W - .38, .11, .15), mat(accent, { emissive: accent, emissiveIntensity: .23 }));
    stripe.position.set(0, .25, ROOM_D / 2 - .24); group.add(stripe);
    this.roomStripes.set(department.kod, stripe);
    const plantPot = new THREE.Mesh(new THREE.CylinderGeometry(.19, .23, .32, 10), mat(0x8b715d));
    plantPot.position.set(ROOM_W / 2 - .68, .32, -ROOM_D / 2 + .75); group.add(plantPot);
    const plant = new THREE.Mesh(new THREE.DodecahedronGeometry(.48, 1), mat(0x497b67));
    plant.position.set(ROOM_W / 2 - .68, .76, -ROOM_D / 2 + .75); group.add(plant);
    const hitbox = new THREE.Mesh(new THREE.BoxGeometry(ROOM_W - .34, .12, ROOM_D - .34), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }));
    hitbox.position.y = .22; hitbox.userData.department = department.kod; group.add(hitbox); this.clickables.push(hitbox);
    const members = department.kadro || [];
    const cols = 4;
    members.forEach((person, i) => {
      const px = (i % cols - 1.5) * 1.36;
      const pz = Math.floor(i / cols) * 1.05 - .08;
      const py = person.sorumlu_mu ? .58 : .49;
      const color = person.sorumlu_mu ? 0xe2b768 : STATUS_COLORS[statusKind(person.status)];
      const desk = new THREE.Mesh(new THREE.BoxGeometry(1.08, .12, .62), mat(0x708090));
      desk.position.set(px, .43, pz + .25); group.add(desk);
      this.colliders.push({ minX: x + px - .77, maxX: x + px + .77,
        minZ: z + pz - .18, maxZ: z + pz + .68 });
      const stand = new THREE.Mesh(new THREE.CylinderGeometry(.15, .15, .4, 8), mat(0x344759));
      stand.position.set(px, .25, pz + .25); group.add(stand);
      const monitor = new THREE.Mesh(new THREE.BoxGeometry(.42, .26, .055), mat(0x1c3542, { emissive: 0x336d82, emissiveIntensity: .25 }));
      monitor.position.set(px, .67, pz + .13); group.add(monitor); this.monitors.set(person.key, monitor);
      const monitorStand = new THREE.Mesh(new THREE.BoxGeometry(.05, .1, .08), mat(0x8b9ca9));
      monitorStand.position.set(px, .51, pz + .13); group.add(monitorStand);
      const chair = new THREE.Mesh(new THREE.BoxGeometry(.46, .11, .43), mat(0x3d4f60));
      chair.position.set(px, .28, pz - .42); group.add(chair);
      const chairBack = new THREE.Mesh(new THREE.BoxGeometry(.46, .5, .09), mat(0x3d4f60));
      chairBack.position.set(px, .52, pz - .66); group.add(chairBack);
      const body = new THREE.Mesh(new THREE.CylinderGeometry(.24, .28, person.sorumlu_mu ? .66 : .53, 12), mat(color, { emissive: color, emissiveIntensity: .1 }));
      body.position.set(px, py, pz - .38); body.userData = { department: department.kod, member: person.key };
      group.add(body); this.clickables.push(body); this.memberObjects.set(person.key, body);
      const head = new THREE.Mesh(new THREE.SphereGeometry(.21, 12, 9), mat(person.sorumlu_mu ? 0xf5d4a4 : 0xc2d5e6));
      head.position.set(px, py + (person.sorumlu_mu ? .44 : .36), pz - .38); group.add(head);
      const personHitbox = new THREE.Mesh(new THREE.CylinderGeometry(.35, .35, 1.4, 8), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }));
      personHitbox.position.set(px, .85, pz - .38);
      personHitbox.userData = { department: department.kod, member: person.key };
      group.add(personHitbox); this.clickables.push(personHitbox);
      this.people.push({ body, head, bodyY: body.position.y, headY: head.position.y, phase: i * 1.31 + x * .17 + z * .11 });
      this.visuals.set(person.key, { body, head, group, x: px, z: pz - .38, department: department.kod });
      const liveRing = new THREE.Mesh(new THREE.TorusGeometry(.45, .045, 6, 24), mat(0x73d5b3, { emissive: 0x73d5b3, emissiveIntensity: .6 }));
      liveRing.rotation.x = Math.PI / 2; liveRing.position.set(px, .22, pz - .38); liveRing.visible = false;
      group.add(liveRing); this.liveMarkers.set(person.key, liveRing);
      if (person.sorumlu_mu) {
        const ring = new THREE.Mesh(new THREE.TorusGeometry(.35, .045, 6, 20), mat(0xe2b768, { emissive: 0xc49c50, emissiveIntensity: .3 }));
        ring.rotation.x = Math.PI / 2; ring.position.set(px, .22, pz - .38); group.add(ring);
      }
    });
  }

  selectMember(key) {
    this.memberObjects.forEach((mesh, memberKey) => { mesh.scale.setScalar(memberKey === key ? 1.36 : 1); });
  }

  clearDetailed() {
    for (const item of this.detailed) {
      item.mixer.stopAllAction();
      item.visual.group.remove(item.model);
      item.visual.body.visible = true;
      item.visual.head.visible = true;
    }
    this.detailed = [];
  }

  showDetailedDepartment(code) {
    if (this.selectedDepartment === code && this.detailed.length) return;
    this.clearDetailed();
    this.selectedDepartment = code;
    if (!this.characterTemplate) return;
    const visuals = [...this.visuals.values()].filter((visual) => visual.department === code);
    for (const visual of visuals) {
      const model = cloneSkeleton(this.characterTemplate);
      const height = new THREE.Box3().setFromObject(model).getSize(new THREE.Vector3()).y || 1.8;
      model.scale.setScalar(1.15 / height);
      model.position.set(visual.x, .18, visual.z);
      model.rotation.y = Math.PI;
      visual.group.add(model);
      visual.body.visible = false; visual.head.visible = false;
      const mixer = new THREE.AnimationMixer(model);
      const clip = this.characterAnimations.find((animation) => animation.name === 'Sit_Work')
        || this.characterAnimations.find((animation) => animation.name === 'Idle');
      if (clip) mixer.clipAction(clip).play();
      this.detailed.push({ model, mixer, visual });
    }
  }

  updateStatuses(departments) {
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
          avatar.material.color.setHex(color); avatar.material.emissive.setHex(color);
        }
      }
    }
  }

  updateLive(active) {
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
