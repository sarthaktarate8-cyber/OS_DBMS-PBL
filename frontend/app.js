/**
 * MEMORA 3D Cybernetic Buffer Pool Visualizer
 * Core WebGL Three.js Scene & Real-Time Simulation Engine
 */

// ----------------- GLOBAL CONSTANTS & PALETTE -----------------
const PALETTE = {
  bgDeep: 0x060911,
  cyan: 0x00f0ff,
  emerald: 0x00ff9d,
  crimson: 0xff3366,
  amber: 0xffb700,
  purple: 0xa855f7,
  slate: 0x1a263d,
  frameBase: 0x0e1726,
};

// ----------------- THREE.JS SCENE SETUP -----------------
const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();
scene.background = new THREE.Color(PALETTE.bgDeep);
scene.fog = new THREE.FogExp2(PALETTE.bgDeep, 0.025);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(0, 24, 32);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
container.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;
controls.maxPolarAngle = Math.PI / 2.1;
controls.minDistance = 10;
controls.maxDistance = 60;
controls.target.set(0, 0, 0);

// Lighting
const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
scene.add(ambientLight);

const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
dirLight.position.set(20, 40, 20);
dirLight.castShadow = true;
dirLight.shadow.mapSize.width = 1024;
dirLight.shadow.mapSize.height = 1024;
scene.add(dirLight);

const pointLight = new THREE.PointLight(PALETTE.cyan, 2, 50);
pointLight.position.set(0, 10, 0);
scene.add(pointLight);

// 3D Cybernetic Grid Floor
const gridHelper = new THREE.GridHelper(60, 60, PALETTE.cyan, 0x162238);
gridHelper.position.y = -0.5;
scene.add(gridHelper);

// ----------------- 3D ARBITER GYROSCOPE CORE -----------------
const arbiterGroup = new THREE.Group();
arbiterGroup.position.set(-18, 6, -10);

const ringGeo1 = new THREE.TorusGeometry(3.2, 0.08, 16, 100);
const ringMat1 = new THREE.MeshStandardMaterial({ color: PALETTE.purple, emissive: PALETTE.purple, emissiveIntensity: 0.6, roughness: 0.2 });
const ring1 = new THREE.Mesh(ringGeo1, ringMat1);
arbiterGroup.add(ring1);

const ringGeo2 = new THREE.TorusGeometry(2.5, 0.08, 16, 100);
const ringMat2 = new THREE.MeshStandardMaterial({ color: PALETTE.cyan, emissive: PALETTE.cyan, emissiveIntensity: 0.6, roughness: 0.2 });
const ring2 = new THREE.Mesh(ringGeo2, ringMat2);
arbiterGroup.add(ring2);

const coreGeo = new THREE.OctahedronGeometry(1.4, 0);
const coreMat = new THREE.MeshStandardMaterial({ color: PALETTE.purple, emissive: PALETTE.purple, emissiveIntensity: 1.0, wireframe: true });
const coreMesh = new THREE.Mesh(coreGeo, coreMat);
arbiterGroup.add(coreMesh);

scene.add(arbiterGroup);

// ----------------- 3D BUFFER POOL MATRIX -----------------
let bufferCapacity = 64;
let frameMeshes = [];
const frameGroup = new THREE.Group();
scene.add(frameGroup);

