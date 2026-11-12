// 3D-Begleiter: eigener kleiner Schwebe-Roboter (three.js r128, frontend/vendor/three).
// Aufbau: abgerundeter Würfelkopf mit Display-Gesicht (LED-Augen auf einer Canvas-Textur),
// Kopfhörer-Scheiben, federnde Antenne, kurze Arme, Rumpf und ein leuchtender Schwebering.
//
// Das Popup meldet über onPythonEvent("companion"):
//   {kind: "state", state}  idle | listening | transcribing | thinking | speaking
//   {kind: "reply" | "proactive" | "error" | "hello"}  kurze Gesten
//   {kind: "theme", accent} Akzentfarbe des Designs für Ohren, Hände und Kragen
//   {kind: "side", value}   steht links oder rechts vom Popup (Blick zum Chat geht dorthin)
//   {kind: "model", url, options}  anderes Modell (backend/companion_models.py); url "" = eingebaute Figur
// Den Mauszeiger reicht backend/desktop/companion_window.py per Companion.pointer() herein.
//
// Eigenes Modell: Mit ?model=<file-URL einer .glb/.gltf> (backend/config.py COMPANION_MODEL) ersetzt es die
// eingebaute Figur. Es wird auf Größe gebracht und bewegt sich als Ganzes (Schweben, Blick, Gesten).
// Teile mit üblichen Namen (Head/Kopf, Arm_L/Arm_R ...) bewegen sich zusätzlich einzeln; leuchtende
// Materialien (Emission oder Namen wie eye, light, glow) bekommen die Zustandsfarbe. Hat ein Material namens
// screen/display/face eine Augen-Textur, bleiben dessen Augen erhalten: eingefärbt nach Zustand, blinzeln,
// schauen umher, freuen sich (siehe modelEyes). Mitgelieferte Animationen laufen (idle bevorzugt).
//
// Sparsam: höchstens 30 Bilder pro Sekunde, kleine Fläche, nichts zeichnen, solange das Fenster
// verborgen ist. Das Gesicht wird nur neu gemalt, wenn sich daran etwas geändert hat.

