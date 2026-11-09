(function () {
  const stage = document.querySelector(".robot-stage");
  const canvas = stage.querySelector("canvas");
  const shadow = stage.querySelector(".robot-shadow");
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const gl = canvas.getContext("webgl", {alpha: true, antialias: true, depth: true});
  if (!gl) return;

  const vertexSource = `
    attribute vec3 position;
    attribute vec3 normal;
    uniform vec3 angles;
    uniform float lift;
    varying vec3 surfaceNormal;
    varying vec3 toCamera;

    vec3 rotate(vec3 p) {
      vec3 c = cos(angles);
      vec3 s = sin(angles);
      p.xz = vec2(c.y * p.x + s.y * p.z, -s.y * p.x + c.y * p.z);
      p.yz = vec2(c.x * p.y - s.x * p.z, s.x * p.y + c.x * p.z);
      p.xy = vec2(c.z * p.x - s.z * p.y, s.z * p.x + c.z * p.y);
      return p;
    }

    void main() {
      vec3 p = rotate(position);
      p.y += lift;
      float depth = 4.8 - p.z;
      gl_Position = vec4(3.6 * p.xy, 1.013 * depth - .201, depth);
      surfaceNormal = rotate(normalize(normal));
      toCamera = vec3(-p.xy, depth);
    }
  `;
  const fragmentSource = `
    precision mediump float;
    varying vec3 surfaceNormal;
    varying vec3 toCamera;
    uniform vec3 color;
    uniform float gloss;
    uniform float emission;

    void main() {
      vec3 n = normalize(surfaceNormal);
      vec3 v = normalize(toCamera);
      vec3 key = normalize(vec3(-.5, .8, .9));
      vec3 fill = normalize(vec3(.8, .25, -.45));
      float diffuse = max(dot(n, key), 0.);
      float bounce = max(dot(n, fill), 0.);
      float highlight = pow(max(dot(n, normalize(key + v)), 0.), 27.);
      float softbox = pow(max(dot(n, normalize(vec3(.65, .2, .75) + v)), 0.), 12.);
      float rim = pow(1. - clamp(dot(n, v), 0., 1.), 3.);
      vec3 light = vec3(.40, .45, .56) + vec3(.58, .56, .52) * diffuse + .18 * bounce;
      vec3 shaded = color * mix(light, vec3(1.), emission);
      shaded += gloss * (highlight + .24 * softbox) + vec3(.05, .10, .18) * rim;
      gl_FragColor = vec4(shaded, 1.);
    }
  `;

  let scene, frame = 0, inView = false, lastDraw = null, elapsed = 0, dirty = true;

  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const error = gl.getShaderInfoLog(shader);
      gl.deleteShader(shader);
      throw new Error(error);
    }
    return shader;
  }

  function setup() {
    let vertex, fragment, program;
    try {
      vertex = compile(gl.VERTEX_SHADER, vertexSource);
      fragment = compile(gl.FRAGMENT_SHADER, fragmentSource);
      program = gl.createProgram();
      gl.attachShader(program, vertex);
      gl.attachShader(program, fragment);
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
    } catch (error) {
      if (program) gl.deleteProgram(program);
      console.warn("Die 3D-Ansicht ist nicht verfügbar.", error);
      return;
    } finally {
      if (vertex) gl.deleteShader(vertex);
      if (fragment) gl.deleteShader(fragment);
    }

    function buffer(target, data) {
      const handle = gl.createBuffer();
      gl.bindBuffer(target, handle);
      gl.bufferData(target, data, gl.STATIC_DRAW);
      return handle;
    }

    const meshes = buildRobotModel().map(({vertices, indices, color, gloss, emission}) => ({
      vertices: buffer(gl.ARRAY_BUFFER, vertices),
      indices: buffer(gl.ELEMENT_ARRAY_BUFFER, indices),
      count: indices.length, color, gloss, emission
    }));
    const uniforms = {};
    for (const name of ["angles", "lift", "color", "gloss", "emission"]) {
      uniforms[name] = gl.getUniformLocation(program, name);
    }
    const position = gl.getAttribLocation(program, "position");
    const normal = gl.getAttribLocation(program, "normal");
    gl.useProgram(program);
    gl.enableVertexAttribArray(position);
    gl.enableVertexAttribArray(normal);
    gl.enable(gl.DEPTH_TEST);
    gl.clearColor(0, 0, 0, 0);
    scene = {meshes, uniforms, position, normal};
  }

  function draw(time) {
    const pixels = Math.max(1, Math.round(stage.clientWidth * Math.min(window.devicePixelRatio || 1, 2)));
    if (canvas.width !== pixels || canvas.height !== pixels) canvas.width = canvas.height = pixels;
    gl.viewport(0, 0, pixels, pixels);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const {meshes, uniforms, position, normal} = scene;
    const hover = Math.sin(time * 1.55);
    gl.uniform3f(uniforms.angles, -.075 + .05 * Math.sin(time * .9),
      .18 + .25 * Math.sin(time * .95), .045 * Math.sin(time * 1.22));
    gl.uniform1f(uniforms.lift, .064 * hover);
    for (const mesh of meshes) {
      gl.bindBuffer(gl.ARRAY_BUFFER, mesh.vertices);
      gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 24, 0);
      gl.vertexAttribPointer(normal, 3, gl.FLOAT, false, 24, 12);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, mesh.indices);
      gl.uniform3fv(uniforms.color, mesh.color);
      gl.uniform1f(uniforms.gloss, mesh.gloss);
      gl.uniform1f(uniforms.emission, mesh.emission);
      gl.drawElements(gl.TRIANGLES, mesh.count, gl.UNSIGNED_SHORT, 0);
    }
    shadow.style.transform = `scaleX(${1 + .11 * hover})`;
    shadow.style.opacity = 1 - .16 * hover;
    stage.dataset.renderer = "webgl";
  }

  function tick(now) {
    frame = 0;
    if (!scene || !inView || document.hidden) return;
    const delta = lastDraw === null ? 0 : now - lastDraw;
    if (dirty || delta >= 32) {
      if (!motion.matches) elapsed += Math.min(delta, 64) / 1000;
      draw(motion.matches ? 0 : elapsed);
      lastDraw = now;
      dirty = false;
    }
    if (!motion.matches) frame = requestAnimationFrame(tick);
  }

  function refresh() {
    cancelAnimationFrame(frame);
    frame = 0;
    lastDraw = null;
    dirty = true;
    if (scene && inView && !document.hidden) frame = requestAnimationFrame(tick);
  }

  canvas.addEventListener("webglcontextlost", event => {
    event.preventDefault();
    scene = null;
    delete stage.dataset.renderer;
    refresh();
  });
  canvas.addEventListener("webglcontextrestored", () => { setup(); refresh(); });
  document.addEventListener("visibilitychange", refresh);
  motion.addListener(refresh);
  new ResizeObserver(refresh).observe(stage);
  new IntersectionObserver(([entry]) => {
    inView = entry.isIntersecting;
    refresh();
  }).observe(stage);
  setup();
}());