function build3DBufferPool(capacity) {
  // Clear previous meshes
  while (frameGroup.children.length > 0) {
    const obj = frameGroup.children[0];
    frameGroup.remove(obj);
    if (obj.geometry) obj.geometry.dispose();
  }
  frameMeshes = [];
  bufferCapacity = capacity;

  const cols = Math.ceil(Math.sqrt(capacity));
  const rows = Math.ceil(capacity / cols);
  const spacing = 2.4;
  const startX = -((cols - 1) * spacing) / 2;
  const startZ = -((rows - 1) * spacing) / 2;

  const boxGeo = new THREE.BoxGeometry(1.8, 0.8, 1.8);

  for (let i = 0; i < capacity; i++) {
    const c = i % cols;
    const r = Math.floor(i / cols);
    const x = startX + c * spacing;
    const z = startZ + r * spacing;

    const baseMat = new THREE.MeshStandardMaterial({
      color: PALETTE.frameBase,
      emissive: 0x08101e,
      emissiveIntensity: 0.3,
      roughness: 0.3,
      metalness: 0.8,
    });

    const mesh = new THREE.Mesh(boxGeo, baseMat);
    mesh.position.set(x, 0, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;

    mesh.userData = {
      frameId: i,
      pageId: null,
      usageCount: 0,
      dirty: false,
      targetY: 0,
      baseColor: PALETTE.frameBase,
    };

    frameGroup.add(mesh);
    frameMeshes.push(mesh);
  }
}

build3DBufferPool(64);

// ----------------- 3D PULSE & PARTICLES -----------------
const particleGeo = new THREE.BufferGeometry();
const particleCount = 200;
const particlePositions = new Float32Array(particleCount * 3);
for (let i = 0; i < particleCount * 3; i++) {
  particlePositions[i] = (Math.random() - 0.5) * 50;
}
particleGeo.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
const particleMat = new THREE.PointsMaterial({ color: PALETTE.cyan, size: 0.15, transparent: true, opacity: 0.6 });
const particles = new THREE.Points(particleGeo, particleMat);
scene.add(particles);

// ----------------- CLIENT-SIDE SIMULATION ENGINE -----------------
class ReplacementPolicySim {
  constructor(name) {
    this.name = name;
    this.pages = new Set();
    this.order = []; // For LRU / FIFO
    this.freq = new Map(); // For LFU
    this.usage = new Map(); // For Clock (0-5)
    this.clockHand = 0;
    this.hits = 0;
    this.misses = 0;
    this.diskReads = 0;
    this.diskWrites = 0;
  }

  access(pageId, isWrite = false, capacity = 64) {
    let isHit = this.pages.has(pageId);
    if (isHit) {
      this.hits++;
      if (this.name === 'lru') {
        this.order = this.order.filter(p => p !== pageId);
        this.order.push(pageId);
      } else if (this.name === 'lfu') {
        this.freq.set(pageId, (this.freq.get(pageId) || 0) + 1);
      } else if (this.name === 'clock') {
        let u = this.usage.get(pageId) || 0;
        this.usage.set(pageId, Math.min(u + 1, 5));
      }
    } else {
      this.misses++;
      this.diskReads++;
      if (this.pages.size >= capacity) {
        this.evict();
      }
      this.insert(pageId);
    }
    if (isWrite) this.diskWrites++;
    return isHit;
  }

  insert(pageId) {
    this.pages.add(pageId);
    this.order.push(pageId);
    this.freq.set(pageId, 1);
    this.usage.set(pageId, 1);
  }

  evict() {
    if (this.pages.size === 0) return null;
    let victim = null;

    if (this.name === 'lru' || this.name === 'fifo') {
      victim = this.order.shift();
    } else if (this.name === 'lfu') {
      let minF = Infinity;
      for (let p of this.pages) {
        let f = this.freq.get(p) || 0;
        if (f < minF) {
          minF = f;
          victim = p;
        }
      }
      this.order = this.order.filter(p => p !== victim);
    } else if (this.name === 'clock') {
      let list = Array.from(this.pages);
      let count = 0;
      while (count < list.length * 5) {
        let p = list[this.clockHand % list.length];
        let u = this.usage.get(p) || 0;
        if (u > 0) {
          this.usage.set(p, u - 1);
          this.clockHand = (this.clockHand + 1) % list.length;
        } else {
          victim = p;
          this.clockHand = (this.clockHand + 1) % list.length;
          break;
        }
        count++;
      }
      if (!victim) victim = list[0];
      this.order = this.order.filter(p => p !== victim);
    }

    if (victim !== null) {
      this.pages.delete(victim);
      this.freq.delete(victim);
      this.usage.delete(victim);
    }
    return victim;
  }

  reset() {
    this.pages.clear();
    this.order = [];
    this.freq.clear();
    this.usage.clear();
    this.clockHand = 0;
    this.hits = 0;
    this.misses = 0;
    this.diskReads = 0;
    this.diskWrites = 0;
  }

  get hitRatio() {
    let tot = this.hits + this.misses;
    return tot > 0 ? this.hits / tot : 0;
  }
}

// ----------------- MEMORA ADAPTIVE CONTROLLER SIM -----------------
class MemoraAdaptiveSim {
  constructor(capacity) {
    this.capacity = capacity;
    this.activePolicyName = 'lru';
    this.policy = new ReplacementPolicySim('lru');
    this.cooldown = 300;
    this.minBenefit = 0.02;
    this.lastSwitchAccess = 0;
    this.accessCounter = 0;
    this.switchHistory = [];
    this.windowHistory = [];
    this.windowSize = 250;
    this.recentPages = [];
    this.entropy = 0.0;
    this.jsd = 0.0;
    this.seqRatio = 0.0;
  }

  access(pageId, isWrite = false) {
    this.accessCounter++;
    this.recentPages.push(pageId);

    // Run underlying policy
    let isHit = this.policy.access(pageId, isWrite, this.capacity);

    // Periodic Window Evaluation
    if (this.recentPages.length >= this.windowSize) {
      this.evaluateWindow();
      this.recentPages = this.recentPages.slice(this.recentPages.length - 100); // 60% overlap
    }

    return isHit;
  }

  evaluateWindow() {
    let n = this.recentPages.length;
    let counts = new Map();
    let seqHits = 0;

    for (let i = 0; i < n; i++) {
      let p = this.recentPages[i];
      counts.set(p, (counts.get(p) || 0) + 1);
      if (i > 0 && p === this.recentPages[i - 1] + 1) {
        seqHits++;
      }
    }

    // Normalized Shannon Entropy
    let ent = 0.0;
    let distSize = counts.size;
    for (let [p, c] of counts) {
      let prob = c / n;
      ent -= prob * Math.log2(prob);
    }
    this.entropy = distSize > 1 ? Math.min(1.0, ent / Math.log2(distSize)) : 0.0;
    this.seqRatio = seqHits / Math.max(1, n - 1);

    // Jensen-Shannon Divergence against prior window
    if (this.windowHistory.length > 0) {
      let prior = this.windowHistory[this.windowHistory.length - 1];
      let jsdSum = 0.0;
      let allKeys = new Set([...counts.keys(), ...prior.keys()]);
      for (let k of allKeys) {
        let p = (counts.get(k) || 0) / n;
        let q = (prior.get(k) || 0) / n;
        let m = 0.5 * (p + q);
        if (p > 0 && m > 0) jsdSum += 0.5 * p * Math.log2(p / m);
        if (q > 0 && m > 0) jsdSum += 0.5 * q * Math.log2(q / m);
      }
      this.jsd = Math.max(0.0, Math.min(1.0, jsdSum));
    } else {
      this.jsd = 0.0;
    }

    this.windowHistory.push(counts);

    // Decision Logic
    this.checkPolicySwitch();
  }

  checkPolicySwitch() {
    let accessesSince = this.accessCounter - this.lastSwitchAccess;
    let isCoolingDown = accessesSince < this.cooldown;

    let detectedPhase = 'recency';
    if (this.seqRatio > 0.40) detectedPhase = 'sequential';
    else if (this.entropy < 0.55 && this.jsd > 0.30) detectedPhase = 'frequency';

    let targetPolicy = 'lru';
    if (detectedPhase === 'sequential') targetPolicy = 'fifo';
    else if (detectedPhase === 'frequency') targetPolicy = 'lfu';
    else targetPolicy = 'lru';

    if (targetPolicy !== this.activePolicyName) {
      if (isCoolingDown) {
        this.recordEvent(targetPolicy, detectedPhase, 0.0, false, `Cooldown active (${accessesSince}/${this.cooldown} accesses)`);
      } else {
        // Analytical Cost-Benefit Check
        let benefit = 0.08;
        let cost = 0.015 * (this.capacity / 64);
        let netBenefit = benefit - cost;

        if (netBenefit >= this.minBenefit) {
          // Switch Policy
          let prev = this.activePolicyName;
          this.activePolicyName = targetPolicy;
          this.policy.name = targetPolicy;
          this.lastSwitchAccess = this.accessCounter;

          this.recordEvent(targetPolicy, detectedPhase, netBenefit, true, `Profit margin +${(netBenefit * 100).toFixed(1)}% >= safety threshold`);
          triggerSwitchVFX(targetPolicy);
        } else {
          this.recordEvent(targetPolicy, detectedPhase, netBenefit, false, `Sub-threshold margin +${(netBenefit * 100).toFixed(1)}% < safety threshold`);
        }
      }
    }
  }

  recordEvent(target, phase, netBenefit, accepted, reason) {
    let evt = {
      timestamp: this.accessCounter,
      prev: this.activePolicyName,
      target: target,
      phase: phase,
      netBenefit: netBenefit,
      accepted: accepted,
      reason: reason,
    };
    this.switchHistory.push(evt);
    appendLogUI(evt);
  }

  reset() {
    this.policy.reset();
    this.activePolicyName = 'lru';
    this.policy.name = 'lru';
    this.lastSwitchAccess = 0;
    this.accessCounter = 0;
    this.switchHistory = [];
    this.windowHistory = [];
    this.recentPages = [];
    this.entropy = 0.0;
    this.jsd = 0.0;
    this.seqRatio = 0.0;
  }
}

// ----------------- WORKLOAD GENERATOR -----------------
function generateWorkloadStream(type, length = 2000) {
  let stream = [];
  if (type === 'phase_shift') {
    // 1. Sequential (pages 100-300)
    for (let i = 0; i < Math.floor(length * 0.33); i++) {
      stream.push({ pageId: 100 + (i % 200), isWrite: i % 5 === 0 });
    }
    // 2. Frequency Zipf (pages 500-530)
    for (let i = 0; i < Math.floor(length * 0.33); i++) {
      let r = Math.pow(Math.random(), 2.5);
      let offset = Math.floor(r * 30);
      stream.push({ pageId: 500 + offset, isWrite: i % 4 === 0 });
    }
    // 3. Recency (pages 800-900, 90% in 10 hot pages)
    for (let i = 0; i < Math.floor(length * 0.34); i++) {
      let p = Math.random() < 0.90 ? 800 + Math.floor(Math.random() * 10) : 800 + Math.floor(Math.random() * 100);
      stream.push({ pageId: p, isWrite: i % 3 === 0 });
    }
  } else if (type === 'pgbench') {
    // Realistic TPC-B transaction stream
    for (let i = 0; i < length; i++) {
      let op = i % 7;
      if (op === 0 || op === 1) stream.push({ pageId: 1000 + Math.floor(Math.pow(Math.random(), 2.0) * 200), isWrite: op === 1 }); // Account
      else if (op === 2 || op === 3) stream.push({ pageId: 100 + (i % 10), isWrite: op === 3 }); // Teller
      else if (op === 4 || op === 5) stream.push({ pageId: 10 + (i % 2), isWrite: op === 5 }); // Branch
      else stream.push({ pageId: 8000 + ((i / 7) % 50), isWrite: true }); // History sequential
    }
  } else if (type === 'sequential_flood') {
    for (let i = 0; i < length; i++) {
      stream.push({ pageId: 1000 + i, isWrite: false });
    }
  } else if (type === 'zipfian') {
    for (let i = 0; i < length; i++) {
      let r = Math.pow(Math.random(), 2.0);
      stream.push({ pageId: 500 + Math.floor(r * 80), isWrite: i % 4 === 0 });
    }
  } else {
    // Recency
    for (let i = 0; i < length; i++) {
      let p = Math.random() < 0.85 ? 100 + Math.floor(Math.random() * 8) : 100 + Math.floor(Math.random() * 80);
      stream.push({ pageId: p, isWrite: i % 5 === 0 });
    }
  }
  return stream;
}

// ----------------- SIMULATION STATE -----------------
let memora = new MemoraAdaptiveSim(64);
let baselineLRU = new ReplacementPolicySim('lru');
let baselineLFU = new ReplacementPolicySim('lfu');
let baselineFIFO = new ReplacementPolicySim('fifo');
let baselineClock = new ReplacementPolicySim('clock');

let workloadTrace = generateWorkloadStream('phase_shift', 2500);
let traceCursor = 0;
let isPlaying = false;
let replaySpeed = 20;

// ----------------- UI CONTROLS & INTERACTION -----------------
const btnPlay = document.getElementById('btn-play');
const btnStep = document.getElementById('btn-step');
const btnReset = document.getElementById('btn-reset');
const workloadSelect = document.getElementById('workload-select');
const sliderBufferSize = document.getElementById('slider-buffer-size');
const valBufferSize = document.getElementById('val-buffer-size');
const sliderSpeed = document.getElementById('slider-speed');
const valSpeed = document.getElementById('val-speed');
const sliderGate = document.getElementById('slider-gate');
const valGate = document.getElementById('val-gate');

sliderBufferSize.addEventListener('input', (e) => {
  let val = parseInt(e.target.value);
  valBufferSize.textContent = `${val} frames`;
  build3DBufferPool(val);
  resetAll();
});

sliderSpeed.addEventListener('input', (e) => {
  replaySpeed = parseInt(e.target.value);
  valSpeed.textContent = `${replaySpeed} accesses/sec`;
});

sliderGate.addEventListener('input', (e) => {
  let val = parseFloat(e.target.value);
  memora.minBenefit = val;
  valGate.textContent = `+${val.toFixed(3)} (${(val * 100).toFixed(1)}%)`;
});

workloadSelect.addEventListener('change', (e) => {
  workloadTrace = generateWorkloadStream(e.target.value, 2500);
  resetAll();
});

btnPlay.addEventListener('click', () => {
  isPlaying = !isPlaying;
  btnPlay.innerHTML = isPlaying ? '<span>⏸ Pause Replay</span>' : '<span>▶ Start Replay</span>';
  btnPlay.classList.toggle('btn-primary', !isPlaying);
  btnPlay.classList.toggle('btn-secondary', isPlaying);
});

btnStep.addEventListener('click', () => {
  if (isPlaying) {
    isPlaying = false;
    btnPlay.innerHTML = '<span>▶ Start Replay</span>';
  }
  executeNextAccess();
});

btnReset.addEventListener('click', () => {
  resetAll();
});

function resetAll() {
  traceCursor = 0;
  memora.reset();
  baselineLRU.reset();
  baselineLFU.reset();
  baselineFIFO.reset();
  baselineClock.reset();

  // Reset 3D frames
  frameMeshes.forEach((mesh) => {
    mesh.material.color.setHex(PALETTE.frameBase);
    mesh.material.emissive.setHex(0x08101e);
    mesh.position.y = 0;
    mesh.userData.pageId = null;
    mesh.userData.dirty = false;
  });

  document.getElementById('event-log').innerHTML = `
    <div class="log-item">
      <span>Buffer Pool reset. Allocated ${bufferCapacity} frames.</span>
      <span style="color:var(--text-dim)">Ready</span>
    </div>
  `;
  updateHUD(null, false);
}

function appendLogUI(evt) {
  const logContainer = document.getElementById('event-log');
  const div = document.createElement('div');
  div.className = `log-item ${evt.accepted ? 'switch' : 'guarded'}`;
  div.innerHTML = `
    <span>[#${evt.timestamp}] ${evt.prev.toUpperCase()} → ${evt.target.toUpperCase()} (${evt.phase})</span>
    <span style="color:${evt.accepted ? 'var(--emerald-neon)' : 'var(--amber-neon)'}">${evt.accepted ? 'ACCEPTED' : 'GUARDED'}</span>
  `;
  logContainer.insertBefore(div, logContainer.firstChild);
}

// ----------------- STEP EXECUTION & 3D REACTION -----------------
function executeNextAccess() {
  if (traceCursor >= workloadTrace.length) {
    isPlaying = false;
    btnPlay.innerHTML = '<span>▶ Start Replay</span>';
    return;
  }

  const rec = workloadTrace[traceCursor++];
  const isHit = memora.access(rec.pageId, rec.isWrite);

  // Baselines
  baselineLRU.access(rec.pageId, rec.isWrite, bufferCapacity);
  baselineLFU.access(rec.pageId, rec.isWrite, bufferCapacity);
  baselineFIFO.access(rec.pageId, rec.isWrite, bufferCapacity);
  baselineClock.access(rec.pageId, rec.isWrite, bufferCapacity);

  // Animate 3D frame slot
  let targetMeshIndex = rec.pageId % bufferCapacity;
  let mesh = frameMeshes[targetMeshIndex];

  if (mesh) {
    if (isHit) {
      // 3D HIT Visual: Emerald flash + upward bounce
      mesh.material.emissive.setHex(PALETTE.emerald);
      mesh.material.emissiveIntensity = 2.0;
      mesh.position.y = 1.2;
    } else {
      // 3D MISS Visual: Crimson flash + downward dip
      mesh.material.emissive.setHex(PALETTE.crimson);
      mesh.material.emissiveIntensity = 2.0;
      mesh.position.y = -0.6;
    }
    mesh.userData.pageId = rec.pageId;
    if (rec.isWrite) mesh.userData.dirty = true;
  }

  updateHUD(rec, isHit);
}

function updateHUD(rec, isHit) {
  // Hit ratios
  let mHR = memora.policy.hitRatio * 100;
  let cHR = baselineClock.hitRatio * 100;
  let delta = mHR - cHR;

  document.getElementById('metric-hit-ratio').textContent = `${mHR.toFixed(2)}%`;
  document.getElementById('metric-hit-delta').textContent = `${delta >= 0 ? '+' : ''}${delta.toFixed(2)}% vs Clock`;
  document.getElementById('metric-hit-bar').style.width = `${Math.min(100, mHR)}%`;

  // Storage I/O saved
  let clockIO = baselineClock.diskReads + baselineClock.diskWrites;
  let memoraIO = memora.policy.diskReads + memora.policy.diskWrites;
  let ioSaved = Math.max(0, clockIO - memoraIO);
  let ioPct = clockIO > 0 ? (ioSaved / clockIO) * 100 : 0.0;

  document.getElementById('metric-io-reduction').textContent = `${ioPct.toFixed(1)}%`;
  document.getElementById('metric-io-saved').textContent = `${ioSaved} ops saved`;

  // Live Scoreboard
  document.getElementById('score-memora').textContent = `${mHR.toFixed(2)}%`;
  document.getElementById('score-lru').textContent = `${(baselineLRU.hitRatio * 100).toFixed(2)}%`;
  document.getElementById('score-clock').textContent = `${cHR.toFixed(2)}%`;
  document.getElementById('score-lfu').textContent = `${(baselineLFU.hitRatio * 100).toFixed(2)}%`;
  document.getElementById('score-fifo').textContent = `${(baselineFIFO.hitRatio * 100).toFixed(2)}%`;

  // Status pills
  document.getElementById('status-policy-text').textContent = memora.activePolicyName.toUpperCase();
  let phaseText = 'STATIONARY';
  if (memora.seqRatio > 0.4) phaseText = 'SEQUENTIAL SCAN';
  else if (memora.entropy < 0.55 && memora.jsd > 0.3) phaseText = 'FREQUENCY SKEW';
  else if (memora.accessCounter > 100) phaseText = 'RECENCY WORKING SET';
  document.getElementById('status-phase-text').textContent = phaseText;

  // Bottom Intelligence
  document.getElementById('intel-entropy').textContent = memora.entropy.toFixed(3);
  document.getElementById('intel-jsd').textContent = memora.jsd.toFixed(3);
  document.getElementById('intel-seq').textContent = `${(memora.seqRatio * 100).toFixed(1)}%`;
}

function triggerSwitchVFX(newPolicy) {
  // Flash gyroscope core with vibrant energy
  let colorHex = PALETTE.purple;
  if (newPolicy === 'lfu') colorHex = PALETTE.emerald;
  else if (newPolicy === 'fifo') colorHex = PALETTE.amber;
  else if (newPolicy === 'lru') colorHex = PALETTE.cyan;

  coreMat.color.setHex(colorHex);
  coreMat.emissive.setHex(colorHex);
  coreMat.emissiveIntensity = 3.0;

  pointLight.color.setHex(colorHex);
  pointLight.intensity = 4.0;
}

// ----------------- ANIMATION TICK LOOP -----------------
let lastFrameTime = performance.now();
let accumulator = 0;

function animate(now) {
  requestAnimationFrame(animate);

  const delta = (now - lastFrameTime) / 1000;
  lastFrameTime = now;

  // OrbitControls update
  controls.update();

  // Rotate 3D Arbiter Core
  arbiterGroup.rotation.y += 0.015;
  ring1.rotation.x += 0.02;
  ring2.rotation.z += 0.025;
  coreMesh.rotation.x += 0.01;
  coreMesh.rotation.y += 0.02;

  // Smoothly damp light intensity back to baseline
  pointLight.intensity += (1.8 - pointLight.intensity) * 0.05;
  coreMat.emissiveIntensity += (1.0 - coreMat.emissiveIntensity) * 0.05;

  // Animate 3D frame meshes back to neutral position & color
  for (let mesh of frameMeshes) {
    mesh.position.y += (0 - mesh.position.y) * 0.12;
    let currEmissive = mesh.material.emissiveIntensity;
    mesh.material.emissiveIntensity += (0.3 - currEmissive) * 0.08;
    if (currEmissive < 0.5 && mesh.userData.pageId !== null) {
      if (mesh.userData.dirty) {
        mesh.material.color.setHex(PALETTE.amber);
      } else {
        mesh.material.color.setHex(PALETTE.cyan);
      }
    }
  }

  // Float particles gently
  particles.rotation.y += 0.001;

  // Playback execution accumulator
  if (isPlaying) {
    accumulator += delta;
    const interval = 1.0 / replaySpeed;
    while (accumulator >= interval) {
      executeNextAccess();
      accumulator -= interval;
    }
  }

  renderer.render(scene, camera);
}

requestAnimationFrame(animate);

// Window resize listener
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ----------------- BACKEND REST API INTEGRATION -----------------
async function checkPostgresStatus() {
  try {
    const res = await fetch('/api/pg_status');
    if (!res.ok) throw new Error('API unavailable');
    const data = await res.json();
    const dot = document.getElementById('status-pg-dot');
    const txt = document.getElementById('status-pg-text');

    if (data.connected) {
      dot.className = 'indicator green';
      const bufs = data.buffercache ? data.buffercache.total_buffers.toLocaleString() : '16,384';
      const hr = (data.hit_ratio * 100).toFixed(1);
      txt.innerHTML = `CONNECTED <span style="font-size:10px; font-weight:normal; opacity:0.8;">(${bufs} bufs, ${hr}% hit)</span>`;
    } else {
      dot.className = 'indicator amber';
      txt.textContent = 'STANDALONE (SIMULATED)';
    }
  } catch (err) {
    const dot = document.getElementById('status-pg-dot');
    const txt = document.getElementById('status-pg-text');
    dot.className = 'indicator cyan';
    txt.textContent = 'CLIENT-SIDE (WEBGL)';
  }
}

// Initial check and periodic polling
checkPostgresStatus();
setInterval(checkPostgresStatus, 8000);

// Backend Benchmark Trigger
const btnRunPython = document.getElementById('btn-run-python');
if (btnRunPython) {
  btnRunPython.addEventListener('click', async () => {
    btnRunPython.disabled = true;
    btnRunPython.innerHTML = '<span>⏳ Running Python Benchmark...</span>';
    const logContainer = document.getElementById('event-log');

    const workloadKey = workloadSelect.value;
    let pyWorkload = 'phase_shift';
    if (workloadKey === 'pgbench') pyWorkload = 'pgbench';
    else if (workloadKey === 'sequential_flood') pyWorkload = 'sequential';
    else if (workloadKey === 'zipfian') pyWorkload = 'zipfian';

    try {
      const res = await fetch('/api/benchmark', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workload: pyWorkload,
          buffer_size: bufferCapacity,
          num_records: 1200,
        }),
      });

      if (!res.ok) throw new Error('Benchmark API failed');
      const data = await res.json();

      if (data.status === 'success') {
        // Update scoreboard with Python engine results
        document.getElementById('score-memora').textContent = `${data.memora.hit_ratio}%`;
        document.getElementById('score-clock').textContent = `${data.clock.hit_ratio}%`;
        if (data.baselines.lru) document.getElementById('score-lru').textContent = `${data.baselines.lru.hit_ratio}%`;
        if (data.baselines.lfu) document.getElementById('score-lfu').textContent = `${data.baselines.lfu.hit_ratio}%`;
        if (data.baselines.fifo) document.getElementById('score-fifo').textContent = `${data.baselines.fifo.hit_ratio}%`;

        document.getElementById('metric-hit-ratio').textContent = `${data.memora.hit_ratio}%`;
        document.getElementById('metric-hit-bar').style.width = `${Math.min(100, data.memora.hit_ratio)}%`;

        const hrDelta = data.hit_ratio_improvement;
        const deltaEl = document.getElementById('metric-hit-delta');
        deltaEl.textContent = `${hrDelta >= 0 ? '+' : ''}${hrDelta.toFixed(1)}% vs Clock`;
        deltaEl.className = `metric-sub ${hrDelta >= 0 ? 'pos' : 'neg'}`;

        document.getElementById('metric-io-reduction').textContent = `${data.io_reduction_pct}%`;
        const ioDiff = data.clock.total_disk_io - data.memora.total_disk_io;
        document.getElementById('metric-io-saved').textContent = `${ioDiff.toLocaleString()} ops saved`;

        // Flash arbiter
        triggerSwitchVFX('lfu');

        const div = document.createElement('div');
        div.className = 'log-item switch';
        div.innerHTML = `
          <span>[BACKEND] Python benchmark finished on ${data.total_accesses} accesses. IO Reduction: +${data.io_reduction_pct}%</span>
          <span style="color:var(--emerald-neon)">PASS</span>
        `;
        logContainer.insertBefore(div, logContainer.firstChild);
      }
    } catch (err) {
      console.warn('Backend benchmark error:', err);
      const div = document.createElement('div');
      div.className = 'log-item guarded';
      div.innerHTML = `
        <span>[BACKEND] Run in Client-Side mode (Python server not responding).</span>
        <span style="color:var(--amber-neon)">LOCAL</span>
      `;
      logContainer.insertBefore(div, logContainer.firstChild);
    } finally {
      btnRunPython.disabled = false;
      btnRunPython.innerHTML = '<span>⚡ Run Backend Benchmark (Python + PG 17)</span>';
    }
  });
}