const Companion = (() => {
  const FRAME_MS = 1000 / 30;
  const TAU = Math.PI * 2;
  // Farbe der Augen, Ohrringe, Antennenspitze und des Schweberings je Zustand
  const STATES = {
    idle:         {color: "#3FC4FF", label: "bereit"},
    listening:    {color: "#1FE07A", label: "hört zu"},
    transcribing: {color: "#14D6C8", label: "versteht"},
    thinking:     {color: "#FFB020", label: "denkt nach"},
    speaking:     {color: "#9573FF", label: "spricht"},
  };
  const ERROR_COLOR = "#FF4559";
  const SLEEP_AFTER_MS = 90000;   // so lange nichts los: Augen fallen halb zu

  const canvas = document.getElementById("companion-canvas");
  const renderer = new THREE.WebGLRenderer({canvas, alpha: true, antialias: true, powerPreference: "low-power"});
  renderer.setClearColor(0x000000, 0);
  renderer.outputEncoding = THREE.sRGBEncoding;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  const scene = new THREE.Scene();

  // Glanz ohne Umgebungs-Textur (PMREM läuft nicht auf jeder Grafik): Lichter von oben und der Seite
  const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 50);
  camera.position.set(0, 0.45, 9.6);
  camera.lookAt(0, 0.12, 0);

  scene.add(new THREE.HemisphereLight(0xffffff, 0x3a4256, 1.0));
  const top = new THREE.DirectionalLight(0xffffff, 0.6);   // Glanzlicht auf Kopf und Schultern
  top.position.set(-1.5, 6, 2);
  scene.add(top);
  const key = new THREE.DirectionalLight(0xffffff, 0.85);
  key.position.set(2.5, 4, 5);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x8fd8ff, 0.9);    // Kantenlicht in der Zustandsfarbe
  rim.position.set(-3, 2.5, -4);
  scene.add(rim);
  const rim2 = new THREE.DirectionalLight(0x8fd8ff, 0.5);
  rim2.position.set(3.5, 0.5, -3);
  scene.add(rim2);
  // farbiges Licht: vom Display aufs Gesicht davor und vom Schwebering auf den Rumpf
  const faceLight = new THREE.PointLight(0x8fd8ff, 0.9, 3.2, 2);
  const ringLight = new THREE.PointLight(0x8fd8ff, 1.6, 3.0, 2);
  scene.add(ringLight);

  // --- Materialien ------------------------------------------------------------------------------
  const shell = new THREE.MeshPhysicalMaterial({color: 0xf4f6fa, roughness: 0.22, metalness: 0.0,
    clearcoat: 1, clearcoatRoughness: 0.08});
  const darkShell = new THREE.MeshPhysicalMaterial({color: 0x1c2029, roughness: 0.3, metalness: 0.4,
    clearcoat: 0.6, clearcoatRoughness: 0.2});
  const accent = new THREE.MeshPhysicalMaterial({color: 0x7c83f2, roughness: 0.25, metalness: 0.3,
    clearcoat: 1, clearcoatRoughness: 0.1});
  const glow = new THREE.MeshBasicMaterial({color: 0x8fd8ff});
  const glowSoft = new THREE.MeshBasicMaterial({color: 0x8fd8ff, transparent: true, opacity: 0.35, depthWrite: false,
    blending: THREE.AdditiveBlending});

  // weicher Lichthof (Sprite, additiv) - für Augen, Antenne, Brust und Schwebering
  const haloTexture = (() => {
    const c = document.createElement("canvas");
    c.width = c.height = 128;
    const ctx = c.getContext("2d");
    const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    g.addColorStop(0, "rgba(255,255,255,0.9)");
    g.addColorStop(0.25, "rgba(255,255,255,0.35)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
  })();
  const halos = [];
  function halo(size, opacity) {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({map: haloTexture, color: 0x8fd8ff, transparent: true,
      opacity, depthWrite: false, blending: THREE.AdditiveBlending}));
    sprite.scale.set(size, size, 1);
    sprite.userData.base = opacity;
    halos.push(sprite);
    return sprite;
  }

  // --- Gesicht: Canvas-Textur -----------------------------------------------------------------
  const face = document.createElement("canvas");
  face.width = 512;
  face.height = 320;
  const faceCtx = face.getContext("2d");
  const faceTexture = new THREE.CanvasTexture(face);
  faceTexture.encoding = THREE.sRGBEncoding;
  faceTexture.anisotropy = 4;

  function roundedRect(width, height, radius) {
    const shape = new THREE.Shape();
    const x = -width / 2, y = -height / 2;
    shape.moveTo(x + radius, y);
    shape.lineTo(x + width - radius, y);
    shape.quadraticCurveTo(x + width, y, x + width, y + radius);
    shape.lineTo(x + width, y + height - radius);
    shape.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    shape.lineTo(x + radius, y + height);
    shape.quadraticCurveTo(x, y + height, x, y + height - radius);
    shape.lineTo(x, y + radius);
    shape.quadraticCurveTo(x, y, x + radius, y);
    return shape;
  }

  // UV einer ShapeGeometry auf 0..1 bringen, damit die Textur das ganze Display füllt
  function fitUv(geometry, width, height) {
    const position = geometry.attributes.position, uv = geometry.attributes.uv;
    for (let i = 0; i < position.count; i++) {
      uv.setXY(i, position.getX(i) / width + 0.5, position.getY(i) / height + 0.5);
    }
    uv.needsUpdate = true;
    return geometry;
  }

  // --- Figur ----------------------------------------------------------------------------------
  const root = new THREE.Group();          // schwebt auf und ab
  scene.add(root);
  const bodyPivot = new THREE.Group();     // Hüpfen, Drehen, Neigen des ganzen Körpers
  root.add(bodyPivot);

  // Rumpf: gedrechselte Form, oben breit, unten schmal
  const torsoCurve = new THREE.SplineCurve([
    [0.0, 0.02], [0.5, 0.02], [0.6, -0.08], [0.63, -0.3], [0.56, -0.62], [0.4, -0.9], [0.22, -1.02], [0.0, -1.05],
  ].map(([x, y]) => new THREE.Vector2(x, y)));
  const torso = new THREE.Mesh(new THREE.LatheGeometry(torsoCurve.getPoints(28), 48), shell);
  bodyPivot.add(torso);
  const collar = new THREE.Mesh(new THREE.TorusGeometry(0.5, 0.06, 12, 40), accent);
  collar.rotation.x = Math.PI / 2;
  collar.position.y = 0.0;
  bodyPivot.add(collar);
  const chest = new THREE.Mesh(new THREE.CircleGeometry(0.12, 32), glow);
  chest.position.set(0, -0.33, 0.615);
  chest.rotation.x = -0.12;
  bodyPivot.add(chest);
  const chestRing = new THREE.Mesh(new THREE.RingGeometry(0.14, 0.18, 32), darkShell);
  chestRing.position.copy(chest.position).add(new THREE.Vector3(0, 0, -0.004));
  chestRing.rotation.x = chest.rotation.x;
  bodyPivot.add(chestRing);
  const chestHalo = halo(0.75, 0.4);
  chestHalo.position.copy(chest.position).add(new THREE.Vector3(0, 0, 0.05));
  bodyPivot.add(chestHalo);

  // Arme: Schultergelenk, Oberarm und Hand; hängen in Ruhe leicht nach außen
  function makeArm(side) {
    const shoulder = new THREE.Group();
    shoulder.position.set(side * 0.64, -0.18, 0);
    const joint = new THREE.Mesh(new THREE.SphereGeometry(0.12, 20, 14), darkShell);
    shoulder.add(joint);
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.085, 0.07, 0.46, 16), shell);
    arm.position.y = -0.26;
    shoulder.add(arm);
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.13, 20, 14), accent);
    hand.position.y = -0.53;
    hand.scale.set(1, 0.9, 1);
    shoulder.add(hand);
    bodyPivot.add(shoulder);
    return shoulder;
  }
  const arms = {left: makeArm(-1), right: makeArm(1)};

  // Kopf: Nackengelenk (Drehen/Nicken) und darüber der Kopf
  const neck = new THREE.Group();
  neck.position.y = 0.16;
  bodyPivot.add(neck);
  const head = new THREE.Group();
  head.position.y = 0.66;
  neck.add(head);

  const HEAD_W = 1.72, HEAD_H = 1.24, HEAD_D = 0.82;
  const headGeometry = new THREE.ExtrudeGeometry(roundedRect(HEAD_W - 0.3, HEAD_H - 0.3, 0.32), {
    depth: HEAD_D, bevelEnabled: true, bevelThickness: 0.15, bevelSize: 0.15, bevelSegments: 6, curveSegments: 12,
  });
  headGeometry.translate(0, 0, -HEAD_D / 2);
  head.add(new THREE.Mesh(headGeometry, shell));

  // Display: dunkler Rahmen, darauf das Gesicht
  const FRONT = HEAD_D / 2 + 0.15;
  const bezel = new THREE.Mesh(new THREE.ShapeGeometry(roundedRect(1.42, 0.98, 0.28), 12), darkShell);
  bezel.position.z = FRONT + 0.002;
  head.add(bezel);
  const SCREEN_W = 1.32, SCREEN_H = 0.88;
  const screen = new THREE.Mesh(fitUv(new THREE.ShapeGeometry(roundedRect(SCREEN_W, SCREEN_H, 0.24), 12),
    SCREEN_W, SCREEN_H), new THREE.MeshBasicMaterial({map: faceTexture}));
  screen.position.z = FRONT + 0.004;
  head.add(screen);
  // schmaler Leuchtrand ums Display in der Zustandsfarbe
  const edgeShape = roundedRect(1.4, 0.96, 0.27);
  edgeShape.holes.push(roundedRect(1.34, 0.9, 0.25));
  const screenEdge = new THREE.Mesh(new THREE.ShapeGeometry(edgeShape, 12), glow);
  screenEdge.position.z = FRONT + 0.003;
  head.add(screenEdge);
  const faceHalo = halo(2.6, 0.22);
  faceHalo.position.z = FRONT + 0.05;
  head.add(faceHalo);
  faceLight.position.set(0, 0, FRONT + 0.6);
  head.add(faceLight);
  // Glanzstreifen über dem Display (Glasabdeckung)
  const glare = new THREE.Mesh(new THREE.ShapeGeometry(roundedRect(1.0, 0.12, 0.06), 6),
    new THREE.MeshBasicMaterial({color: 0xffffff, transparent: true, opacity: 0.07, depthWrite: false}));
  glare.position.set(-0.08, 0.3, FRONT + 0.006);
  glare.rotation.z = 0.04;
  head.add(glare);

  // Kopfhörer-Scheiben mit Leuchtring
  const earRings = [];
  for (const side of [-1, 1]) {
    const ear = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.16, 32), accent);
    ear.rotation.z = Math.PI / 2;
    ear.position.x = side * (HEAD_W / 2 + 0.08);
    head.add(ear);
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.19, 0.19, 0.18, 32), darkShell);
    cap.rotation.z = Math.PI / 2;
    cap.position.x = side * (HEAD_W / 2 + 0.1);
    head.add(cap);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.025, 10, 40), glow);
    ring.rotation.y = Math.PI / 2;
    ring.position.x = side * (HEAD_W / 2 + 0.19);
    head.add(ring);
    earRings.push(ring);
  }

  // Antenne: federnd, Spitze leuchtet
  const antenna = new THREE.Group();
  antenna.position.set(0.32, HEAD_H / 2 + 0.08, 0);
  head.add(antenna);
  const stalk = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.035, 0.42, 10), darkShell);
  stalk.position.y = 0.21;
  antenna.add(stalk);
  const tip = new THREE.Mesh(new THREE.SphereGeometry(0.075, 16, 12), glow);
  tip.position.y = 0.46;
  antenna.add(tip);
  const tipHalo = halo(0.7, 0.55);
  tipHalo.position.y = 0.46;
  antenna.add(tipHalo);


  // Licht von unten auf den Körper (Schweben)
  ringLight.position.set(0, -1.15, 0.5);
  bodyPivot.add(ringLight);

  // Schatten auf dem "Boden": verlaufender Fleck, wird beim Hochschweben kleiner und blasser
  const shadowCanvas = document.createElement("canvas");
  shadowCanvas.width = shadowCanvas.height = 64;
  const shadowCtx = shadowCanvas.getContext("2d");
  const gradient = shadowCtx.createRadialGradient(32, 32, 2, 32, 32, 32);
  gradient.addColorStop(0, "rgba(0,0,0,0.45)");
  gradient.addColorStop(1, "rgba(0,0,0,0)");
  shadowCtx.fillStyle = gradient;
  shadowCtx.fillRect(0, 0, 64, 64);
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 0.5),
    new THREE.MeshBasicMaterial({map: new THREE.CanvasTexture(shadowCanvas), transparent: true, depthWrite: false}));
  shadow.position.y = -1.75;
  shadow.rotation.x = -Math.PI / 2 + 0.25;
  scene.add(shadow);

  // Lichtschein am Boden in der Zustandsfarbe: weicher Lichtfleck statt Ring, atmet ruhig mit
  const poolCanvas = document.createElement("canvas");
  poolCanvas.width = poolCanvas.height = 128;
  const poolCtx = poolCanvas.getContext("2d");
  const poolGradient = poolCtx.createRadialGradient(64, 64, 0, 64, 64, 64);
  poolGradient.addColorStop(0, "rgba(255,255,255,0.85)");
  poolGradient.addColorStop(0.35, "rgba(255,255,255,0.35)");
  poolGradient.addColorStop(1, "rgba(255,255,255,0)");
  poolCtx.fillStyle = poolGradient;
  poolCtx.fillRect(0, 0, 128, 128);
  const pool = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 1.5),
    new THREE.MeshBasicMaterial({map: new THREE.CanvasTexture(poolCanvas), color: 0x8fd8ff, transparent: true,
      opacity: 0.3, depthWrite: false}));   // normal überblenden: additiv bliebe im durchsichtigen Fenster unsichtbar
  pool.position.y = -1.74;
  pool.rotation.x = -Math.PI / 2 + 0.25;
  scene.add(pool);

  let chatSide = 1;   // Chat liegt rechts (1) oder links (-1) vom Begleiter

  // --- Eigenes Modell (glTF) -------------------------------------------------------------------
  const BUILT_IN = [torso, collar, chest, chestRing, chestHalo, arms.left, arms.right, neck];
  let custom = null;   // {pivot, head, armL, armR, rest, glowMaterials, mixer}

  function findPart(model, pattern) {
    let found = null;
    model.traverse(node => { if (!found && node !== model && pattern.test(node.name || "")) found = node; });
    return found;
  }

  const DEFAULT_OPTIONS = {yaw: 0, size: 1, lift: 0, hover: true, eyes: "glow", iris_hue: [160, 260]};

  function useModel(gltf, options) {
    options = Object.assign({}, DEFAULT_OPTIONS, options || {});
    const model = gltf.scene;
    model.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(model);
    const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());

    // Blickrichtung: Viele Modelle schauen nicht nach +Z (zur Kamera). Liegt das Gesicht (Material/Objekt
    // mit face, screen, display, eye im Namen) seitlich oder hinten, das Modell in 90°-Schritten drehen.
    const front = new THREE.Box3();
    model.traverse(node => {
      if (!node.isMesh) return;
      const materials = Array.isArray(node.material) ? node.material : [node.material];
      if (materials.some(m => /face|screen|display|eye/i.test(`${m.name} ${node.name}`))) front.expandByObject(node);
    });
    let yaw = 0;
    if (!front.isEmpty()) {
      const toFace = front.getCenter(new THREE.Vector3()).sub(center);
      if (Math.hypot(toFace.x, toFace.z) > 0.05 * Math.max(size.x, size.z)) {
        yaw = -Math.round(Math.atan2(toFace.x, toFace.z) / (Math.PI / 2)) * (Math.PI / 2);
      }
    }

    const faceYaw = yaw, extraYaw = (options.yaw || 0) * Math.PI / 180;   // z. B. ein Auto schräg von vorn
    yaw = faceYaw + extraYaw * chatSide;   // schräg zum Popup hin, auf beiden Seiten

    // auf Größe bringen: etwa so hoch wie die eingebaute Figur, unten über dem Schwebering
    const scale = 2.95 * options.size / Math.max(size.y, Math.max(size.x, size.z) * 0.8, 0.001);
    const pivot = new THREE.Group(), turn = new THREE.Group();
    model.position.set(-center.x, -box.min.y, -center.z);
    turn.rotation.y = yaw;
    turn.add(model);
    pivot.add(turn);
    pivot.scale.setScalar(scale);
    pivot.position.y = -1.2 + options.lift * 2.95;
    bodyPivot.add(pivot);

    const glowMaterials = [], faceMeshes = [];
    let eyes = null;
    model.traverse(node => {
      if (!node.isMesh) return;
      const materials = Array.isArray(node.material) ? node.material : [node.material];
      for (const material of materials) {
        const label = `${material.name} ${node.name}`;
        const eyeImage = (material.emissiveMap || material.map || {}).image;
        if (options.eyes === "iris" && /eye|auge/i.test(label) && material.emissive && eyeImage && !eyes) {
          // echte Augen (Augapfel + Iris): nur die Iris nimmt die Zustandsfarbe an und leuchtet leicht
          eyes = irisEyes(eyeImage, options.iris_hue);
          if (eyes) {
            material.map = eyes.texture;
            material.emissiveMap = eyes.glowTexture;
            material.emissive.set(0xffffff);
            material.emissiveIntensity = 0.9;
            material.needsUpdate = true;
            eyes.material = material;
            continue;
          }
        }
        if (options.eyes === "glow" && /screen|display|face/i.test(label) && material.emissive && eyeImage && !eyes) {
          // Visier mit eigenen Augen: die bleiben, werden aber eingefärbt und bewegt (modelEyes)
          eyes = modelEyes(eyeImage);
          if (eyes) {
            material.map = null;
            material.color.set(0x05070c);
            material.emissiveMap = eyes.texture;
            material.emissive.copy(color);
            material.emissiveIntensity = 1;
            material.toneMapped = false;   // Augenfarbe kräftig lassen, nicht ausbleichen
            material.needsUpdate = true;
            eyes.material = material;
            faceMeshes.push(node);
            continue;
          }
        }
        const emissive = material.emissive && (material.emissive.getHex() !== 0 || material.emissiveMap);
        if (options.eyes !== "keep" && (emissive || /eye|light|glow|emiss|led|lamp/i.test(label))) {
          glowMaterials.push(material);
        }
      }
    });

    if (eyes && !eyes.iris) eyeAxes(pivot, faceMeshes, eyes);

    const head = findPart(model, /head|kopf/i);
    const armL = findPart(model, /(arm|hand).*(_l\b|\.l\b|left|links)|(left|links).*(arm|hand)/i);
    const armR = findPart(model, /(arm|hand).*(_r\b|\.r\b|right|rechts)|(right|rechts).*(arm|hand)/i);
    const rest = new Map([head, armL, armR].filter(Boolean).map(part => [part, part.rotation.clone()]));

    let mixer = null;
    if (gltf.animations && gltf.animations.length) {
      mixer = new THREE.AnimationMixer(model);
      const clip = gltf.animations.find(item => /idle|hover|float|loop/i.test(item.name)) || gltf.animations[0];
      mixer.clipAction(clip).play();
    }
    for (const part of BUILT_IN) part.visible = false;
    custom = {pivot, head, armL, armR, rest, glowMaterials, mixer, eyes, hover: options.hover,
      turn, faceYaw, extraYaw};
    wake();
  }

  // Modell wieder entfernen (Wechsel in den Einstellungen) und den Speicher freigeben
  function unloadModel() {
    if (!custom) return;
    bodyPivot.remove(custom.pivot);
    custom.pivot.traverse(node => {
      if (!node.isMesh) return;
      node.geometry.dispose();
      for (const material of Array.isArray(node.material) ? node.material : [node.material]) {
        for (const key of ["map", "emissiveMap", "normalMap", "roughnessMap", "metalnessMap", "aoMap"]) {
          if (material[key]) material[key].dispose();
        }
        material.dispose();
      }
    });
    custom = null;
    for (const part of BUILT_IN) part.visible = true;
    faceKey = "";
    wake();
  }

  // Echte Augen: Pixel im Farbton der Iris werden zur Maske; beim Zustandswechsel wird nur die Iris
  // neu eingefärbt (Helligkeit/Struktur bleibt). Zweite Leinwand: nur die Iris, fürs Leuchten.
  function irisEyes(image, hueRange) {
    const width = Math.min(512, image.width || 512);
    const height = Math.max(1, Math.round(width * (image.height || 1) / (image.width || 1)));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    let pixels;
    try {
      ctx.drawImage(image, 0, 0, width, height);
      pixels = ctx.getImageData(0, 0, width, height);
    } catch (error) {
      return null;
    }
    const original = new Uint8ClampedArray(pixels.data);
    const weight = new Float32Array(width * height);   // 0 = keine Iris, 1 = Iris
    const [from, to] = hueRange;
    let count = 0;
    for (let i = 0; i < weight.length; i++) {
      const r = original[i * 4] / 255, g = original[i * 4 + 1] / 255, b = original[i * 4 + 2] / 255;
      const max = Math.max(r, g, b), min = Math.min(r, g, b), chroma = max - min;
      if (chroma < 0.12 || max < 0.12) continue;
      let hue = max === r ? ((g - b) / chroma) % 6 : max === g ? (b - r) / chroma + 2 : (r - g) / chroma + 4;
      hue = (hue * 60 + 360) % 360;
      const inside = from <= to ? hue >= from && hue <= to : hue >= from || hue <= to;
      if (inside) {
        weight[i] = Math.min(1, chroma * 2.5);
        count++;
      }
    }
    if (!count) return null;
    const glow = document.createElement("canvas");
    glow.width = width;
    glow.height = height;
    const make = source => {
      const texture = new THREE.CanvasTexture(source);
      texture.flipY = false;
      texture.encoding = THREE.sRGBEncoding;
      return texture;
    };
    return {iris: true, canvas, ctx, pixels, original, weight, glow, glowCtx: glow.getContext("2d"),
      texture: make(canvas), glowTexture: make(glow), tint: "", material: null};
  }

  function tintIris(eyes) {
    const tint = color.getHexString();
    if (tint === eyes.tint) return;
    eyes.tint = tint;
    const {pixels, original, weight} = eyes;
    const out = pixels.data;
    const glow = eyes.glowCtx.createImageData(eyes.glow.width, eyes.glow.height);
    const tr = color.r * 255, tg = color.g * 255, tb = color.b * 255;
    for (let i = 0; i < weight.length; i++) {
      const k = i * 4, w = weight[i];
      if (!w) {
        out[k] = original[k]; out[k + 1] = original[k + 1]; out[k + 2] = original[k + 2];
        glow.data[k + 3] = 255;
        continue;
      }
      // Helligkeit des Originals behalten, Farbe aus dem Zustand
      const light = Math.max(original[k], original[k + 1], original[k + 2]) / 255;
      const shade = Math.min(1.25, 0.35 + light * 1.1);
      out[k] = original[k] * (1 - w) + Math.min(255, tr * shade) * w;
      out[k + 1] = original[k + 1] * (1 - w) + Math.min(255, tg * shade) * w;
      out[k + 2] = original[k + 2] * (1 - w) + Math.min(255, tb * shade) * w;
      glow.data[k] = tr * w * light;
      glow.data[k + 1] = tg * w * light;
      glow.data[k + 2] = tb * w * light;
      glow.data[k + 3] = 255;
    }
    eyes.ctx.putImageData(pixels, 0, 0);
    eyes.glowCtx.putImageData(glow, 0, 0);
    eyes.texture.needsUpdate = true;
    eyes.glowTexture.needsUpdate = true;
  }

  // Augen des Modells: Aus seiner Textur wird eine helligkeitsbasierte Maske (Form und LED-Linien bleiben),
  // die in eine eigene Leinwand gezeichnet wird - verschoben, gestaucht, beschnitten je nach Stimmung.
  // Das Material färbt sie über die Emission in der Zustandsfarbe.
  function modelEyes(image) {
    const width = 512, height = Math.max(1, Math.round(512 * (image.height || 1) / (image.width || 1)));
    const mask = document.createElement("canvas");
    mask.width = width;
    mask.height = height;
    const maskCtx = mask.getContext("2d");
    let pixels;
    try {
      maskCtx.drawImage(image, 0, 0, width, height);
      pixels = maskCtx.getImageData(0, 0, width, height);
    } catch (error) {
      return null;   // Bild nicht lesbar: Modell behält sein Gesicht unverändert
    }
    const data = pixels.data;
    let x0 = width, y0 = height, x1 = -1, y1 = -1;
    for (let i = 0; i < data.length; i += 4) {
      const light = Math.max(data[i], data[i + 1], data[i + 2]);
      data[i] = data[i + 1] = data[i + 2] = 255;   // weiß, Helligkeit steckt im Alpha
      data[i + 3] = Math.min(255, light * 1.15);
      if (light > 60) {
        const x = (i / 4) % width, y = Math.floor(i / 4 / width);
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
    if (x1 < 0) return null;   // keine hellen Augen gefunden
    maskCtx.putImageData(pixels, 0, 0);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const texture = new THREE.CanvasTexture(canvas);
    texture.flipY = false;   // glTF-Konvention
    texture.encoding = THREE.sRGBEncoding;
    texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
    return {mask, canvas, ctx: canvas.getContext("2d"), texture, key: "", material: null,
      box: {x: (x0 + x1) / 2, y: (y0 + y1) / 2, w: x1 - x0, h: y1 - y0}, sx: 1, sy: 1};
  }

  // Richtung der Textur auf dem Visier: wohin geht "rechts" und "oben" auf dem Bildschirm in der Textur?
  function eyeAxes(pivot, meshes, eyes) {
    pivot.updateMatrixWorld(true);
    const toPivot = new THREE.Matrix4().copy(pivot.matrixWorld).invert();
    const point = new THREE.Vector3();
    let ux = 0, vy = 0;
    for (const mesh of meshes) {
      const positions = mesh.geometry.attributes.position, uvs = mesh.geometry.attributes.uv;
      if (!uvs) continue;
      const matrix = new THREE.Matrix4().multiplyMatrices(toPivot, mesh.matrixWorld);
      const step = Math.max(1, Math.floor(positions.count / 400));
      const samples = [];
      for (let i = 0; i < positions.count; i += step) {
        point.fromBufferAttribute(positions, i).applyMatrix4(matrix);
        samples.push([point.x, point.y, uvs.getX(i), uvs.getY(i)]);
      }
      const mean = k => samples.reduce((sum, item) => sum + item[k], 0) / samples.length;
      const [mx, my, mu, mv] = [0, 1, 2, 3].map(mean);
      for (const [x, y, u, v] of samples) {
        ux += (u - mu) * (x - mx);
        vy += (v - mv) * (y - my);
      }
    }
    eyes.sx = ux < 0 ? -1 : 1;   // Textur-x wächst nach rechts (1) oder links (-1)
    eyes.sy = vy < 0 ? -1 : 1;   // Textur-y (Zeilen) wächst nach oben (1) oder unten (-1)
  }

  function drawModelEyes(eyes, now, mood) {
    const {ctx, mask, box} = eyes;
    const blink = now < blinkUntil ? 0.1 : 1;
    const sleepy = mood === "sleepy" ? 0.45 : 1;
    let open = Math.max(0.1, blink * sleepy), scale = 1, lookUp = 0;
    if (mood === "listen") scale = 1.08;
    const thinking = mood === "think";
    if (mood === "error") open *= 0.5;
    if (mood === "speak") scale = 1 + voice * 0.07;
    // Blick: im Bild um bis zu ~ein Fünftel der Augenbreite verschieben
    const dx = look.x * box.w * 0.09 * eyes.sx;
    const dy = (look.y * 0.12 + lookUp) * box.h * eyes.sy;   // sy: wächst die Zeile nach oben (1) oder unten (-1)
    const key = [mood, open.toFixed(2), scale.toFixed(3), dx.toFixed(0), dy.toFixed(0),
      thinking ? Math.floor(now / 110) : 0].join("|");
    if (key === eyes.key) return;
    eyes.key = key;

    const W = eyes.canvas.width, H = eyes.canvas.height;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#fff";
    ctx.save();
    ctx.shadowColor = "rgba(255,255,255,0.75)";   // weicher Lichtschein um die Augen
    ctx.shadowBlur = 14;
    if (thinking) {
      drawThinkDots(ctx, box, now);
    } else {
      ctx.translate(box.x + dx, box.y + dy);
      ctx.scale(scale, scale * open);
      ctx.translate(-box.x, -box.y);
      ctx.drawImage(mask, 0, 0);
    }
    ctx.restore();
    if (mood === "happy") {
      // fröhlich: unteren Teil wegschneiden - übrig bleiben nach oben gewölbte Bögen
      ctx.fillStyle = "#000";
      ctx.beginPath();
      ctx.ellipse(box.x + dx, box.y + dy + box.h * 0.45 * eyes.sy * -1, box.w * 0.62, box.h * 0.55, 0, 0, TAU);
      ctx.fill();
    }
    eyes.texture.needsUpdate = true;
  }

  // Beim Nachdenken: drei Punkte im Augenbereich, die nacheinander aufleuchten (Farbe kommt vom Material)
  function drawThinkDots(ctx, box, now) {
    const radius = Math.min(box.h * 0.27, box.w * 0.085), gap = radius * 3;
    for (let i = 0; i < 3; i++) {
      const phase = (now / 900 - i * 0.18) % 1;
      const pulse = Math.max(0, Math.sin(phase * Math.PI));   // 0 .. 1 .. 0
      ctx.globalAlpha = 0.3 + 0.7 * pulse;
      ctx.beginPath();
      ctx.arc(box.x + (i - 1) * gap, box.y - pulse * radius * 0.5, radius * (0.85 + 0.25 * pulse), 0, TAU);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  let modelUrl = "", loadToken = 0;

  // url "" oder ungültig: eingebaute Figur. Ein späterer Wechsel überholt einen noch laufenden.
  function loadModel(url, options) {
    if (!/^file:\/\/.+\.(glb|gltf)$/i.test(url || "") || !THREE.GLTFLoader) url = "";
    if (url === modelUrl) return;
    modelUrl = url;
    const token = ++loadToken;
    if (!url) {
      unloadModel();
      return;
    }
    new THREE.GLTFLoader().load(url, gltf => {
      if (token !== loadToken) return;   // inzwischen ein anderes gewählt
      unloadModel();
      useModel(gltf, options);
      gesture("wave", 1500);
    }, undefined, error => {
      console.warn("Modell nicht geladen, eingebaute Figur bleibt:", error && error.message);
      if (token === loadToken) { modelUrl = ""; unloadModel(); }
    });
  }

  function startModel() {
    const params = new URLSearchParams(location.search);
    let options = {};
    try { options = JSON.parse(params.get("options") || "{}"); } catch (error) { options = {}; }
    loadModel(params.get("model") || "", options);
  }

  // Bewegungen der eingebauten Figur aufs eigene Modell übertragen
  function driveModel(dt, now, mood) {
    if (!custom) return;
    if (custom.eyes && custom.eyes.iris) {
      tintIris(custom.eyes);
    } else if (custom.eyes) {
      drawModelEyes(custom.eyes, now, mood);
      custom.eyes.material.emissive.copy(color);
      custom.eyes.material.emissiveIntensity = mood === "speak" ? 1 + voice * 0.35 : 1;
    }
    if (custom.mixer) custom.mixer.update(dt);
    if (custom.head) {
      const rest = custom.rest.get(custom.head);
      custom.head.rotation.set(rest.x + neck.rotation.x, rest.y + neck.rotation.y, rest.z + neck.rotation.z);
      custom.pivot.rotation.y = 0;
    } else {
      // ohne eigenen Kopf: das ganze Modell schaut (etwas schwächer) mit
      custom.pivot.rotation.set(neck.rotation.x * 0.5, neck.rotation.y * 0.6, neck.rotation.z * 0.6);
    }
    for (const [part, arm, restZ] of [[custom.armR, arms.right, 0.18], [custom.armL, arms.left, -0.18]]) {
      if (!part) continue;
      const rest = custom.rest.get(part);
      part.rotation.set(rest.x + arm.rotation.x * 0.6, rest.y, rest.z + (arm.rotation.z - restZ) * 0.6);
    }
    for (const material of custom.glowMaterials) {
      if (material.emissive) {
        material.emissive.copy(color);
        if (material.emissiveIntensity < 1) material.emissiveIntensity = 1;
      } else if (material.color) {
        material.color.copy(color);
      }
    }
  }

  // --- Zustand ----------------------------------------------------------------------------------
  let state = "idle";
  const color = new THREE.Color(STATES.idle.color);   // aktuelle Leuchtfarbe (weich angenähert)
  const targetColor = new THREE.Color(STATES.idle.color);
  const errorColor = new THREE.Color(ERROR_COLOR);
  const look = {x: 0, y: 0, tx: 0, ty: 0, nextWander: 0};
  const pointer = {x: 0, y: 0, movedAt: -1e9, inside: false};
  const gestures = [];   // laufende Gesten: {name, start, duration}
  let blinkAt = 0, blinkUntil = 0;
  let lastActivity = performance.now();
  let voice = 0, voiceTarget = 0, nextVoiceAt = 0;
  let antennaVel = 0, antennaAngle = 0, lastYaw = 0;
  let faceKey = "";
  let running = false, lastFrame = 0;

  function setState(next) {
    if (!STATES[next]) return;
    if (next !== state) lastActivity = performance.now();
    state = next;
    targetColor.set(STATES[state].color);
  }

  function gesture(name, duration) {
    lastActivity = performance.now();
    for (let i = gestures.length - 1; i >= 0; i--) if (gestures[i].name === name) gestures.splice(i, 1);
    gestures.push({name, start: performance.now(), duration});
    wake();
  }

  function gestureProgress(name, now) {
    for (const item of gestures) {
      if (item.name === name) return Math.min(1, (now - item.start) / item.duration);
    }
    return -1;
  }

  function setAccent(value) {
    try { accent.color.set(value); } catch (error) { /* ungültige Farbe: bleibt */ }
    wake();
  }

  // Mauszeiger relativ zum Fenster (x, y, Breite, Höhe) - auch außerhalb des Fensters
  function setPointer(x, y, width, height) {
    if (!width || !height) return;
    // Kopf sitzt etwa im oberen Drittel des Fensters
    const dx = (x - width / 2) / (width * 1.6);
    const dy = (height * 0.36 - y) / (height * 1.6);
    pointer.x = Math.max(-1, Math.min(1, dx));
    pointer.y = Math.max(-1, Math.min(1, dy));
    pointer.movedAt = performance.now();
    pointer.inside = x >= 0 && y >= 0 && x < width && y < height;
    lastActivity = pointer.movedAt;
    wake();
  }

  // --- Gesicht malen ---------------------------------------------------------------------------
  function hex(c) { return `#${c.getHexString()}`; }

  function drawFace(now, mood) {
    const W = face.width, H = face.height;
    const ctx = faceCtx;
    const lit = hex(color);
    const blink = now < blinkUntil ? 0.08 : 1;
    const sleepy = mood === "sleepy" ? 0.35 : 1;
    const open = Math.max(0.08, blink * sleepy);
    const ex = look.x * 34, ey = -look.y * 22;
    const keyNow = [mood, lit, open.toFixed(2), ex.toFixed(0), ey.toFixed(0), voice.toFixed(2),
      state === "thinking" || mood === "listen" ? Math.floor(now / 120) : 0].join("|");
    if (keyNow === faceKey) return;
    faceKey = keyNow;

    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, "#0b0e15");
    bg.addColorStop(1, "#040509");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);
    // feine Zeilen wie bei einem LED-Display
    ctx.fillStyle = "rgba(255,255,255,0.018)";
    for (let y = 0; y < H; y += 6) ctx.fillRect(0, y, W, 2);

    ctx.save();
    ctx.shadowColor = lit;
    ctx.shadowBlur = 16;
    ctx.fillStyle = lit;
    ctx.strokeStyle = lit;
    ctx.lineCap = "round";
    const cy = 140 + ey;
    const eyes = [W / 2 - 100 + ex, W / 2 + 100 + ex];

    if (mood === "happy") {
      ctx.lineWidth = 22;
      for (const x of eyes) {
        ctx.beginPath();
        ctx.arc(x, cy + 22, 44, Math.PI * 1.15, Math.PI * 1.85);
        ctx.stroke();
      }
    } else if (mood === "error") {
      ctx.lineWidth = 20;
      for (const [x, dir] of [[eyes[0], 1], [eyes[1], -1]]) {
        ctx.beginPath();
        ctx.moveTo(x - 34 * dir, cy - 34);
        ctx.lineTo(x + 30 * dir, cy);
        ctx.lineTo(x - 34 * dir, cy + 34);
        ctx.stroke();
      }
    } else {
      const width = mood === "listen" ? 76 : 66;
      const height = (mood === "listen" ? 116 : mood === "think" ? 70 : 104) * open;
      for (const x of eyes) {
        const r = Math.min(width, height) / 2;
        ctx.beginPath();
        ctx.moveTo(x - width / 2 + r, cy - height / 2);
        ctx.arcTo(x + width / 2, cy - height / 2, x + width / 2, cy + height / 2, r);
        ctx.arcTo(x + width / 2, cy + height / 2, x - width / 2, cy + height / 2, r);
        ctx.arcTo(x - width / 2, cy + height / 2, x - width / 2, cy - height / 2, r);
        ctx.arcTo(x - width / 2, cy - height / 2, x + width / 2, cy - height / 2, r);
        ctx.fill();
      }
    }

    // unter den Augen: Denk-Punkte, Pegel beim Zuhören, Mund beim Sprechen
    ctx.shadowBlur = 10;
    if (mood === "think") {
      const step = Math.floor(now / 260) % 4;
      for (let i = 0; i < 3; i++) {
        ctx.globalAlpha = i < step ? 1 : 0.25;
        ctx.beginPath();
        ctx.arc(W / 2 - 34 + i * 34, 258, 10, 0, TAU);
        ctx.fill();
      }
    } else if (mood === "listen" || mood === "speak") {
      const bars = mood === "speak" ? 7 : 5;
      for (let i = 0; i < bars; i++) {
        const wave = 0.35 + 0.65 * Math.abs(Math.sin(now / 140 + i * 1.3)) * (0.4 + voice);
        const h = 8 + wave * (mood === "speak" ? 44 : 30);
        ctx.globalAlpha = 0.95;
        ctx.fillRect(W / 2 - bars * 11 + i * 22 + 3, 262 - h / 2, 12, h);
      }
    }
    ctx.restore();
    faceTexture.needsUpdate = true;
  }

  function currentMood(now) {
    if (gestureProgress("error", now) >= 0) return "error";
    if (gestureProgress("hop", now) >= 0 || gestureProgress("wave", now) >= 0) return "happy";
    if (state === "thinking" || state === "transcribing") return "think";
    if (state === "listening") return "listen";
    if (state === "speaking") return "speak";
    if (now - lastActivity > SLEEP_AFTER_MS) return "sleepy";
    return "normal";
  }

  // --- Bewegung -----------------------------------------------------------------------------
  function chooseLook(now) {
    if (state === "listening" || state === "transcribing") { look.tx = 0; look.ty = 0.05; return; }
    if (state === "thinking") {
      look.tx = Math.sin(now / 2400) * 0.12;   // leicht hin und her, wie beim Grübeln
      look.ty = 0.2;
      return;
    }
    if (state === "speaking") {   // meist den Nutzer ansehen, ab und zu zum Chat
      look.tx = Math.sin(now / 1700) * 0.18 + (Math.sin(now / 5300) > 0.75 ? 0.55 * chatSide : 0);
      look.ty = Math.sin(now / 1300) * 0.06;
      return;
    }
    if (now - pointer.movedAt < 2500) {   // dem Mauszeiger folgen
      look.tx = pointer.x;
      look.ty = pointer.y;
      return;
    }
    if (now > look.nextWander) {          // sich umschauen
      const glanceAtChat = Math.random() < 0.3;
      look.tx = glanceAtChat ? 0.7 * chatSide : (Math.random() * 2 - 1) * 0.6;
      look.ty = glanceAtChat ? -0.1 : (Math.random() * 2 - 1) * 0.35;
      look.nextWander = now + 1400 + Math.random() * 3200;
    }
  }

  function ease(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

  function update(now, dt) {
    for (let i = gestures.length - 1; i >= 0; i--) {
      if (now - gestures[i].start > gestures[i].duration) gestures.splice(i, 1);
    }
    chooseLook(now);
    const follow = Math.min(1, dt * (state === "speaking" ? 3 : 5));
    look.x += (look.tx - look.x) * follow;
    look.y += (look.ty - look.y) * follow;

    // Blinzeln
    if (now > blinkAt) {
      blinkUntil = now + 110;
      blinkAt = now + 2200 + Math.random() * 4200;
    }
    // Stimme nachahmen (die echte Ausgabe läuft in Python)
    if (now > nextVoiceAt) {
      voiceTarget = state === "speaking" || state === "listening" ? Math.pow(Math.random(), 1.3) : 0;
      nextVoiceAt = now + 90 + Math.random() * 110;
    }
    voice += (voiceTarget - voice) * Math.min(1, dt * 10);

    // Farbe: Zustand, bei Fehler kurz rot
    const errorAt = gestureProgress("error", now);
    const wanted = errorAt >= 0 ? errorColor : targetColor;
    color.lerp(wanted, Math.min(1, dt * 6));
    glow.color.copy(color);
    glowSoft.color.copy(color);
    rim.color.copy(color);
    rim2.color.copy(color);
    faceLight.color.copy(color);
    ringLight.color.copy(color);
    pool.material.color.copy(color);
    for (const sprite of halos) sprite.material.color.copy(color);

    // Schweben
    const t = now / 1000;
    const floating = !custom || custom.hover;   // z. B. ein Auto steht und wippt nur leicht
    let hover = Math.sin(t * 1.7) * (floating ? 0.07 : 0.015) + (state === "speaking" ? voice * 0.05 : 0);
    let spin = 0, tilt = 0;
    const hop = gestureProgress("hop", now);
    if (hop >= 0) {
      hover += Math.sin(hop * Math.PI) * 0.45;
      spin = ease(hop) * TAU;
    }
    const bounce = gestureProgress("wave", now);
    if (bounce >= 0) hover += Math.abs(Math.sin(bounce * Math.PI * 3)) * 0.08 * (1 - bounce);
    root.position.y = hover;
    bodyPivot.rotation.y = spin + look.x * 0.12;
    if (state === "listening") tilt = 0.12;
    bodyPivot.rotation.z += (0 - bodyPivot.rotation.z) * Math.min(1, dt * 3);

    // Kopf: Blickrichtung, Neigen, Nicken, Kopfschütteln
    let yaw = look.x * 0.55, pitch = -look.y * 0.3, roll = tilt;
    const nod = gestureProgress("nod", now);
    if (nod >= 0) pitch += Math.sin(nod * Math.PI * 2) * 0.22 * (1 - nod);
    if (errorAt >= 0) yaw += Math.sin(errorAt * Math.PI * 6) * 0.35 * (1 - errorAt);
    if (state === "speaking") pitch += Math.sin(t * 5.5) * 0.025 * (0.5 + voice);
    neck.rotation.y += (yaw - neck.rotation.y) * Math.min(1, dt * 8);
    neck.rotation.x += (pitch - neck.rotation.x) * Math.min(1, dt * 8);
    neck.rotation.z += (roll - neck.rotation.z) * Math.min(1, dt * 5);

    // Arme: Ruhe, Winken, Hand ans Kinn beim Nachdenken, Gesten beim Sprechen, Ohr beim Zuhören
    let rightZ = 0.18, rightX = 0, leftZ = -0.18, leftX = 0;
    if (state === "thinking") { rightZ = -0.7; rightX = -1.15; }
    if (state === "listening") { leftZ = -2.6; leftX = -0.2; }   // Hand ans Ohr
    if (state === "speaking") {
      rightZ = 0.35 + Math.sin(t * 2.3) * 0.25 * (0.4 + voice);
      rightX = -0.35 + Math.sin(t * 1.7) * 0.2;
      leftZ = -0.3 - Math.sin(t * 2.1 + 1) * 0.18 * (0.4 + voice);
    }
    if (bounce >= 0) {   // Winken
      const raise = Math.min(1, bounce * 5) * Math.min(1, (1 - bounce) * 5);
      rightZ = rightZ * (1 - raise) + (2.5 + Math.sin(bounce * Math.PI * 8) * 0.35) * raise;
      rightX = rightX * (1 - raise);
    }
    if (hop >= 0) { rightZ = 1.2; leftZ = -1.2; }
    const armEase = Math.min(1, dt * 7);
    arms.right.rotation.z += (rightZ - arms.right.rotation.z) * armEase;
    arms.right.rotation.x += (rightX - arms.right.rotation.x) * armEase;
    arms.left.rotation.z += (leftZ - arms.left.rotation.z) * armEase;
    arms.left.rotation.x += (leftX - arms.left.rotation.x) * armEase;

    // Antenne: Feder, angestoßen von Kopfdrehung und Schweben
    const yawSpeed = (neck.rotation.y - lastYaw) / Math.max(dt, 0.001);
    lastYaw = neck.rotation.y;
    antennaVel += (-antennaAngle * 60 - antennaVel * 6 - yawSpeed * 2.5) * dt;
    antennaAngle += antennaVel * dt;
    antenna.rotation.z = Math.max(-0.6, Math.min(0.6, antennaAngle)) - 0.08;
    const tipPulse = state === "thinking" ? 0.6 + 0.4 * Math.abs(Math.sin(t * 6)) : 1;
    tip.scale.setScalar(0.9 + 0.2 * tipPulse);

    // Ohrringe drehen sich beim Zuhören, Schwebering pulsiert
    const ringSpeed = state === "listening" ? 4 : state === "thinking" ? 2.5 : 0.6;
    for (const ring of earRings) ring.rotation.x += dt * ringSpeed;
    const pulse = 1 + (state === "listening" || state === "speaking" ? voice * 0.12 : Math.sin(t * 2) * 0.03);
    glowSoft.opacity = 0.22 + 0.18 * (pulse - 0.97) * 4;
    chest.scale.setScalar(state === "speaking" ? 0.85 + voice * 0.35 : 1);

    // Licht atmet mit: ruhig im Leerlauf, lebhaft beim Sprechen und Zuhören
    const busy = state === "idle" ? 0 : 1;
    const breathe = 0.85 + 0.15 * Math.sin(t * 2.2);
    const energy = breathe + busy * 0.25 + voice * 0.5;
    faceLight.intensity = 0.7 * energy;
    ringLight.intensity = 1.8 * energy;
    for (const sprite of halos) sprite.material.opacity = sprite.userData.base * Math.min(1.6, energy);
    tipHalo.material.opacity = tipHalo.userData.base * (state === "thinking" ? tipPulse * 1.6 : energy);

    // Schatten
    const lift = root.position.y + 0.2;
    shadow.scale.set(1 - lift * 0.35, 1 - lift * 0.35, 1);
    shadow.material.opacity = Math.max(0.25, 0.9 - lift * 0.8);
    pool.scale.set(pulse * (1 - lift * 0.25), pulse * (1 - lift * 0.25), 1);
    pool.material.opacity = (0.42 + 0.18 * busy + 0.15 * voice) * breathe * (1 - lift * 0.3);

    const mood = currentMood(now);
    if (!custom || !custom.eyes) drawFace(now, mood);
    driveModel(dt, now, mood);
  }

  // --- Schleife -------------------------------------------------------------------------------
  function resize() {
    const width = canvas.clientWidth || window.innerWidth;
    const height = canvas.clientHeight || window.innerHeight;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    // schmales Fenster: Kamera weiter weg, damit die ganze Figur hineinpasst
    camera.position.z = 9.6 * Math.max(1, 0.72 / camera.aspect);
    camera.updateProjectionMatrix();
  }

  function frame(now) {
    if (document.hidden) { running = false; return; }
    const dt = Math.min(0.1, (now - lastFrame) / 1000);
    if (now - lastFrame >= FRAME_MS - 2) {
      lastFrame = now;
      update(now, dt);
      renderer.render(scene, camera);
    }
    requestAnimationFrame(frame);
  }

  function wake() {
    if (running || document.hidden) return;
    running = true;
    lastFrame = performance.now();
    requestAnimationFrame(frame);
  }

  // --- Ereignisse -------------------------------------------------------------------------------
  function onEvent(message) {
    if (!message || typeof message !== "object") return;
    switch (message.kind) {
      case "state": setState(message.state); break;
      case "reply": gesture("nod", 900); break;
      case "proactive": gesture("wave", 1800); gesture("nod", 900); break;
      case "hello": gesture("wave", 1500); break;
      case "error": gesture("error", 1100); break;
      case "theme": if (typeof message.accent === "string") setAccent(message.accent); break;
      case "side":
        chatSide = message.value === "right" ? -1 : 1;
        if (custom) custom.turn.rotation.y = custom.faceYaw + custom.extraYaw * chatSide;
        break;
      case "model": loadModel(typeof message.url === "string" ? message.url : "", message.options); break;
      default: break;
    }
    wake();
  }

  // Anklicken: Hüpfer mit Pirouette; über der Figur sieht sie den Zeiger direkt an
  canvas.addEventListener("click", () => gesture("hop", 950));
  canvas.addEventListener("mousemove", event => {
    setPointer(event.clientX, event.clientY, window.innerWidth, window.innerHeight);
  });
  window.addEventListener("resize", () => { resize(); wake(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) wake(); });
  // Grafikkontext verloren (z. B. Fenster lange verborgen, Treiber): wiederherstellen lassen
  canvas.addEventListener("webglcontextlost", event => { event.preventDefault(); running = false; });
  canvas.addEventListener("webglcontextrestored", () => {
    faceKey = "";
    faceTexture.needsUpdate = true;
    resize();
    wake();
  });

  // Nach dem Einblenden (companion_window.py): sofort ein Bild und die Schleife wieder anwerfen
  function resume() {
    running = false;
    faceKey = "";
    resize();
    gesture("wave", 1500);
    wake();
  }

  resize();
  wake();
  startModel();
  if (window.onPythonEvent) {
    onPythonEvent("companion", onEvent);
    if (window.notifyPython) notifyPython("companion_ready", true);   // Popup schickt Zustand und Design
  }

  return {pointer: setPointer, setState, gesture, setAccent, resume, get state() { return state; }};
})();
