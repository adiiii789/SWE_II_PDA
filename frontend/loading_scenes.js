// Szenen des Ladebildschirms - pro Design eine (loading_screen.js zeichnet sie auf ein einziges Canvas).
//
// Eine Szene: {
//   start(W, H)            einmaliger Aufbau, gibt den Zustand zurück (optional)
//   draw(c, W, H, t, s, info)   ein Bild; t = Sekunden seit Start, s = Zustand,
//                          info = {progress 0..1, index, total, labels, label}
//   tagline                Spruch unter der Szene: Text oder Liste (wechselt alle 3,2 s)
//   ink, inkMuted          Farben der Beschriftung, falls die Szene nicht zum Design-Text passt
//   fps                    Standard 20; 0 = nur neu zeichnen, wenn sich der Fortschritt ändert
//   pixel                  grobe Pixel: so viele Bildschirmpunkte pro Canvas-Punkt
//   screen                 true = nur der Anzeigebereich statt des ganzen Popups (Gameboy)
//   showsStep              true = die Szene nennt den aktuellen Schritt selbst, keine Zeile darunter
// }
// Sparsam bleiben: kein shadowBlur pro Bild, nur einfache Formen - dieselbe Seite wickelt die
// Python-Aufrufe ab.

const LoadingScenes = (() => {
  const TAU = Math.PI * 2;

  // --- Hilfen -----------------------------------------------------------------------------------
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, f) => a + (b - a) * f;
  const ease = f => f * f * (3 - 2 * f);
  const cycle = (t, period) => (t % period) / period;
  const pick = (list, t, period) => list[Math.floor(t / period) % list.length];

  function random(seed) {
    return () => {
      seed = (seed + 0x6D2B79F5) | 0;
      let x = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
      return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
    };
  }

  function fill(c, x, y, w, h, color) { c.fillStyle = color; c.fillRect(x, y, w, h); }
  function disc(c, x, y, r, color) { c.fillStyle = color; c.beginPath(); c.arc(x, y, Math.max(0, r), 0, TAU); c.fill(); }
  function oval(c, x, y, rx, ry, color, rot = 0) {
    c.fillStyle = color; c.beginPath(); c.ellipse(x, y, Math.max(0, rx), Math.max(0, ry), rot, 0, TAU); c.fill();
  }
  function shape(c, points, color, close = true) {
    c.beginPath();
    points.forEach(([x, y], i) => (i ? c.lineTo(x, y) : c.moveTo(x, y)));
    if (close) { c.closePath(); c.fillStyle = color; c.fill(); } else { c.strokeStyle = color; c.stroke(); }
  }
  function line(c, x1, y1, x2, y2, color, width = 1) {
    c.strokeStyle = color; c.lineWidth = width; c.beginPath(); c.moveTo(x1, y1); c.lineTo(x2, y2); c.stroke();
  }
  function round(c, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    c.beginPath();
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
  }
  function card(c, x, y, w, h, r, color) { round(c, x, y, w, h, r); c.fillStyle = color; c.fill(); }
  function write(c, text, x, y, font, color, align = "center") {
    c.font = font; c.fillStyle = color; c.textAlign = align; c.textBaseline = "middle"; c.fillText(text, x, y);
  }
  function linear(c, x1, y1, x2, y2, stops) {
    const g = c.createLinearGradient(x1, y1, x2, y2);
    stops.forEach(([at, color]) => g.addColorStop(at, color));
    return g;
  }

  // Linienzüge nach und nach zeichnen (Bleistift, Reißbrett); gibt die Spitze zurück.
  function drawLines(c, lines, length, color, width) {
    c.strokeStyle = color; c.lineWidth = width; c.lineCap = "round"; c.lineJoin = "round";
    let left = length, tip = lines[0][0];
    for (const points of lines) {
      c.beginPath();
      c.moveTo(points[0][0], points[0][1]);
      tip = left > 0 ? points[0] : tip;
      for (let i = 1; i < points.length && left > 0; i++) {
        const [ax, ay] = points[i - 1], [bx, by] = points[i];
        const part = Math.hypot(bx - ax, by - ay), f = Math.min(1, left / part);
        tip = [lerp(ax, bx, f), lerp(ay, by, f)];
        c.lineTo(tip[0], tip[1]);
        left -= part;
      }
      c.stroke();
      if (left <= 0) break;
    }
    return tip;
  }
  const linesLength = lines => lines.reduce((sum, points) => sum + points.slice(1).reduce(
    (part, [x, y], i) => part + Math.hypot(x - points[i][0], y - points[i][1]), 0), 0);

  // Zahnrad
  function gear(c, x, y, radius, teeth, angle, color, hole) {
    c.save();
    c.translate(x, y);
    c.rotate(angle);
    c.beginPath();
    const step = TAU / teeth, inner = radius * 0.84;
    for (let i = 0; i < teeth; i++) {
      const a = i * step;
      c.lineTo(Math.cos(a - step * 0.27) * inner, Math.sin(a - step * 0.27) * inner);
      c.lineTo(Math.cos(a - step * 0.14) * radius, Math.sin(a - step * 0.14) * radius);
      c.lineTo(Math.cos(a + step * 0.14) * radius, Math.sin(a + step * 0.14) * radius);
      c.lineTo(Math.cos(a + step * 0.27) * inner, Math.sin(a + step * 0.27) * inner);
    }
    c.closePath();
    c.fillStyle = color;
    c.fill();
    for (let i = 0; i < 4; i++) {
      c.rotate(TAU / 4);
      fill(c, -radius * 0.05, 0, radius * 0.1, radius * 0.7, hole);
    }
    disc(c, 0, 0, radius * 0.2, hole);
    c.restore();
  }

  // Frucht (rund, mit Blatt) für die beiden Apple-Designs
  function fruit(c, x, y, S, squeeze = 1) {
    c.save();
    c.translate(x, y);
    c.scale(squeeze, 1);
    c.beginPath();
    c.moveTo(0, -S * 0.56);
    c.bezierCurveTo(S * 0.38, -S * 0.92, S * 1.02, -S * 0.66, S * 0.96, S * 0.06);
    c.bezierCurveTo(S * 0.9, S * 0.72, S * 0.42, S * 1.04, S * 0.17, S * 0.92);
    c.bezierCurveTo(S * 0.08, S * 0.87, -S * 0.08, S * 0.87, -S * 0.17, S * 0.92);
    c.bezierCurveTo(-S * 0.42, S * 1.04, -S * 0.9, S * 0.72, -S * 0.96, S * 0.06);
    c.bezierCurveTo(-S * 1.02, -S * 0.66, -S * 0.38, -S * 0.92, 0, -S * 0.56);
    c.fillStyle = linear(c, 0, -S, 0, S, [[0, "#FF5A52"], [1, "#C8102E"]]);
    c.fill();
    oval(c, -S * 0.46, -S * 0.2, S * 0.17, S * 0.3, "rgba(255, 255, 255, 0.38)", 0.35);
    c.restore();
    line(c, x, y - S * 0.54, x + S * 0.08, y - S * 0.92, "#6B4226", S * 0.09);
    c.beginPath();
    c.moveTo(x + S * 0.08, y - S * 0.74);
    c.quadraticCurveTo(x + S * 0.3, y - S * 1.12, x + S * 0.66, y - S * 0.98);
    c.quadraticCurveTo(x + S * 0.46, y - S * 0.64, x + S * 0.08, y - S * 0.74);
    c.fillStyle = "#4CAF50";
    c.fill();
  }

  // Strichmännchen-Gelenke (Papier): Linie mit leichtem Handzittern
  function wobbly(c, x1, y1, x2, y2, r, color, width = 2.4) {
    c.strokeStyle = color; c.lineWidth = width; c.lineCap = "round";
    c.beginPath();
    c.moveTo(x1 + (r() - 0.5) * 2, y1 + (r() - 0.5) * 2);
    c.quadraticCurveTo((x1 + x2) / 2 + (r() - 0.5) * 5, (y1 + y2) / 2 + (r() - 0.5) * 5,
      x2 + (r() - 0.5) * 2, y2 + (r() - 0.5) * 2);
    c.stroke();
  }

  // --- Farben --------------------------------------------------------------------------------------

  const night = {
    tagline: ["Ich zähle noch schnell die Sterne.", "Die Eule hat alles im Blick.", "Nachtschicht im Arbeitsspeicher."],
    ink: "#E6E7EA", inkMuted: "#9DA3C7",
    start(W, H) {
      const r = random(7);
      return {stars: Array.from({length: 150}, () => ({x: r() * W, y: r() * H * 0.78, s: 0.5 + r() * 1.5, p: r() * TAU}))};
    },
    draw(c, W, H, t, s) {
      fill(c, 0, 0, W, H, linear(c, 0, 0, 0, H, [[0, "#0B0D26"], [0.7, "#1E2150"], [1, "#2C2A63"]]));
      for (const star of s.stars) {
        c.globalAlpha = 0.45 + 0.55 * Math.abs(Math.sin(t * 1.3 + star.p));
        fill(c, star.x, star.y, star.s, star.s, "#FFFFFF");
      }
      c.globalAlpha = 1;
      const mx = W * 0.8, my = H * 0.16, R = 40;
      c.beginPath();
      c.arc(mx, my, R, -Math.PI / 2, Math.PI / 2, true);
      c.quadraticCurveTo(mx - R * 0.42, my, mx, my - R);
      c.fillStyle = "#F6E7A8";
      c.fill();
      // Sternbild entsteht Linie für Linie
      const pts = [[0.14, 0.34], [0.26, 0.2], [0.42, 0.28], [0.54, 0.14], [0.66, 0.26], [0.74, 0.42], [0.58, 0.48], [0.44, 0.42]]
        .map(([x, y]) => [x * W, y * H]);
      const drawn = (t * 1.1) % (pts.length + 3);
      for (let i = 1; i < pts.length; i++) {
        const f = clamp(drawn - i + 1);
        if (f > 0) line(c, pts[i - 1][0], pts[i - 1][1], lerp(pts[i - 1][0], pts[i][0], f), lerp(pts[i - 1][1], pts[i][1], f), "rgba(180, 190, 255, 0.75)", 1.4);
      }
      pts.forEach(([x, y], i) => disc(c, x, y, drawn >= i ? 4 : 2, drawn >= i ? "#FFF6C8" : "#8089C9"));
      // Sternschnuppe alle paar Sekunden
      const shoot = cycle(t, 5.5);
      if (shoot < 0.16) {
        const f = shoot / 0.16, x = lerp(W * 0.1, W * 0.62, f), y = lerp(H * 0.06, H * 0.3, f);
        line(c, x - 70, y - 30, x, y, `rgba(255, 255, 255, ${1 - f})`, 2);
      }
      // Hügel und Eule
      c.beginPath();
      c.moveTo(0, H);
      for (let x = 0; x <= W; x += 12) c.lineTo(x, H * 0.76 + Math.sin(x * 0.012) * 20 + Math.sin(x * 0.034) * 8);
      c.lineTo(W, H);
      c.fillStyle = "#0A0B1C";
      c.fill();
      const ox = W * 0.2, oy = H * 0.7;
      oval(c, ox, oy, 26, 33, "#3A2E5C");
      shape(c, [[ox - 22, oy - 26], [ox - 16, oy - 44], [ox - 4, oy - 29]], "#3A2E5C");
      shape(c, [[ox + 22, oy - 26], [ox + 16, oy - 44], [ox + 4, oy - 29]], "#3A2E5C");
      const blink = cycle(t, 3.4) > 0.94, look = Math.sin(t * 0.8) * 3;
      for (const side of [-1, 1]) {
        disc(c, ox + side * 11, oy - 13, 10, "#FFE9A8");
        if (blink) line(c, ox + side * 4, oy - 13, ox + side * 18, oy - 13, "#3A2E5C", 3);
        else disc(c, ox + side * 11 + look, oy - 13, 4.5, "#14152A");
      }
      shape(c, [[ox - 4, oy - 6], [ox + 4, oy - 6], [ox, oy + 2]], "#E9B44C");
    },
  };

  const graphite = {
    tagline: ["Skizziere gerade den Assistenten.", "Bitte nicht wackeln.", "Radiergummi liegt bereit."],
    start(W, H) {
      const x = W / 2, y = H * 0.4, u = Math.min(W, H) / 7;
      const pts = list => list.map(([a, b]) => [x + a * u, y + b * u]);
      const circle = (cx, cy, r) => Array.from({length: 22}, (_, i) => [cx + Math.cos(i / 21 * TAU) * r, cy + Math.sin(i / 21 * TAU) * r]);
      const lines = [
        [[-1.5, -1], [1.5, -1], [1.5, 1.3], [-1.5, 1.3], [-1.5, -1]], [[0, -1], [0, -1.7]], circle(0, -1.9, 0.2),
        circle(-0.65, 0, 0.36), circle(0.65, 0, 0.36), circle(-0.65, 0, 0.1), circle(0.65, 0, 0.1),
        [[-0.8, 0.8], [-0.4, 0.95], [0.4, 0.95], [0.8, 0.8]], [[-1.5, 0], [-2, 0], [-2, 0.7]], [[1.5, 0], [2, 0], [2, 0.7]],
        ...[0, 1, 2, 3, 4, 5, 6].map(i => [[-1.4 + i * 0.28, 1.25], [-1.1 + i * 0.28, 0.96]]),
      ].map(pts);
      return {lines, total: linesLength(lines)};
    },
    draw(c, W, H, t, s) {
      fill(c, 0, 0, W, H, "#141416");
      const rub = cycle(t, 11);
      const length = s.total * clamp(rub / 0.72);
      c.globalAlpha = rub > 0.88 ? 1 - (rub - 0.88) / 0.12 : 1;
      const tip = drawLines(c, s.lines, length, "#C9CED8", 2);
      c.globalAlpha = 1;
      c.save();
      c.translate(tip[0], tip[1]);
      c.rotate(0.65);
      shape(c, [[0, 0], [-7, -20], [7, -20]], "#E8D3B0");
      shape(c, [[0, 0], [-2.6, -7.5], [2.6, -7.5]], "#30323A");
      fill(c, -7, -130, 14, 110, "#D9A73C");
      fill(c, -7, -130, 4.5, 110, "#EBC15F");
      fill(c, -7, -146, 14, 16, "#B8BCC4");
      fill(c, -7, -164, 14, 18, "#E58B8B");
      c.restore();
    },
  };

  const light = {
    tagline: ["Moment, ich finde den Schalter.", "Die Motte freut sich schon.", "Gleich geht mir ein Licht auf."],
    ink: "#1C1E24", inkMuted: "#6E7280",
    draw(c, W, H, t) {
      const p = cycle(t, 4.2), on = p > 0.16 && !(p > 0.19 && p < 0.23);
      const x = W / 2, y = H * 0.38;
      fill(c, 0, 0, W, H, on ? "#FFFBEA" : "#C9CCD3");
      if (on) {
        for (let i = 0; i < 14; i++) {
          const a = i / 14 * TAU + t * 0.25, inner = 90, outer = 138 + Math.sin(t * 5 + i) * 12;
          line(c, x + Math.cos(a) * inner, y + Math.sin(a) * inner, x + Math.cos(a) * outer, y + Math.sin(a) * outer, "#F5C542", 5);
        }
        disc(c, x, y, 78, "rgba(255, 224, 110, 0.35)");
      }
      line(c, x, 0, x, y - 86, "#30323A", 3);
      fill(c, x - 22, y - 92, 44, 34, "#6E7280");
      for (let i = 0; i < 3; i++) fill(c, x - 24, y - 86 + i * 10, 48, 4, "#4C4F58");
      disc(c, x, y, 62, on ? "#FFE36E" : "#ECEEF1");
      c.lineWidth = 3; c.strokeStyle = on ? "#E0A92B" : "#A8ACB5"; c.beginPath(); c.arc(x, y, 62, 0, TAU); c.stroke();
      c.beginPath();
      c.moveTo(x - 16, y - 58);
      c.lineTo(x - 16, y - 6);
      for (let i = 0; i < 4; i++) c.lineTo(x - 16 + (i + 1) * 8, y + (i % 2 ? 2 : -14));
      c.lineTo(x + 16, y - 58);
      c.strokeStyle = on ? "#FF8A1E" : "#8B8F99";
      c.lineWidth = 2.5;
      c.stroke();
      // Zugschnur: wird am Anfang jedes Durchgangs gezogen
      const pull = p < 0.16 ? Math.sin(p / 0.16 * Math.PI) * 44 : 0;
      const swing = Math.sin(t * 3) * (p < 0.5 ? 12 * (1 - p * 2) : 0);
      const knobX = x + 96 + swing, knobY = y + 40 + pull;
      line(c, x + 96, 0, knobX, knobY, "#6E7280", 2);
      disc(c, knobX, knobY, 8, "#4F5FE8");
      // Motte: kreist bei Licht, sitzt im Dunkeln
      const a = t * 3.2, mx = on ? x + Math.cos(a) * 84 : x + 46, my = on ? y + Math.sin(a * 1.3) * 68 : y + 42;
      const flap = on ? 5 + Math.abs(Math.sin(t * 22)) * 7 : 4;
      oval(c, mx - flap * 0.7, my, flap, 4, "#8B6F52", -0.4);
      oval(c, mx + flap * 0.7, my, flap, 4, "#8B6F52", 0.4);
      oval(c, mx, my, 2, 6, "#3E3226");
    },
  };

  function tree(c, x, y, length, angle, depth, grown, sway) {
    const size = length * grown, ex = x + Math.cos(angle) * size, ey = y + Math.sin(angle) * size;
    line(c, x, y, ex, ey, depth > 3 ? "#5A4332" : "#3C8D6A", depth * 1.3 + 0.8);
    if (depth > 0) {
      tree(c, ex, ey, length * 0.74, angle - 0.42 + sway, depth - 1, grown, sway);
      tree(c, ex, ey, length * 0.74, angle + 0.42 + sway, depth - 1, grown, sway);
    } else if (grown > 0.8) {
      disc(c, ex, ey, 5.5, "#4FB58A");
    }
  }

  const forest = {
    tagline: ["Pflanze gerade ein paar Entscheidungsbäume.", "Glühwürmchen übernehmen die Beleuchtung.", "Gut Ding will Wurzeln haben."],
    ink: "#E3EAE6", inkMuted: "#8FB3A3",
    start(W, H) {
      const r = random(3);
      return {flies: Array.from({length: 26}, () => ({x: r() * W, y: H * (0.25 + r() * 0.55), p: r() * TAU, q: 0.4 + r()}))};
    },
    draw(c, W, H, t, s) {
      fill(c, 0, 0, W, H, linear(c, 0, 0, 0, H, [[0, "#0D1A17"], [1, "#16322A"]]));
      const ground = H * 0.82, time = t % 15;
      fill(c, 0, ground, W, H - ground, "#0B1512");
      const sway = Math.sin(t * 0.9) * 0.025;
      [[0.13, 44, 0], [0.34, 62, 0.9], [0.56, 74, 0.3], [0.78, 56, 1.5], [0.93, 38, 2.1]].forEach(([fx, size, delay]) => {
        tree(c, W * fx, ground, size, -Math.PI / 2, 6, ease(clamp((time - delay) / 4.5)), sway);
      });
      for (let i = 0; i < 6; i++) {
        const x = W * (0.08 + i * 0.17), y = ground + 10;
        fill(c, x - 2, y, 4, 8, "#D9CBB0");
        c.beginPath(); c.arc(x, y, 8, Math.PI, 0); c.fillStyle = "#C25555"; c.fill();
      }
      for (const fly of s.flies) {
        const x = fly.x + Math.sin(t * fly.q + fly.p) * 30, y = fly.y + Math.cos(t * fly.q * 0.8 + fly.p) * 22;
        const glow = 0.3 + 0.7 * Math.abs(Math.sin(t * 1.6 + fly.p));
        disc(c, x, y, 7, `rgba(240, 240, 120, ${glow * 0.2})`);
        disc(c, x, y, 2.2, `rgba(250, 250, 150, ${glow})`);
      }
    },
  };

  const sand = {
    tagline: ["Die Zeit rinnt. Das Modell auch.", "Das Kamel kennt den Weg.", "Nur noch ein paar Körnchen."],
    ink: "#EDE6E0", inkMuted: "#B7A898",
    draw(c, W, H, t) {
      fill(c, 0, 0, W, H, linear(c, 0, 0, 0, H, [[0, "#2A1A12"], [1, "#6B3C20"]]));
      disc(c, W * 0.8, H * 0.18, 48, "#E6B566");
      [[0.72, 34, "#8A5230"], [0.8, 26, "#A9683A"]].forEach(([fy, amp, color]) => {
        c.beginPath();
        c.moveTo(0, H);
        for (let x = 0; x <= W; x += 12) c.lineTo(x, H * fy + Math.sin(x * 0.012 + fy * 9) * amp);
        c.lineTo(W, H);
        c.fillStyle = color;
        c.fill();
      });
      // Kamel zieht vorbei
      const walk = (t * 16) % (W + 140) - 70, cy = H * 0.74, step = Math.sin(t * 4);
      c.fillStyle = "#3A2415";
      oval(c, walk, cy, 30, 14, "#3A2415");
      oval(c, walk - 8, cy - 14, 13, 13, "#3A2415");
      oval(c, walk + 10, cy - 12, 11, 11, "#3A2415");
      line(c, walk + 28, cy - 2, walk + 44, cy - 22, "#3A2415", 7);
      oval(c, walk + 50, cy - 24, 10, 6, "#3A2415");
      [-22, -12, 12, 22].forEach((dx, i) => line(c, walk + dx, cy + 8, walk + dx + (i % 2 ? step : -step) * 7, cy + 32, "#3A2415", 4));
      // Sanduhr: läuft, wird gedreht, läuft wieder
      const p = cycle(t, 7), flow = clamp(p / 0.85), flip = ease(clamp((p - 0.88) / 0.12));
      const x = W / 2, y = H * 0.38, w = 62, h = 96;
      c.save();
      c.translate(x, y);
      c.rotate(flip * Math.PI);
      const level = 1 - flow;
      if (level > 0.01) shape(c, [[-w * 0.82 * level - 6, -h * 0.72 * level - 4], [w * 0.82 * level + 6, -h * 0.72 * level - 4], [0, -2]], "#E6B566");
      if (flow > 0.01) shape(c, [[-w * 0.9, h - 2], [w * 0.9, h - 2], [w * 0.9 * (1 - flow * 0.45), h - 24 * flow], [0, h - 62 * flow], [-w * 0.9 * (1 - flow * 0.45), h - 24 * flow]], "#E6B566");
      if (p < 0.85) {
        line(c, 0, 0, 0, h - 62 * flow, "#E6B566", 2.5);
        for (let i = 0; i < 6; i++) fill(c, Math.sin(i * 3 + t * 30) * 3 - 1, ((t * 220 + i * 18) % (h - 62 * flow)), 2, 2, "#FFE0A8");
      }
      c.lineWidth = 4; c.strokeStyle = "rgba(255, 255, 255, 0.72)"; c.lineJoin = "round"; c.beginPath();
      c.moveTo(-w, -h); c.quadraticCurveTo(-w, -30, -6, 0); c.quadraticCurveTo(-w, 30, -w, h);
      c.lineTo(w, h); c.quadraticCurveTo(w, 30, 6, 0); c.quadraticCurveTo(w, -30, w, -h); c.closePath(); c.stroke();
      card(c, -w - 14, -h - 14, w * 2 + 28, 14, 4, "#8A5230");
      card(c, -w - 14, h, w * 2 + 28, 14, 4, "#8A5230");
      c.restore();
    },
  };

  const classic = {
    tagline: ["Das Uhrwerk wird aufgezogen.", "Handarbeit seit 1.0.", "Ölen nicht vergessen."],
    draw(c, W, H, t) {
      fill(c, 0, 0, W, H, "#2E2E2E");
      const x = W / 2, y = H * 0.32, a = t * 0.7;
      gear(c, x - 66, y, 86, 16, a, "#8AB4F8", "#2E2E2E");
      gear(c, x + 66.5, y + 2, 56, 10, -a * 1.6 + 0.16, "#E0B050", "#2E2E2E");
      gear(c, x + 104, y + 96, 50, 9, a * 1.78 + 0.1, "#AAAAAA", "#2E2E2E");
      // Zifferblatt auf dem großen Rad, Zeiger laufen viel zu schnell
      disc(c, x - 66, y, 40, "#F1F1F1");
      for (let i = 0; i < 12; i++) {
        const b = i / 12 * TAU;
        disc(c, x - 66 + Math.cos(b) * 33, y + Math.sin(b) * 33, 1.8, "#383838");
      }
      const minute = t * 2.4, hour = t * 0.2;
      line(c, x - 66, y, x - 66 + Math.sin(minute) * 30, y - Math.cos(minute) * 30, "#383838", 2.5);
      line(c, x - 66, y, x - 66 + Math.sin(hour) * 20, y - Math.cos(hour) * 20, "#C25555", 3.5);
      // Pendel
      const swing = Math.sin(t * 2.6) * 0.42, px = x - 66, py = y + 92, L = 148;
      line(c, px, py, px + Math.sin(swing) * L, py + Math.cos(swing) * L, "#AAAAAA", 4);
      disc(c, px + Math.sin(swing) * L, py + Math.cos(swing) * L, 24, "#E0B050");
      disc(c, px + Math.sin(swing) * L - 6, py + Math.cos(swing) * L - 7, 7, "#F5D693");
      disc(c, px, py, 6, "#F1F1F1");
    },
  };

  // --- Modern --------------------------------------------------------------------------------------

  const apple = {
    tagline: ["Das beste Laden, das wir je gemacht haben.", "Laden. Neu gedacht.", "Jetzt auch in Titan-Grau.",
      "Adapter separat erhältlich.", "Mit 40 % mehr Ladebalken.", "Der Wurm ist eine Funktion."],
    ink: "#1D1D1F", inkMuted: "#6E6E73",
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, "#FFFFFF");
      const x = W / 2, y = H * 0.36 + Math.sin(t * 1.4) * 5, S = 92;
      oval(c, x, H * 0.36 + S * 1.28, S * 0.7 - Math.sin(t * 1.4) * 4, 8, "rgba(0, 0, 0, 0.08)");
      fruit(c, x, y, S);
      // Der Wurm schaut mal raus - mit Designerbrille
      const p = cycle(t, 5), out = ease(clamp(p / 0.15)) * ease(clamp((1 - p) / 0.15));
      const wx = x + S * 0.62, wy = y + S * 0.06;
      if (out > 0.01) {
        const look = Math.sin(t * 2.4) * 3;
        c.save();
        c.translate(wx, wy);
        c.scale(out, out);
        c.lineCap = "round";
        line(c, 0, 0, 22, -16, "#8BC34A", 16);
        disc(c, 26, -20, 14, "#9CCC65");
        for (const dx of [20, 33]) {
          disc(c, dx, -22, 6.5, "#FFFFFF");
          disc(c, dx + look * 0.5, -22, 2.8, "#1D1D1F");
          c.lineWidth = 1.6; c.strokeStyle = "#1D1D1F"; c.beginPath(); c.arc(dx, -22, 6.5, 0, TAU); c.stroke();
        }
        line(c, 26, -22, 27, -22, "#1D1D1F", 1.6);
        c.beginPath(); c.arc(27, -14, 4, 0.2, Math.PI - 0.2); c.lineWidth = 1.6; c.strokeStyle = "#1D1D1F"; c.stroke();
        c.restore();
        disc(c, wx, wy, 9 * out, "#6B1420");
      }
      // Hauchdünner Balken und Drehrädchen
      const bar = H * 0.62;
      card(c, x - 90, bar, 180, 4, 2, "#E3E3E6");
      card(c, x - 90, bar, Math.max(6, 180 * info.smooth), 4, 2, "#1D1D1F");
      for (let i = 0; i < 12; i++) {
        const a = i / 12 * TAU, shade = (i + Math.floor(t * 12)) % 12;
        c.lineCap = "round";
        line(c, x + Math.cos(a) * 8, bar + 30 + Math.sin(a) * 8, x + Math.cos(a) * 14, bar + 30 + Math.sin(a) * 14, `rgba(29, 29, 31, ${0.12 + shade / 13})`, 2.2);
      }
    },
  };

  const appleDark = {
    ink: "#F5F5F7", inkMuted: "#98989D",
    start(W, H) {
      const r = random(11);
      return {heads: Array.from({length: 26}, (_, i) => ({x: (i + 0.5) / 26 * W, y: H * 0.86 + r() * 16, p: r() * TAU}))};
    },
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, "#000000");
      const x = W / 2, y = H * 0.5;
      // Folie: ein Satz, viel Schwarz
      const slides = ["Noch eine Sache …", "Es lädt einfach.", "Wir nennen es: Laden.", "Das ist bahnbrechend.", "Ab 1.499 €.", "Applaus, bitte."];
      const slide = t % 3.2 / 3.2;
      c.globalAlpha = ease(clamp(slide * 6)) * ease(clamp((1 - slide) * 6));
      write(c, pick(slides, t, 3.2), x, H * 0.14, "600 34px -apple-system, 'Segoe UI Variable Display', 'Segoe UI', sans-serif", "#F5F5F7");
      c.globalAlpha = 1;
      // Scheinwerfer, Podest, die drehende Frucht
      const sway = Math.sin(t * 0.7) * 26;
      shape(c, [[x + sway - 8, 0], [x + sway + 8, 0], [x + 118, y + 66], [x - 118, y + 66]], linear(c, 0, 0, 0, y + 66, [[0, "rgba(255, 255, 255, 0.28)"], [1, "rgba(255, 255, 255, 0.03)"]]));
      oval(c, x, y + 66, 118, 18, "rgba(255, 255, 255, 0.14)");
      c.fillStyle = "#2C2C2E";
      c.fillRect(x - 56, y + 58, 112, 56);
      oval(c, x, y + 58, 56, 12, "#3A3A3C");
      const bump = Math.abs(Math.sin(t * 1.5));
      fruit(c, x, y - 12 - bump * 8, 58, 0.62 + 0.38 * Math.abs(Math.cos(t * 1.1)));
      // Publikum, das immer begeisterter wird
      for (const head of s.heads) {
        const jump = Math.max(0, Math.sin(t * 7 + head.p)) * (4 + info.smooth * 12);
        disc(c, head.x, head.y - jump, 13, "#1C1C1E");
        oval(c, head.x, head.y + 24 - jump, 20, 18, "#1C1C1E");
      }
      card(c, x - 90, H * 0.78, 180, 3, 1.5, "#38383A");
      card(c, x - 90, H * 0.78, Math.max(6, 180 * info.smooth), 3, 1.5, "#F5F5F7");
    },
  };

  const glass = {
    tagline: ["Poliere die Oberflächen.", "Vorsicht, durchsichtig.", "Bitte nicht antippen, gibt Fingerabdrücke."],
    start(W, H) {
      const r = random(5);
      return {bubbles: Array.from({length: 15}, () => ({x: r() * W, y: r() * H, r: 16 + r() * 46, v: 8 + r() * 24, p: r() * TAU}))};
    },
    draw(c, W, H, t, s, info) {
      for (const b of s.bubbles) {
        const y = H + b.r - ((b.y + t * b.v) % (H + b.r * 2)), x = b.x + Math.sin(t * 0.6 + b.p) * 16;
        const g = c.createRadialGradient(x - b.r * 0.35, y - b.r * 0.4, b.r * 0.1, x, y, b.r);
        g.addColorStop(0, "rgba(255, 255, 255, 0.55)");
        g.addColorStop(0.7, "rgba(255, 255, 255, 0.10)");
        g.addColorStop(1, "rgba(255, 255, 255, 0.45)");
        disc(c, x, y, b.r, g);
      }
      // Glasröhre, die sich mit Fortschritt und einer Welle füllt
      const w = Math.min(W * 0.62, 340), h = 66, x = (W - w) / 2, y = H * 0.4;
      card(c, x, y, w, h, h / 2, "rgba(255, 255, 255, 0.34)");
      c.save();
      round(c, x + 5, y + 5, w - 10, h - 10, (h - 10) / 2);
      c.clip();
      const level = x + 5 + (w - 10) * Math.max(0.1, info.smooth);
      c.beginPath();
      c.moveTo(x, y + h);
      c.lineTo(x, y);
      c.lineTo(level, y);
      for (let py = y; py <= y + h; py += 4) c.lineTo(level + Math.sin(py * 0.16 + t * 4) * 7, py);
      c.lineTo(x, y + h);
      c.fillStyle = "rgba(61, 58, 158, 0.72)";
      c.fill();
      c.restore();
      card(c, x + 16, y + 9, w - 32, 10, 5, "rgba(255, 255, 255, 0.72)");
      c.lineWidth = 2; c.strokeStyle = "rgba(255, 255, 255, 0.85)"; round(c, x, y, w, h, h / 2); c.stroke();
    },
  };

  const clay = {
    fps: 10,   // ruckelt mit Absicht: Stop-Motion
    tagline: ["Wird von Hand geknetet.", "Keine Sorge, das tut ihm nicht weh.", "24 Bilder? Wir nehmen zehn."],
    ink: "#3C2A57", inkMuted: "#86739F",
    draw(c, W, H, t) {
      fill(c, 0, 0, W, H, "#F1E7FF");
      const jitter = () => (Math.random() - 0.5) * 1.6;
      const x = W / 2 + jitter(), ground = H * 0.6, time = t % 6.4;
      fill(c, 0, ground + 46, W, H, "#E4D3FA");
      let sx = 1, sy = 1, lift = 0, flat = false;
      if (time < 3.6) {
        const jump = (time % 1.2) / 1.2, h = Math.sin(jump * Math.PI);
        lift = h * 118;
        sy = jump < 0.1 || jump > 0.92 ? 0.74 : 0.92 + h * 0.2;
        sx = 2 - sy;
      } else if (time < 5.2) {
        const rolled = (time - 3.6) / 0.7;
        if (rolled > 0.4) { flat = true; sy = 0.16; sx = 1.75; }
      } else {
        const pop = clamp((time - 5.2) / 0.5);
        flat = pop < 0.4;
        sy = flat ? 0.16 : 1 + Math.sin(pop * Math.PI * 2.5) * 0.3 * (1 - pop);
        sx = flat ? 1.75 : 2 - sy;
      }
      const R = 64, cy = ground + 46 - R * sy - lift;
      oval(c, x, ground + 46, R * sx * (1 - lift / 300), 11, "rgba(150, 110, 200, 0.3)");
      oval(c, x, cy, R * sx, R * sy, "#FF8FB8");
      oval(c, x - R * 0.2 * sx, cy - R * 0.32 * sy, R * 0.5 * sx, R * 0.34 * sy, "#FFB8D4");
      for (let i = 0; i < 4; i++) {
        c.lineWidth = 1.4; c.strokeStyle = "rgba(200, 80, 130, 0.45)"; c.beginPath();
        c.arc(x + R * 0.42 * sx, cy + R * 0.3 * sy, 5 + i * 4, 3.4, 5.4); c.stroke();
      }
      if (flat) {
        for (const side of [-1, 1]) {
          const ex = x + side * 34, ey = cy - 2;
          line(c, ex - 7, ey - 5, ex + 7, ey + 5, "#3C2A57", 3.5);
          line(c, ex + 7, ey - 5, ex - 7, ey + 5, "#3C2A57", 3.5);
        }
      } else {
        for (const side of [-1, 1]) {
          oval(c, x + side * 24 * sx, cy - 8 * sy, 13 * sx, 15 * sy, "#FFFFFF");
          disc(c, x + side * 22 * sx, cy - 6 * sy, 6.5, "#3C2A57");
        }
        c.beginPath(); c.arc(x, cy + 18 * sy, 11 * sx, 0.2, Math.PI - 0.2); c.lineWidth = 3.5; c.strokeStyle = "#3C2A57"; c.stroke();
      }
      // Das Nudelholz kommt
      if (time >= 3.4 && time < 4.8) {
        const f = (time - 3.4) / 1.4, px = lerp(-120, W + 120, f), py = ground + 46 - (flat ? 38 : 110);
        card(c, px - 26, py - 90, 52, 200, 24, "#C89B6A");
        card(c, px - 8, py - 118, 16, 34, 7, "#A87C4F");
        card(c, px - 8, py + 104, 16, 34, 7, "#A87C4F");
        fill(c, px - 16, py - 80, 10, 180, "#DDB98D");
      }
    },
  };

  const material = {
    tagline: ["Form folgt Stimmung.", "Tonal und entspannt.", "Elevation: emotional."],
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, "#FEF7FF");
      const x = W / 2, y = H * 0.38, kinds = [3, 5, 8, 12, 6];
      const step = t / 1.1, i = Math.floor(step), f = ease(step - i);
      const k1 = kinds[i % kinds.length], k2 = kinds[(i + 1) % kinds.length];
      const blob = (R, depth, rotation, color) => {
        c.beginPath();
        for (let n = 0; n <= 96; n++) {
          const a = n / 96 * TAU;
          const r = R * (1 + depth * lerp(Math.cos(k1 * a), Math.cos(k2 * a), f));
          c.lineTo(x + Math.cos(a + rotation) * r, y + Math.sin(a + rotation) * r);
        }
        c.closePath();
        c.fillStyle = color;
        c.fill();
      };
      blob(128, 0.08, -t * 0.32, "#ECE6F0");
      blob(96, 0.12, t * 0.55, "#D0BCFF");
      blob(62, 0.16, -t * 1.05, "#6750A4");
      disc(c, x, y, 14, "#FFFFFF");
      const bar = H * 0.68, w = Math.min(W * 0.66, 340), left = x - w / 2;
      card(c, left, bar, w, 6, 3, "#E8DEF8");
      const front = cycle(t, 1.7), a = left + w * ease(clamp(front * 1.6 - 0.3)), b = left + w * ease(clamp(front * 1.6));
      card(c, a, bar, Math.max(6, b - a), 6, 3, "#6750A4");
      card(c, left, bar + 14, w * info.smooth, 3, 1.5, "#B69DF8");
    },
  };

  const depth = {
    tagline: ["Tiefe wird nachgeladen.", "Rendere die dritte Dimension.", "Z-Puffer wird poliert."],
    ink: "#E8ECF8", inkMuted: "#8E98B8",
    draw(c, W, H, t) {
      fill(c, 0, 0, W, H, linear(c, 0, 0, 0, H, [[0, "#25325E"], [0.62, "#0B0F1A"]]));
      const horizon = H * 0.62, cx = W / 2;
      c.lineWidth = 1;
      c.strokeStyle = "rgba(91, 140, 255, 0.4)";
      c.beginPath();
      for (let i = -14; i <= 14; i++) { c.moveTo(cx + i * 10, horizon); c.lineTo(cx + i * 150, H); }
      for (let i = 0; i < 12; i++) {
        const z = ((i + t * 1.5) % 12) / 12, y = horizon + (H - horizon) * z * z;
        c.moveTo(0, y); c.lineTo(W, y);
      }
      c.stroke();
      const size = Math.min(W, H) * 0.2, ay = t * 0.85, ax = 0.55 + Math.sin(t * 0.6) * 0.25;
      const bob = Math.sin(t * 1.6) * 10, cy = H * 0.36 + bob;
      const rotate = ([x, y, z]) => {
        const x1 = x * Math.cos(ay) - z * Math.sin(ay), z1 = x * Math.sin(ay) + z * Math.cos(ay);
        const y1 = y * Math.cos(ax) - z1 * Math.sin(ax), z2 = y * Math.sin(ax) + z1 * Math.cos(ax);
        return [x1, y1, z2];
      };
      const project = ([x, y, z]) => { const p = 4.2 / (4.2 + z); return [cx + x * size * p, cy + y * size * p]; };
      const faces = [[[-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], [[1, -1, -1], [-1, -1, -1], [-1, 1, -1], [1, 1, -1]],
        [[-1, -1, -1], [-1, -1, 1], [-1, 1, 1], [-1, 1, -1]], [[1, -1, 1], [1, -1, -1], [1, 1, -1], [1, 1, 1]],
        [[-1, -1, -1], [1, -1, -1], [1, -1, 1], [-1, -1, 1]], [[-1, 1, 1], [1, 1, 1], [1, 1, -1], [-1, 1, -1]]];
      const orbit = i => { const a = t * 1.7 + i * TAU / 3; return {depth: Math.sin(a) * 2.1, point: project(rotate([Math.cos(a) * 2.1, Math.sin(a * 2) * 0.5, Math.sin(a) * 2.1]))}; };
      const ball = o => {
        const [x, y] = o.point, g = c.createRadialGradient(x - 4, y - 5, 1, x, y, 14);
        g.addColorStop(0, "#BFE9FF"); g.addColorStop(1, "#1F6BB5");
        disc(c, x, y, 14, g);
      };
      const orbs = [0, 1, 2].map(orbit);
      orbs.filter(o => o.depth > 0).forEach(ball);
      oval(c, cx, horizon + 44, size * 1.1, 14, "rgba(0, 0, 0, 0.4)");
      faces.map(face => ({face: face.map(rotate)})).map(item => ({...item, z: item.face.reduce((sum, p) => sum + p[2], 0) / 4}))
        .sort((a, b) => b.z - a.z).forEach(({face}) => {
          const [a, b, d] = face;
          const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = d[0] - a[0], vy = d[1] - a[1], vz = d[2] - a[2];
          const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
          if (nz > 0) return;   // Rückseite
          const light = 0.3 + 0.7 * clamp((nx * -0.35 + ny * -0.75 + nz * -0.55) / 4);   // Licht von oben links vorn
          shape(c, face.map(project), `rgb(${Math.round(lerp(28, 120, light))}, ${Math.round(lerp(58, 175, light))}, ${Math.round(lerp(130, 255, light))})`);
          c.lineWidth = 1.5; c.strokeStyle = "rgba(190, 215, 255, 0.55)"; c.stroke();
        });
      orbs.filter(o => o.depth <= 0).forEach(ball);
    },
  };

  const neumorph = {
    tagline: ["Drücke jede Taste einzeln.", "Sanfter Druck, große Wirkung.", "Alles aus einem Material."],
    ink: "#3A4256", inkMuted: "#7D869A",
    start() {
      const size = 96, make = paint => {
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = size;
        paint(canvas.getContext("2d"), size / 2);
        return canvas;
      };
      const raised = make((c, m) => {
        c.fillStyle = "#E3E7EE";
        c.shadowBlur = 12;
        c.shadowColor = "#BFC5CF"; c.shadowOffsetX = c.shadowOffsetY = 6; c.beginPath(); c.arc(m, m, 28, 0, TAU); c.fill();
        c.shadowColor = "#FFFFFF"; c.shadowOffsetX = c.shadowOffsetY = -6; c.beginPath(); c.arc(m, m, 28, 0, TAU); c.fill();
      });
      const pressed = make((c, m) => {
        const g = c.createLinearGradient(m - 28, m - 28, m + 28, m + 28);
        g.addColorStop(0, "#C8CDD6"); g.addColorStop(1, "#F4F6FA");
        c.fillStyle = g; c.beginPath(); c.arc(m, m, 28, 0, TAU); c.fill();
        c.fillStyle = "#DFE3EA"; c.beginPath(); c.arc(m + 1, m + 1, 24, 0, TAU); c.fill();
      });
      return {raised, pressed};
    },
    draw(c, W, H, t, s) {
      fill(c, 0, 0, W, H, "#E3E7EE");
      const gap = 92, n = 4, ox = W / 2 - gap * (n - 1) / 2, oy = H * 0.4 - gap * (n - 1) / 2;
      for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
          const d = Math.hypot(i - 1.5, j - 1.5), press = clamp(Math.sin(d * 1.5 - t * 3.2) * 1.5 - 0.3);
          const x = ox + i * gap, y = oy + j * gap;
          c.globalAlpha = 1 - press;
          c.drawImage(s.raised, x - 48, y - 48);
          c.globalAlpha = press;
          c.drawImage(s.pressed, x - 48, y - 48);
          c.globalAlpha = 1;
          if (press > 0.4) disc(c, x, y, 5, `rgba(90, 108, 240, ${press})`);
        }
      }
    },
  };

  // --- Retro -----------------------------------------------------------------------------------------

  // Gameboy: eigene Fallende-Blöcke-Animation mit eigenen Steinformen, spielt sich selbst.
  const FALLING_PIECES = [
    [[1, 1, 1]], [[1, 0], [1, 1]], [[1, 1], [1, 1], [1, 0]], [[1, 1]], [[1, 1, 1], [0, 1, 0], [0, 1, 0]],
    [[1, 0, 1], [1, 1, 1]], [[0, 1, 0], [1, 1, 1], [0, 1, 0]],
  ];
  const FIELD_COLS = 10, FIELD_ROWS = 14;
  const rotations = piece => {
    const seen = new Map();
    let shapeNow = piece;
    for (let i = 0; i < 4; i++) {
      seen.set(JSON.stringify(shapeNow), shapeNow);
      shapeNow = shapeNow[0].map((_, x) => shapeNow.map(row => row[x]).reverse());
    }
    return Array.from(seen.values());
  };
  const fits = (grid, piece, px, py) => piece.every((row, y) => row.every((cell, x) => !cell
    || (px + x >= 0 && px + x < FIELD_COLS && py + y < FIELD_ROWS && (py + y < 0 || !grid[py + y][px + x]))));
  function dropRow(grid, piece, px) {
    let py = -piece.length;
    while (fits(grid, piece, px, py + 1)) py++;
    return py;
  }
  function score(grid, piece, px, py) {
    const test = grid.map(row => row.slice());
    piece.forEach((row, y) => row.forEach((cell, x) => { if (cell && py + y >= 0) test[py + y][px + x] = 1; }));
    const lines = test.filter(row => row.every(Boolean)).length;
    let holes = 0, bump = 0, last = null, peak = 0;
    for (let x = 0; x < FIELD_COLS; x++) {
      let top = FIELD_ROWS;
      for (let y = FIELD_ROWS - 1; y >= 0; y--) if (test[y][x]) top = y;
      for (let y = top; y < FIELD_ROWS; y++) if (!test[y][x]) holes++;
      const height = FIELD_ROWS - top;
      peak = Math.max(peak, height);
      if (last !== null) bump += Math.abs(height - last);
      last = height;
    }
    return lines * 8 - holes * 7 - bump * 1.1 - peak * 1.6;
  }
  function nextPiece(s) {
    const piece = s.upcoming;
    s.upcoming = FALLING_PIECES[Math.floor(s.r() * FALLING_PIECES.length)];
    let best = null;
    for (const form of rotations(piece)) {
      for (let px = 0; px <= FIELD_COLS - form[0].length; px++) {
        const py = dropRow(s.grid, form, px);
        if (py < 0) continue;
        const value = score(s.grid, form, px, py);
        if (!best || value > best.value) best = {value, form, px};
      }
    }
    if (!best) { s.wipe = 0; return; }
    s.piece = best.form;
    s.target = best.px;
    s.px = Math.floor((FIELD_COLS - best.form[0].length) / 2);
    s.py = -best.form.length;
  }
  function advance(s) {
    if (s.wipe !== null) {
      if (++s.wipe > FIELD_ROWS) { s.grid = s.grid.map(() => Array(FIELD_COLS).fill(0)); s.wipe = null; nextPiece(s); }
      return;
    }
    if (s.flash) {
      if (--s.flash.ticks <= 0) {
        s.flash.rows.forEach(y => { s.grid.splice(y, 1); s.grid.unshift(Array(FIELD_COLS).fill(0)); });
        s.lines += s.flash.rows.length;
        s.flash = null;
        nextPiece(s);
      }
      return;
    }
    if (!s.piece) return;
    if (s.px !== s.target && fits(s.grid, s.piece, s.px + Math.sign(s.target - s.px), s.py)) s.px += Math.sign(s.target - s.px);
    if (fits(s.grid, s.piece, s.px, s.py + 1)) { s.py++; return; }
    s.piece.forEach((row, y) => row.forEach((cell, x) => { if (cell && s.py + y >= 0) s.grid[s.py + y][s.px + x] = 1; }));
    s.piece = null;
    const rows = [];
    s.grid.forEach((row, y) => { if (row.every(Boolean)) rows.push(y); });
    if (rows.length) s.flash = {rows, ticks: 8};
    else nextPiece(s);
  }

  const gameboy = {
    screen: true,
    pixel: 2,
    tagline: null,
    ink: "#0F380F", inkMuted: "#306230",
    start() {
      const s = {r: random(21), grid: Array.from({length: FIELD_ROWS}, () => Array(FIELD_COLS).fill(0)), lines: 0,
        piece: null, flash: null, wipe: null, last: 0, upcoming: FALLING_PIECES[0]};
      nextPiece(s);
      return s;
    },
    draw(c, W, H, t, s) {
      const dark = "#0F380F", mid = "#306230", lightest = "#9BBC0F", soft = "#8BAC0F";
      s.last = Math.max(s.last, t - 2);   // nach geschlossenem Popup nicht alles nachspielen
      while (t - s.last > 0.09) { advance(s); s.last += 0.09; }
      fill(c, 0, 0, W, H, lightest);
      const cell = Math.floor((H - 44) / FIELD_ROWS), width = cell * FIELD_COLS, height = cell * FIELD_ROWS;
      const ox = Math.floor((W - width) / 2) - 26, oy = 10;
      fill(c, ox - 3, oy - 3, width + 6, height + 6, dark);
      fill(c, ox, oy, width, height, soft);
      const block = (x, y, color) => {
        fill(c, ox + x * cell, oy + y * cell, cell - 1, cell - 1, color);
        fill(c, ox + x * cell + 2, oy + y * cell + 2, cell - 7, 2, lightest);
      };
      for (let y = 0; y < FIELD_ROWS; y++) {
        const flashing = s.flash && s.flash.rows.includes(y) && s.flash.ticks % 2;
        for (let x = 0; x < FIELD_COLS; x++) {
          if (s.wipe !== null && y >= FIELD_ROWS - s.wipe) block(x, y, mid);
          else if (s.grid[y][x] && !flashing) block(x, y, dark);
        }
      }
      if (s.piece) s.piece.forEach((row, y) => row.forEach((on, x) => { if (on && s.py + y >= 0) block(s.px + x, s.py + y, mid); }));
      const panel = ox + width + 12, font = "bold 11px Consolas, 'Lucida Console', monospace";
      write(c, "GLEICH", panel, 16, font, dark, "left");
      fill(c, panel, 26, 50, 50, dark);
      fill(c, panel + 2, 28, 46, 46, soft);
      const small = 9, shapeNow = s.upcoming, sx = panel + 25 - shapeNow[0].length * small / 2, sy = 51 - shapeNow.length * small / 2;
      shapeNow.forEach((row, y) => row.forEach((on, x) => { if (on) fill(c, sx + x * small, sy + y * small, small - 1, small - 1, dark); }));
      write(c, "REIHEN", panel, 94, font, dark, "left");
      write(c, String(s.lines).padStart(3, "0"), panel, 110, "bold 15px Consolas, monospace", dark, "left");
    },
  };

  const win95 = {
    ink: "#FFFFFF", inkMuted: "#C0D0FF",
    tagline: ["Bitte legen Sie Diskette 12 von 340 ein.", "Haben Sie schon einen Kaffee?", "Entspannen Sie sich, während das Setup arbeitet."],
    draw(c, W, H, t, s, info) {
      const bands = 24;
      for (let i = 0; i < bands; i++) fill(c, 0, Math.floor(i * H / bands), W, Math.ceil(H / bands) + 1, `rgb(0, 0, ${Math.round(190 - i * 7)})`);
      write(c, "PDA Setup", 24, 40, "italic bold 36px 'Times New Roman', serif", "#000000", "left");
      write(c, "PDA Setup", 22, 38, "italic bold 36px 'Times New Roman', serif", "#FFFFFF", "left");
      const w = Math.min(W - 40, 420), h = 214, x = Math.floor((W - w) / 2), y = Math.floor(H * 0.25);
      const bevel = (bx, by, bw, bh, face, inset) => {
        fill(c, bx, by, bw, bh, inset ? "#808080" : "#FFFFFF");
        fill(c, bx + 1, by + 1, bw - 1, bh - 1, inset ? "#FFFFFF" : "#404040");
        fill(c, bx + 1, by + 1, bw - 2, bh - 2, face);
      };
      bevel(x, y, w, h, "#C0C0C0");
      fill(c, x + 3, y + 3, w - 6, 20, linear(c, x, 0, x + w, 0, [[0, "#000080"], [1, "#1084D0"]]));
      write(c, "Kopiere Dateien …", x + 8, y + 13, "bold 12px Tahoma, sans-serif", "#FFFFFF", "left");
      const folder = (fx, fy) => {
        fill(c, fx, fy + 6, 22, 7, "#E0C050");
        fill(c, fx, fy + 11, 52, 34, "#FFD966");
        fill(c, fx, fy + 11, 52, 2, "#FFF2B8");
        fill(c, fx, fy + 44, 52, 2, "#807030");
      };
      const fy = y + 40, left = x + 34, right = x + w - 86;
      folder(left, fy);
      folder(right, fy);
      for (let i = 0; i < 3; i++) {
        const f = cycle(t + i * 0.42, 1.26), px = lerp(left + 34, right + 8, f), py = fy + 20 - Math.sin(f * Math.PI) * 46;
        fill(c, px, py, 18, 22, "#FFFFFF");
        fill(c, px, py, 18, 1, "#404040");
        fill(c, px + 17, py, 1, 22, "#404040");
        for (let l = 0; l < 3; l++) fill(c, px + 3, py + 5 + l * 5, 11, 1, "#000080");
      }
      const files = ["neuronen.dll", "gedanken.sys", "smalltalk.vxd", "kaffee.drv", "prompt32.exe", "halluzination.tmp"];
      const estimates = ["2 Minuten", "37 Sekunden", "4 Stunden", "11 Tage", "1 Minute", "gleich"];
      write(c, `Quelle: C:\\PDA\\${pick(files, t, 0.7)}`, x + 16, y + 108, "12px Tahoma, sans-serif", "#000000", "left");
      write(c, `Verbleibend: ${pick(estimates, t, 1.9)}`, x + 16, y + 128, "12px Tahoma, sans-serif", "#000000", "left");
      const bx = x + 16, by = y + 148, bw = w - 32, bh = 22;
      bevel(bx, by, bw, bh, "#FFFFFF", true);
      const blocks = Math.floor((bw - 8) / 14 * Math.max(0.04, info.smooth));
      for (let i = 0; i < blocks; i++) fill(c, bx + 4 + i * 14, by + 4, 12, bh - 8, "#000080");
      bevel(x + w - 96, y + h - 34, 80, 24, "#C0C0C0");
      write(c, "Abbrechen", x + w - 56, y + h - 22, "12px Tahoma, sans-serif", "#808080");
    },
  };

  const BOOT_LINES = ["Mounting /dev/kaffee", "Starte Neuronen (1 von 86 Mrd.)", "Prüfe, ob Ollama wach ist", "Lade smalltalk.ko",
    "Sortiere Tokens nach Größe", "Bestechung der GPU", "Entferne Halluzinationen (3 übrig)", "Wecke Daemons, höflich",
    "Prüfe Ironie-Modul", "Synchronisiere Gedanken", "Sage dem Lüfter Bescheid", "Lese Anleitung (zum ersten Mal)"];

  const terminal = {
    tagline: null,
    showsStep: true,
    ink: "#5CFF85", inkMuted: "#2FA552",
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, "#050A06");
      const font = "13px 'Cascadia Mono', Consolas, monospace", lh = 19, count = Math.floor(t / 0.42);
      const rows = Math.floor((H - 130) / lh);
      for (let i = Math.max(0, count - rows), y = 22; i < count; i++, y += lh) {
        const text = BOOT_LINES[i % BOOT_LINES.length], failed = i % 7 === 5;
        write(c, "[", 14, y, font, "#2FA552", "left");
        write(c, failed ? " WARN " : "  OK  ", 23, y, font, failed ? "#E8FF5C" : "#5CFF85", "left");
        write(c, "]", 73, y, font, "#2FA552", "left");
        write(c, text, 92, y, font, "#B6FFC8", "left");
      }
      const y = H - 92, spin = "|/-\\"[Math.floor(t * 8) % 4];
      write(c, `pda@localhost:~$ ${info.label || "fertig"} ${spin}`, 14, y, font, "#5CFF85", "left");
      if (cycle(t, 1) < 0.5) fill(c, 14, y + 12, 9, 15, "#5CFF85");
      for (let py = 0; py < H; py += 3) fill(c, 0, py, W, 1, "rgba(0, 0, 0, 0.22)");
    },
  };

  const vapor = {
    tagline: ["ＡＥＳＴＨＥＴＩＣ ＬＯＡＤＩＮＧ", "Fahrt in den Sonnenuntergang.", "Kassette wird zurückgespult."],
    ink: "#FFE8FB", inkMuted: "#F7A8E6",
    draw(c, W, H, t) {
      const horizon = Math.floor(H * 0.58), cx = W / 2;
      fill(c, 0, 0, W, horizon, linear(c, 0, 0, 0, horizon, [[0, "#1A0533"], [0.55, "#6B1A7B"], [1, "#FF7A45"]]));
      const R = 104, sy = horizon - 66;
      c.save();
      c.beginPath(); c.arc(cx, sy, R, 0, TAU); c.clip();
      fill(c, cx - R, sy - R, R * 2, R * 2, linear(c, 0, sy - R, 0, sy + R, [[0, "#FFFB96"], [1, "#FF71CE"]]));
      for (let i = 0; i < 7; i++) {
        const y = sy + 8 + i * 15 + (t * 12) % 15;
        fill(c, cx - R, y, R * 2, 3 + i * 1.3, "#6B1A7B");
      }
      c.restore();
      for (const side of [-1, 1]) {
        shape(c, [[cx + side * W * 0.5, horizon], [cx + side * W * 0.42, horizon - 58], [cx + side * W * 0.3, horizon - 18], [cx + side * W * 0.2, horizon - 44], [cx + side * W * 0.1, horizon]], "#2B0B4F");
        const px = cx + side * W * 0.37, sway = Math.sin(t * 1.2) * 4;
        c.lineCap = "round";
        line(c, px, horizon + 6, px + side * -14 + sway, horizon - 136, "#14021F", 7);
        for (let i = 0; i < 6; i++) {
          const a = i / 5 * Math.PI, tipX = px + side * -14 + sway + Math.cos(a) * 58, tipY = horizon - 136 - Math.sin(a) * 18 + 22;
          c.beginPath(); c.moveTo(px + side * -14 + sway, horizon - 136);
          c.quadraticCurveTo((px + side * -14 + sway + tipX) / 2, horizon - 166, tipX, tipY);
          c.lineWidth = 5; c.strokeStyle = "#14021F"; c.stroke();
        }
      }
      fill(c, 0, horizon, W, H - horizon, "#14021F");
      c.lineWidth = 1.6; c.strokeStyle = "#FF71CE"; c.beginPath();
      for (let i = -16; i <= 16; i++) { c.moveTo(cx + i * 22, horizon); c.lineTo(cx + i * 150, H); }
      for (let i = 0; i < 12; i++) {
        const z = ((i + t * 2.4) % 12) / 12, y = horizon + (H - horizon) * z * z;
        c.moveTo(0, y); c.lineTo(W, y);
      }
      c.stroke();
      // Auto von hinten
      const sway = Math.sin(t * 0.9) * 22, x = cx + sway, y = H - 142;
      oval(c, x, y + 58, 96, 12, "rgba(0, 0, 0, 0.55)");
      shape(c, [[x - 62, y + 2], [x + 62, y + 2], [x + 44, y - 42], [x - 44, y - 42]], "#3D1358");
      shape(c, [[x - 50, y], [x + 50, y], [x + 37, y - 34], [x - 37, y - 34]], linear(c, 0, y - 34, 0, y, [[0, "#FF9AD5"], [1, "#6B1A7B"]]));
      card(c, x - 92, y, 184, 46, 8, "#22082F");
      fill(c, x - 88, y + 8, 176, 3, "#01CDFE");
      card(c, x - 86, y + 16, 44, 14, 3, "#FF003C");
      card(c, x + 42, y + 16, 44, 14, 3, "#FF003C");
      card(c, x - 26, y + 18, 52, 14, 2, "#FFFB96");
      write(c, "PDA", x, y + 26, "bold 11px 'Trebuchet MS', sans-serif", "#22082F");
      fill(c, x - 88, y + 46, 30, 16, "#050008");
      fill(c, x + 58, y + 46, 30, 16, "#050008");
    },
  };

  const newspaper = {
    tagline: null,
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, "#F3EEE3");
      const headlines = ["PDA FÄHRT HOCH", "EXPERTEN RATLOS: WANN FERTIG?", "MODELL LÄDT! FAMILIE BESTÜRZT", "LESERBRIEFE: ES DAUERT", "KOMMENTAR: GUT DING WILL WEILE", "SPORT: LADEBALKEN GEWINNT"];
      c.lineWidth = 1;
      write(c, "Der Tägliche Agent", W / 2, 42, "900 32px 'Old English Text MT', 'Times New Roman', serif", "#161616");
      fill(c, 24, 66, W - 48, 3, "#161616");
      fill(c, 24, 71, W - 48, 1, "#161616");
      const headline = pick(headlines, t, 2.6), p = cycle(t, 2.6), size = headline.length > 22 ? 25 : 34;
      c.save();
      c.translate(W / 2, 112);
      const spin = 1 - ease(clamp(p * 5));
      c.rotate(spin * -5);
      c.scale(1 - spin, 1 - spin);
      write(c, headline, 0, 0, `900 ${size}px 'Times New Roman', Georgia, serif`, "#161616");
      c.restore();
      // Druckerpresse: Papierbahn läuft zwischen den Walzen hindurch
      const y = H * 0.56, shift = (t * 150) % 110;
      fill(c, 0, y - 12, W, 24, "#F8F4EB");
      fill(c, 0, y - 13, W, 1, "#161616");
      fill(c, 0, y + 12, W, 1, "#161616");
      for (let x = -110 + shift; x < W; x += 110) {
        fill(c, x + 10, y - 8, 70, 5, "#161616");
        for (let l = 0; l < 2; l++) fill(c, x + 10, y + l * 5, 88, 2, "#8E887A");
      }
      for (const [dx, big] of [[-1, 74], [1, 74]]) {
        const rx = W / 2 + dx * 84;
        for (const side of [-1, 1]) {
          const ry = y + side * (big + 12), angle = t * 2.4 * side;
          disc(c, rx, ry, big, "#2A2A2A");
          disc(c, rx, ry, big - 8, "#555048");
          for (let i = 0; i < 6; i++) {
            const a = angle + i / 6 * TAU;
            line(c, rx, ry, rx + Math.cos(a) * (big - 10), ry + Math.sin(a) * (big - 10), "#2A2A2A", 6);
          }
          disc(c, rx, ry, 11, "#D4C9B0");
        }
      }
      // Stapel fertiger Zeitungen wächst
      const pile = Math.floor(t * 2) % 26, px = W - 86, base = H * 0.86;
      for (let i = 0; i < pile; i++) {
        fill(c, px + (i % 3) * 2, base - i * 5, 70, 4, i % 2 ? "#F8F4EB" : "#E9E2D3");
        fill(c, px + (i % 3) * 2, base - i * 5 + 4, 70, 1, "#161616");
      }
      fill(c, 24, H * 0.86 + 6, W - 48, 2, "#161616");
      fill(c, 40, H * 0.86 - 4, 150 * info.smooth, 8, "#7A1F1F");
    },
  };

  const deco = {
    tagline: ["Bitte einsteigen.", "Nächster Halt: Sprachmodell.", "Der Liftboy poliert noch die Knöpfe."],
    ink: "#F3E9D2", inkMuted: "#BFA76A",
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, "#0E0E0E");
      const gold = "#D4AF37", x = W / 2, y = H * 0.36, R = Math.min(W * 0.36, 170);
      for (let i = 0; i < 34; i++) {
        const a = i / 34 * TAU + t * 0.04;
        line(c, x, y, x + Math.cos(a) * 800, y + Math.sin(a) * 800, i % 2 ? "rgba(212, 175, 55, 0.18)" : "rgba(212, 175, 55, 0.06)", 7);
      }
      // Stockwerksanzeige wie im Hotelaufzug
      c.beginPath(); c.arc(x, y, R + 20, Math.PI, 0); c.lineTo(x + R + 20, y + 16); c.lineTo(x - R - 20, y + 16); c.closePath();
      c.fillStyle = "#141414"; c.fill(); c.lineWidth = 2; c.strokeStyle = gold; c.stroke();
      c.beginPath(); c.arc(x, y, R - 16, Math.PI, 0); c.lineWidth = 1; c.stroke();
      for (let i = 0; i <= 8; i++) {
        const a = Math.PI + i / 8 * Math.PI;
        write(c, String(i + 1), x + Math.cos(a) * (R - 2), y + Math.sin(a) * (R - 2), "16px Georgia, serif", gold);
      }
      const a = Math.PI + (Math.max(0, info.smooth * 0.8 + 0.08 + Math.sin(t * 2.3) * 0.05 + cycle(t, 9) * 0.12)) * Math.PI;
      shape(c, [[x + Math.cos(a) * (R - 26), y + Math.sin(a) * (R - 26)], [x + Math.cos(a + 1.5) * 9, y + Math.sin(a + 1.5) * 9], [x + Math.cos(a - 1.5) * 9, y + Math.sin(a - 1.5) * 9]], gold);
      disc(c, x, y, 13, gold);
      disc(c, x, y, 5, "#0E0E0E");
      // Aufzugtüren mit Chevrons
      const doorW = Math.min(W * 0.28, 130), top = y + 26, doorH = H * 0.8 - top;
      for (const side of [-1, 1]) {
        const dx = side === -1 ? x - doorW - 1 : x + 1;
        fill(c, dx, top, doorW, doorH, "#1B1B1B");
        c.lineWidth = 1; c.strokeStyle = gold; c.strokeRect(dx + 4, top + 4, doorW - 8, doorH - 8);
        for (let i = 0; i < 5; i++) {
          const cy = top + 34 + i * ((doorH - 60) / 4), mid = dx + doorW / 2;
          shape(c, [[mid - 26, cy + 12], [mid, cy - 12], [mid + 26, cy + 12]], gold, false);
        }
      }
    },
  };

  // --- Ausdrucksstark ----------------------------------------------------------------------------------

  const maximal = {
    tagline: ["MEHR IST MEHR!", "Warum laden, wenn man feiern kann?", "Noch ein bisschen lauter, bitte!"],
    start(W, H) {
      const r = random(9), colors = ["#FF4FA3", "#FFD23F", "#7CF5FF", "#FF8A3D", "#B5FF6B"];
      return {bits: Array.from({length: 62}, () => ({x: r() * W, y: r() * H, v: 40 + r() * 80, a: r() * TAU, s: 6 + r() * 12, c: colors[Math.floor(r() * 5)], q: r() * 4 - 2}))};
    },
    draw(c, W, H, t, s) {
      const star = (x, y, R, spikes, rot, color) => {
        c.beginPath();
        for (let i = 0; i < spikes * 2; i++) {
          const a = i / spikes * Math.PI + rot, r = i % 2 ? R * 0.45 : R;
          c.lineTo(x + Math.cos(a) * r, y + Math.sin(a) * r);
        }
        c.closePath(); c.fillStyle = color; c.fill();
      };
      star(W * 0.2, H * 0.2, 80 + Math.sin(t * 4) * 12, 12, t * 0.9, "#FF4FA3");
      star(W * 0.82, H * 0.3, 104 + Math.cos(t * 3) * 12, 9, -t * 1.2, "#7CF5FF");
      star(W * 0.3, H * 0.68, 60, 7, t * 1.6, "#B5FF6B");
      star(W * 0.78, H * 0.68, 74, 14, -t, "#FF8A3D");
      for (const b of s.bits) {
        const y = (b.y + t * b.v) % H;
        c.save(); c.translate(b.x + Math.sin(t + b.a) * 22, y); c.rotate(b.a + t * b.q);
        fill(c, -b.s / 2, -b.s / 4, b.s, b.s / 2, b.c);
        c.restore();
      }
      const word = "LADEN!!!", size = Math.min(W / 5.6, 92), gap = size * 0.66, colors = ["#FFD23F", "#FF4FA3", "#7CF5FF", "#FF8A3D"];
      for (let i = 0; i < word.length; i++) {
        const x = W / 2 + (i - (word.length - 1) / 2) * gap, y = H * 0.42 + Math.sin(t * 5 + i * 0.8) * 26;
        c.save(); c.translate(x, y); c.rotate(Math.sin(t * 3.4 + i) * 0.28);
        const font = `italic 900 ${size}px Georgia, serif`;
        write(c, word[i], 5, 5, font, "#2B0B3F");
        write(c, word[i], 0, 0, font, colors[(i + Math.floor(t * 3)) % 4]);
        c.restore();
      }
    },
  };

  const brutal = {
    tagline: null,
    ink: "#000000", inkMuted: "#000000",
    draw(c, W, H, t) {
      const period = 1.5, p = cycle(t, period), hits = Math.floor(t / period);
      const slam = p < 0.12 ? ease(p / 0.12) : p < 0.3 ? 1 : 1 - ease((p - 0.3) / 0.7);
      const shake = p > 0.12 && p < 0.26 ? Math.sin(p * 200) * 8 : 0;
      fill(c, 0, 0, W, H, "#FFF4D6");
      c.save();
      c.translate(0, shake);
      fill(c, 0, H * 0.62, W, H, "#FFD600");
      fill(c, 0, H * 0.62, W, 6, "#000000");
      const words = ["WARTE.", "NOCH NICHT.", "IMMER NOCH NICHT.", "FAST.", "NEIN.", "GLEICH.", "ES LÄDT.", "GEDULD."];
      const word = words[hits % words.length];
      const size = Math.min(84, (W - 40) / word.length * 1.42);
      const font = `900 ${size}px 'Arial Black', 'Segoe UI Black', sans-serif`;
      write(c, word, W / 2 + 6, H * 0.74 + 6, font, "#FF6B35");
      write(c, word, W / 2, H * 0.74, font, "#000000");
      // Balken: jeder Schlag treibt einen Klotz hinein
      const cols = 12, size2 = Math.floor((W - 48) / cols), count = hits % (cols + 1);
      for (let i = 0; i < cols; i++) {
        const x = 24 + i * size2, y = H * 0.54;
        fill(c, x + 4, y + 4, size2 - 4, 30, i < count ? "#000000" : "transparent");
        fill(c, x, y, size2 - 4, 30, i < count ? "#90A8FF" : "#FFF4D6");
        c.lineWidth = 3; c.strokeStyle = "#000000"; c.strokeRect(x, y, size2 - 4, 30);
      }
      // Hammer
      const hx = 24 + Math.min(count, cols - 1) * size2 + size2 / 2, top = 24, hit = H * 0.54 - 60, hy = lerp(top, hit, slam);
      fill(c, hx - 11, -20, 22, hy + 22, "#000000");
      fill(c, hx - 64 + 7, hy + 7, 128, 60, "#000000");
      fill(c, hx - 64, hy, 128, 60, "#FF6B35");
      c.lineWidth = 4; c.strokeStyle = "#000000"; c.strokeRect(hx - 64, hy, 128, 60);
      write(c, "KI", hx, hy + 32, "900 32px 'Arial Black', sans-serif", "#000000");
      if (p > 0.1 && p < 0.26) {
        for (let i = 0; i < 8; i++) {
          const a = Math.PI + i / 7 * Math.PI, inner = 74, outer = 118;
          line(c, hx + Math.cos(a) * inner, H * 0.54 + Math.sin(a) * 18, hx + Math.cos(a) * outer, H * 0.54 + Math.sin(a) * 44, "#000000", 5);
        }
      }
      c.restore();
    },
  };

  function comicRobot(c, x, y, S, t, scared) {
    c.save();
    c.translate(x, y);
    fill(c, -S * 0.9, -S * 0.1, S * 0.5, S * 0.34, "#E63946");   // Umhang
    card(c, -S * 0.5, -S * 0.5, S, S, S * 0.16, "#4CC9F0");
    c.lineWidth = 4; c.strokeStyle = "#111111"; round(c, -S * 0.5, -S * 0.5, S, S, S * 0.16); c.stroke();
    line(c, 0, -S * 0.5, 0, -S * 0.82, "#111111", 4);
    disc(c, 0, -S * 0.88, S * 0.1, "#FFD23F");
    for (const side of [-1, 1]) {
      disc(c, side * S * 0.2, -S * 0.1, S * 0.16, "#FFFFFF");
      disc(c, side * S * 0.2 + Math.sin(t * 3) * S * 0.05, -S * 0.1, S * 0.07, "#111111");
    }
    if (scared) { c.lineWidth = 4; c.strokeStyle = "#111111"; c.beginPath(); c.arc(0, S * 0.32, S * 0.13, Math.PI + 0.3, -0.3); c.stroke(); }
    else fill(c, -S * 0.22, S * 0.18, S * 0.44, S * 0.08, "#111111");
    c.restore();
  }
  function comicBurst(c, x, y, R, text, color, size, rot) {
    c.save();
    c.translate(x, y);
    c.rotate(rot);
    const pts = (r) => { c.beginPath(); for (let i = 0; i < 28; i++) { const a = i / 14 * Math.PI, l = i % 2 ? r * 0.62 : r; c.lineTo(Math.cos(a) * l * 1.3, Math.sin(a) * l * 0.9); } c.closePath(); };
    pts(R + 7); c.fillStyle = "#111111"; c.fill();
    pts(R); c.fillStyle = color; c.fill();
    write(c, text, 3, 3, `${size}px Impact, 'Arial Black', sans-serif`, "#111111");
    write(c, text, 0, 0, `${size}px Impact, 'Arial Black', sans-serif`, "#FFFFFF");
    c.restore();
  }

  const comic = {
    fps: 16,
    tagline: null,
    ink: "#111111", inkMuted: "#333333",
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, "#FFF3B0");
      const panel = (x, y, w, h, color, paint) => {
        c.save();
        c.beginPath(); c.rect(x, y, w, h); c.clip();
        fill(c, x, y, w, h, color);
        paint();
        c.restore();
        c.lineWidth = 5; c.strokeStyle = "#111111"; c.strokeRect(x, y, w, h);
      };
      const m = 14, w = W - m * 2, top = H * 0.46;
      panel(m, m, w, top, "#FFFFFF", () => {
        const cx = m + w * 0.5, cy = m + top * 0.55;
        for (let i = 0; i < 28; i++) {
          const y = m + (i * 37 + 8) % top, len = 60 + (i * 53) % 120, x = (m + w + 200) - ((t * 900 + i * 131) % (w + 400));
          line(c, x, y, x + len, y, "#CFCFCF", 3);
        }
        comicRobot(c, cx + Math.sin(t * 2) * 24, cy + Math.sin(t * 3.3) * 14, 92, t, false);
        const word = pick(["WUSCH!", "ZACK!", "KAWUMM!", "SSSST!"], t, 1.3);
        const pop = clamp(cycle(t, 1.3) * 6);
        comicBurst(c, m + w * 0.8, m + top * 0.33, 58 * pop, word, "#E63946", 34 * pop, -0.15);
        card(c, m + 12, m + 12, 234, 30, 2, "#FFD23F");
        c.lineWidth = 3; c.strokeStyle = "#111111"; c.strokeRect(m + 12, m + 12, 234, 30);
        write(c, "Unterdessen, im Arbeitsspeicher …", m + 20, m + 27, "bold 13px 'Comic Sans MS', cursive", "#111111", "left");
      });
      const y2 = m * 2 + top, h2 = H - y2 - 90, half = (w - m) / 2;
      panel(m, y2, half, h2, "#4CC9F0", () => {
        for (let i = 0; i < 18; i++) {
          const a = i / 18 * TAU + t * 0.4;
          shape(c, [[m + half / 2, y2 + h2 / 2], [m + half / 2 + Math.cos(a) * 400, y2 + h2 / 2 + Math.sin(a) * 400], [m + half / 2 + Math.cos(a + 0.17) * 400, y2 + h2 / 2 + Math.sin(a + 0.17) * 400]], "#8FDCF4");
        }
        comicRobot(c, m + half / 2, y2 + h2 * 0.56, 96, t, true);
        const drop = cycle(t, 1.1);
        oval(c, m + half / 2 + 62, y2 + h2 * 0.3 + drop * 40, 6, 10, "#FFFFFF");
      });
      panel(m * 2 + half, y2, half, h2, "#FFD23F", () => {
        for (let x = m * 2 + half; x < W; x += 9) for (let y = y2; y < y2 + h2; y += 9) disc(c, x, y, 1.8, "rgba(230, 57, 70, 0.4)");
        const x = m * 2 + half + 20, bw = half - 40, by = y2 + h2 * 0.6;
        fill(c, x, by, bw, 26, "#FFFFFF");
        fill(c, x, by, bw * Math.max(0.05, info.smooth), 26, "#E63946");
        c.lineWidth = 4; c.strokeStyle = "#111111"; c.strokeRect(x, by, bw, 26);
        write(c, "GLEICH GEHT'S LOS!", x + bw / 2, y2 + h2 * 0.32, "24px Impact, sans-serif", "#111111");
      });
    },
  };

  const bauhaus = {
    tagline: ["Triadisches Ballett, Akt 1.", "Form folgt Funktion. Funktion lädt.", "Kreis, Quadrat, Dreieck: bitte auf die Plätze."],
    ink: "#111111", inkMuted: "#444444",
    draw(c, W, H, t) {
      fill(c, 0, 0, W, H, "#F2EBDD");
      const red = "#E53935", blue = "#1E4FA0", yellow = "#F9C80E", black = "#111111";
      // Bühnenbild dreht sich in harten Viertelschritten
      const beat = t / 1.2, q = ease(beat - Math.floor(beat)), turn = (Math.floor(beat) + q) * Math.PI / 2;
      c.save(); c.translate(W * 0.2, H * 0.22); c.rotate(turn); fill(c, -56, -56, 112, 112, yellow); c.restore();
      c.save(); c.translate(W * 0.84, H * 0.56); c.rotate(-turn * 0.5); shape(c, [[0, -78], [68, 42], [-68, 42]], blue); c.restore();
      disc(c, W * 0.82, H * 0.17, 56, red);
      c.lineWidth = 4; c.strokeStyle = black;
      c.beginPath(); c.arc(W * 0.16, H * 0.66, 76, turn, turn + Math.PI * 1.3); c.stroke();
      line(c, 0, H * 0.82, W, H * 0.82, black, 6);
      for (let i = 0; i < 7; i++) line(c, 24 + i * 16, H * 0.82 - 34, 24 + i * 16, H * 0.82, black, 3);
      // Die Tänzerin / der Tänzer aus Grundformen
      const x = W / 2 + Math.sin(t * 1.3) * 42, foot = H * 0.82, tilt = Math.sin(t * 2.6) * 0.16;
      const skirtSpin = Math.cos(t * 3.2);
      for (const side of [-1, 1]) line(c, x + side * 12, foot - 92, x + side * (18 + Math.sin(t * 2.6) * side * 10), foot, black, 8);
      c.save();
      c.translate(x, foot - 150);
      c.rotate(tilt);
      c.beginPath(); c.ellipse(0, 46, Math.abs(skirtSpin) * 88 + 14, 22, 0, 0, TAU); c.fillStyle = yellow; c.fill();
      c.lineWidth = 3; c.strokeStyle = black; c.stroke();
      shape(c, [[-36, 42], [36, 42], [0, -46]], blue);
      for (const side of [-1, 1]) {
        c.save(); c.translate(side * 16, -14); c.rotate(side * (1 + Math.sin(t * 2.6 + side) * 0.7));
        fill(c, -5, 0, 10, 80, black); disc(c, 0, 86, 13, red); c.restore();
      }
      disc(c, 0, -68, 27, red);
      fill(c, -27, -71, 54, 6, black);
      c.restore();
    },
  };

  const cyber = {
    tagline: ["Verbinde mit dem neuronalen Netz.", "Firewall sagt: Du kommst hier nicht rein. Noch.", "Chrom wird nachgerüstet."],
    ink: "#FCEE0A", inkMuted: "#00F0FF",
    start(W, H) {
      const r = random(14), buildings = [];
      for (let x = 0; x < W;) {
        const w = 34 + r() * 56, h = H * (0.2 + r() * 0.42), lights = [];
        for (let i = 0; i < 26; i++) lights.push({x: 5 + r() * (w - 14), y: 8 + r() * (h - 16), p: r() * 7, c: r() > 0.6 ? "#FF003C" : r() > 0.5 ? "#00F0FF" : "#FCEE0A"});
        buildings.push({x, w, h, lights});
        x += w + 4;
      }
      return {buildings, rain: Array.from({length: 30}, (_, i) => ({x: (i + 0.5) / 30 * W, v: 90 + r() * 170, o: r() * H}))};
    },
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, "#0D0221");
      for (const b of s.buildings) {
        fill(c, b.x, H - b.h - 80, b.w, b.h + 80, "#160A3A");
        for (const l of b.lights) if (Math.sin(t * 0.9 + l.p) > -0.5) fill(c, b.x + l.x, H - b.h - 80 + l.y, 6, 3, l.c);
      }
      c.font = "12px Consolas, monospace"; c.textAlign = "center"; c.textBaseline = "middle";
      for (let i = 0; i < s.rain.length; i++) {
        const drop = s.rain[i], head = (drop.o + t * drop.v) % H;
        for (let k = 0; k < 7; k++) {
          c.fillStyle = k ? `rgba(0, 240, 255, ${0.55 - k * 0.07})` : "#E8F9FF";
          c.fillText("0123456789ABCDEF"[(i * 7 + k * 3 + Math.floor(t * 9)) % 16], drop.x, head - k * 14);
        }
      }
      // Zugriffsfenster mit Warnstreifen
      const w = Math.min(W - 48, 400), h = 150, x = (W - w) / 2, y = H * 0.27;
      shape(c, [[x, y], [x + w - 24, y], [x + w, y + 24], [x + w, y + h], [x + 24, y + h], [x, y + h - 24]], "#FCEE0A");
      c.save();
      c.beginPath(); c.rect(x + 10, y + 12, w - 44, 16); c.clip();
      for (let i = -20; i < w; i += 22) shape(c, [[x + i, y + 28], [x + i + 11, y + 28], [x + i + 27, y + 12], [x + i + 16, y + 12]], "#000000");
      c.restore();
      write(c, "ZUGRIFF: SPRACHMODELL", x + 16, y + 56, "bold 22px Bahnschrift, 'Segoe UI', sans-serif", "#000000", "left");
      const cells = 18, cw = (w - 32) / cells, filled = Math.floor(cells * Math.max(0.05, info.smooth));
      for (let i = 0; i < cells; i++) {
        fill(c, x + 16 + i * cw, y + 84, cw - 3, 22, i < filled ? "#FF003C" : "rgba(0, 0, 0, 0.18)");
        write(c, i < filled ? "FF" : "..", x + 16 + i * cw + (cw - 3) / 2, y + 95, "10px Consolas, monospace", i < filled ? "#FFFFFF" : "#000000");
      }
      write(c, `HASH 0x${Math.floor(t * 137 * 1021 % 0xFFFFFF).toString(16).toUpperCase().padStart(6, "0")}`, x + 40, y + 128, "12px Consolas, monospace", "#000000", "left");
      // kurzes Flackern
      if (cycle(t, 1.7) < 0.09) {
        for (let i = 0; i < 6; i++) {
          const gy = (i * 97 + Math.floor(t * 40) * 53) % H;
          fill(c, 0, gy, W, 4 + i * 2, i % 2 ? "rgba(255, 0, 60, 0.55)" : "rgba(0, 240, 255, 0.5)");
        }
      }
    },
  };

  // --- Besonders -----------------------------------------------------------------------------------------

  const eco = {
    fps: 0,
    showsStep: true,
    tagline: "Dieser Ladebildschirm steht still und spart Strom.",
    ink: "#000000", inkMuted: "#3A3A3A",
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, "#FFFFFF");
      const blockH = H * 0.5;
      fill(c, 0, 0, W, blockH, "#7ED957");
      fill(c, 0, blockH - 2, W, 2, "#000000");
      write(c, "Wächst pro Schritt um ein Blatt.", 24, 34, "700 15px 'Segoe UI', sans-serif", "#000000", "left");
      fill(c, W * 0.78 - 48, 24, 96, 96, "#00AEEF");
      c.lineWidth = 2; c.strokeStyle = "#000000"; c.strokeRect(W * 0.78 - 48, 24, 96, 96);
      for (let i = 0; i < 8; i++) {
        const a = i / 8 * TAU;
        line(c, W * 0.78 + Math.cos(a) * 26, 72 + Math.sin(a) * 26, W * 0.78 + Math.cos(a) * 38, 72 + Math.sin(a) * 38, "#000000", 2);
      }
      disc(c, W * 0.78, 72, 20, "#FFFFFF");
      c.lineWidth = 2; c.strokeStyle = "#000000"; c.beginPath(); c.arc(W * 0.78, 72, 20, 0, TAU); c.stroke();
      // Pflanze im Topf: ein Blatt pro fertigem Schritt
      const x = W * 0.34, base = blockH + 12, leaves = info.index + 1;
      line(c, x, base, x, base - 34 - leaves * 36, "#000000", 3);
      for (let i = 0; i < leaves; i++) {
        const side = i % 2 ? 1 : -1, y = base - 40 - i * 36;
        c.save(); c.translate(x, y); c.scale(side, 1);
        c.beginPath(); c.moveTo(0, 0); c.quadraticCurveTo(26, -32, 70, -22); c.quadraticCurveTo(48, 12, 0, 0); c.closePath();
        c.fillStyle = "#FFFFFF"; c.fill(); c.lineWidth = 2.5; c.strokeStyle = "#000000"; c.stroke();
        c.restore();
      }
      shape(c, [[x - 42, base - 6], [x + 42, base - 6], [x + 32, base + 58], [x - 32, base + 58]], "#E9B7A9");
      c.lineWidth = 2.5; c.strokeStyle = "#000000"; c.closePath(); c.stroke();
      info.labels.forEach((label, i) => {
        const y = blockH + 28 + i * 32, done = i < info.index, tx = W * 0.56;
        fill(c, tx, y - 9, 18, 18, done ? "#000000" : i === info.index ? "#FF5A1F" : "#FFFFFF");
        c.lineWidth = 2; c.strokeStyle = "#000000"; c.strokeRect(tx, y - 9, 18, 18);
        write(c, label, tx + 28, y, `${i === info.index ? 700 : 400} 12.5px 'Segoe UI', sans-serif`, "#000000", "left");
      });
    },
  };

  const paper = {
    fps: 8,    // das Zittern der Handzeichnung
    tagline: ["Ein kleines Daumenkino, nur für dich.", "Stefan schiebt das schon.", "Die Mathe-Hausaufgaben mussten warten."],
    ink: "#1F3A93", inkMuted: "#5B6B9A",
    draw(c, W, H, t, s, info) {
      const r = random(Math.floor(t * 8) * 31 + 1), ink = "#1F3A93", ground = H * 0.62, x = W * 0.42;
      const w = (x1, y1, x2, y2, color = ink, width = 2.4) => wobbly(c, x1, y1, x2, y2, r, color, width);
      // vorbeiziehende Kritzeleien
      const scroll = t * 60;
      for (let i = 0; i < 4; i++) {
        const dx = W + 70 - ((scroll + i * 230) % (W + 140)), dy = H * 0.2 + (i % 2) * 50;
        for (let k = 0; k < 3; k++) {
          c.beginPath();
          c.arc(dx + k * 22 - 22 + (r() - 0.5) * 2, dy + (r() - 0.5) * 2, 15 + (k === 1 ? 7 : 0), 2.6, 0.5);
          c.lineWidth = 2; c.strokeStyle = ink; c.stroke();
        }
      }
      for (let i = 0; i < 6; i++) {
        const fx = W + 40 - ((scroll * 2.4 + i * 130) % (W + 80));
        w(fx, ground, fx, ground - 18, "#2E7D32", 2);
        for (let k = 0; k < 5; k++) {
          const a = k / 5 * TAU;
          c.beginPath(); c.arc(fx + Math.cos(a) * 5, ground - 22 + Math.sin(a) * 5, 3.4, 0, TAU);
          c.lineWidth = 1.5; c.strokeStyle = "#C62828"; c.stroke();
        }
      }
      w(0, ground, W, ground);
      // Felsbrocken mit "KI" drauf
      const rock = x + 118, R = 74, spin = t * 1.6;
      c.beginPath();
      for (let i = 0; i <= 18; i++) {
        const a = i / 18 * TAU, wob = R + Math.sin(i * 2.7) * 7 + (r() - 0.5) * 2.5;
        c.lineTo(rock + Math.cos(a) * wob, ground - R + Math.sin(a) * wob);
      }
      c.closePath(); c.fillStyle = "#FFFEF9"; c.fill(); c.lineWidth = 2.6; c.strokeStyle = ink; c.stroke();
      c.save(); c.translate(rock, ground - R); c.rotate(spin); write(c, "KI", 0, 0, "bold 44px 'Segoe Print', 'Comic Sans MS', cursive", "#C62828"); c.restore();
      // Strichmännchen schiebt
      const stride = Math.sin(t * 6), hip = [x - 20, ground - 62], neck = [x + 4, ground - 106], hand = [rock - R - 2, ground - 98];
      w(hip[0], hip[1], neck[0], neck[1]);
      c.beginPath(); c.arc(x + 12 + (r() - 0.5), ground - 124 + (r() - 0.5), 18, 0, TAU); c.fillStyle = "#FFFEF9"; c.fill(); c.lineWidth = 2.4; c.strokeStyle = ink; c.stroke();
      disc(c, x + 18, ground - 128, 2, ink);
      w(x + 10, ground - 116, x + 22, ground - 115);
      w(neck[0], neck[1], hand[0], hand[1]);
      w(neck[0], neck[1], hand[0] - 4, hand[1] + 26);
      w(hip[0], hip[1], hip[0] - 8 + stride * 22, ground);
      w(hip[0], hip[1], hip[0] - 8 - stride * 22, ground);
      // Schweißtropfen
      c.beginPath(); c.arc(x - 16 - cycle(t, 0.75) * 22, ground - 136 + cycle(t, 0.75) * 12, 3, 0, TAU); c.lineWidth = 1.5; c.strokeStyle = ink; c.stroke();
      // handschraffierter Fortschritt
      const left = W * 0.16, bw = W * 0.68, y = H * 0.74;
      c.lineWidth = 2; c.strokeStyle = ink; c.strokeRect(left, y, bw, 26);
      for (let hx = 0; hx < bw * Math.max(0.04, info.smooth); hx += 6) w(left + hx, y + 24, left + hx + 9, y + 2, "#C62828", 1.6);
    },
  };

  const blueprint = {
    tagline: ["Maßstab 1:1, ungefähr.", "Bitte nicht auf die Zeichnung abstellen.", "Toleranz: ± ein paar Sekunden."],
    ink: "#F2F7FF", inkMuted: "#A9C4EA",
    start(W, H) {
      const x = W / 2, y = H * 0.38, u = Math.min(W * 0.1, 44);
      const P = list => list.map(([a, b]) => [x + a * u, y + b * u]);
      const arc = (cx, cy, r, from, to, n = 18) => Array.from({length: n + 1}, (_, i) => {
        const a = lerp(from, to, i / n);
        return [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
      });
      const lines = [
        [[-2.3, -3], [2.3, -3], [2.3, 3], [-2.3, 3], [-2.3, -3]], [[-1.9, -2.6], [1.9, -2.6], [1.9, 1.1], [-1.9, 1.1], [-1.9, -2.6]],
        arc(-1, 2.05, 0.55, 0, TAU), arc(1, 2.05, 0.55, 0, TAU), [[-0.25, 1.75], [0.25, 1.75]], [[-0.25, 2.35], [0.25, 2.35]],
        [[-3.1, -3], [-2.5, -3]], [[-3.1, 3], [-2.5, 3]], [[-2.85, -2.85], [-2.85, 2.85]],
        [[-2.3, 3.8], [-2.3, 3.2]], [[2.3, 3.8], [2.3, 3.2]], [[-2.15, 3.55], [2.15, 3.55]],
        arc(0, -0.75, 1.1, 0, TAU, 28), [[-1.5, -0.75], [1.5, -0.75]], [[0, -2.15], [0, 0.65]],
      ].map(P);
      return {lines, total: linesLength(lines), x, y, u};
    },
    draw(c, W, H, t, s) {
      const small = 12, big = 60;
      fill(c, 0, 0, W, H, "#1D4F91");
      c.lineWidth = 1; c.beginPath();
      c.strokeStyle = "rgba(255, 255, 255, 0.07)";
      for (let x = 0; x < W; x += small) { c.moveTo(x + 0.5, 0); c.lineTo(x + 0.5, H); }
      for (let y = 0; y < H; y += small) { c.moveTo(0, y + 0.5); c.lineTo(W, y + 0.5); }
      c.stroke();
      c.beginPath();
      c.strokeStyle = "rgba(255, 255, 255, 0.16)";
      for (let x = 0; x < W; x += big) { c.moveTo(x + 0.5, 0); c.lineTo(x + 0.5, H); }
      for (let y = 0; y < H; y += big) { c.moveTo(0, y + 0.5); c.lineTo(W, y + 0.5); }
      c.stroke();
      const p = cycle(t, 12), f = clamp(p / 0.8);
      const tip = drawLines(c, s.lines, s.total * f, "#F2F7FF", 1.6);
      if (f > 0.55) write(c, "120 mm", s.x - s.u * 3.3, s.y, "11px 'Cascadia Mono', Consolas, monospace", "#FFE08A");
      if (f > 0.8) write(c, "72 mm", s.x, s.y + s.u * 3.95, "11px 'Cascadia Mono', Consolas, monospace", "#FFE08A");
      line(c, tip[0], 0, tip[0], H, "rgba(255, 224, 138, 0.5)", 1);
      line(c, 0, tip[1], W, tip[1], "rgba(255, 224, 138, 0.5)", 1);
      disc(c, tip[0], tip[1], 4, "#FFE08A");
      // Schriftfeld
      const bw = 190, bh = 58, x = W - bw - 14, y = H - bh - 84;
      c.lineWidth = 1; c.strokeStyle = "#F2F7FF"; c.strokeRect(x, y, bw, bh);
      line(c, x, y + 22, x + bw, y + 22, "#F2F7FF", 1);
      line(c, x + 96, y + 22, x + 96, y + bh, "#F2F7FF", 1);
      write(c, "PERSONAL DIGITAL AGENT", x + 8, y + 12, "9.5px 'Cascadia Mono', Consolas, monospace", "#F2F7FF", "left");
      write(c, "BLATT 1/1", x + 8, y + 40, "9.5px 'Cascadia Mono', Consolas, monospace", "#A9C4EA", "left");
      write(c, "ENTWURF", x + 104, y + 40, "9.5px 'Cascadia Mono', Consolas, monospace", "#FFE08A", "left");
    },
  };

  const reader = {
    fps: 15,
    tagline: ["„Es war eine dunkle und stürmische Ladezeit.“", "Kapitel 1, in dem nicht viel passiert.", "Lesezeichen wird gesucht."],
    draw(c, W, H, t) {
      fill(c, 0, 0, W, H, "#F4ECD8");
      const x = W / 2, y = H * 0.17, pw = Math.min(W * 0.4, 210), ph = H * 0.56;
      const text = (px, seed, heading) => {
        const r = random(seed);
        if (heading) write(c, "Kapitel 1", px + pw / 2, y + 36, "italic 19px Georgia, serif", "#3B2F1E");
        for (let i = 0; i < 13; i++) {
          const ly = y + (heading ? 66 : 28) + i * 17, lw = (pw - 44) * (i === 12 ? 0.5 : 0.82 + r() * 0.18);
          if (ly < y + ph - 24) fill(c, px + 22, ly, lw, 3, "rgba(59, 47, 30, 0.45)");
        }
      };
      fill(c, x - pw - 8, y + ph - 2, pw * 2 + 16, 12, "#8B5A2B");
      for (const [px, seed] of [[x - pw, 3], [x, 8]]) {
        fill(c, px, y, pw, ph, "#FBF5E6");
        text(px, seed, seed === 3);
      }
      fill(c, x - 1, y, 2, ph, "rgba(59, 47, 30, 0.25)");
      // Seite wird umgeblättert
      const p = cycle(t, 2.6), f = ease(clamp(p / 0.55));
      if (f > 0 && f < 1) {
        const across = Math.cos(f * Math.PI), width = Math.abs(across) * pw, px = across > 0 ? x : x - width;
        const lift = Math.sin(f * Math.PI) * 18;
        shape(c, [[px, y - (across > 0 ? 0 : lift)], [px + width, y - (across > 0 ? lift : 0)], [px + width, y + ph - (across > 0 ? lift : 0)], [px, y + ph - (across > 0 ? 0 : lift)]], across > 0 ? "#F5EEDB" : "#FFFAEB");
        c.lineWidth = 1; c.strokeStyle = "rgba(59, 47, 30, 0.3)"; c.stroke();
      }
      shape(c, [[x + pw - 44, y - 8], [x + pw - 24, y - 8], [x + pw - 24, y + 66], [x + pw - 34, y + 54], [x + pw - 44, y + 66]], "#8B2C2C");
    },
  };

  const contrast = {
    fps: 2,
    showsStep: true,
    tagline: "Der PDA wird vorbereitet.",
    ink: "#FFFFFF", inkMuted: "#FFFF00",
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, "#000000");
      const left = 36, rowH = 66, top = H * 0.14;
      info.labels.forEach((label, i) => {
        const y = top + i * rowH, done = i < info.index, current = i === info.index;
        c.lineWidth = 4; c.strokeStyle = current || done ? "#FFFF00" : "#FFFFFF";
        c.strokeRect(left, y, 38, 38);
        if (done) {
          fill(c, left, y, 38, 38, "#FFFF00");
          c.lineWidth = 6; c.strokeStyle = "#000000"; c.beginPath(); c.moveTo(left + 8, y + 20); c.lineTo(left + 16, y + 29); c.lineTo(left + 30, y + 10); c.stroke();
        }
        write(c, label, left + 54, y + 20, `${current ? 700 : 400} 21px 'Segoe UI', Arial, sans-serif`, current ? "#FFFF00" : "#FFFFFF", "left");
      });
      const y = top + info.total * rowH + 18, w = W - left * 2, n = 8, size = w / n, at = Math.floor(t * 2) % n;
      for (let i = 0; i < n; i++) {
        fill(c, left + i * size + 3, y, size - 6, 34, i === at ? "#FFFF00" : "#333333");
      }
    },
  };

  // --- Spiele & Getränke: eigene Zeichnungen im Stil, ohne Logos und Figuren der Vorbilder -------------

  function pixelTexture(r, paint) {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 16;
    const c = canvas.getContext("2d");
    for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) fill(c, x, y, 1, 1, paint(x, y, r()));
    return canvas;
  }
  const speckle = colors => (x, y, v) => colors[Math.floor(v * colors.length)];

  const minecraft = {
    pixel: 3,
    tagline: ["Block für Block zum Sprachmodell.", "Erst Holz, dann Intelligenz.", "Bitte nicht senkrecht nach unten graben.", "Die Welt wird gespeichert …"],
    ink: "#FFFFFF", inkMuted: "#E8E0D0",
    start(W, H) {
      const r = random(42);
      const dirtColors = ["#866043", "#79553A", "#9B7653", "#6B4A30"], stoneColors = ["#7F7F7F", "#747474", "#8E8E8E", "#686868"];
      const greens = ["#5FAB3A", "#6CBB45", "#4F9A30"];
      const dirt = pixelTexture(r, speckle(dirtColors)), stone = pixelTexture(r, speckle(stoneColors));
      const lawn = pixelTexture(r, speckle(greens));
      const edge = Array.from({length: 16}, () => 2 + Math.floor(r() * 3));
      const turf = pixelTexture(r, (x, y, v) => (y < edge[x] ? greens : dirtColors)[Math.floor(v * 3)]);
      const gem = pixelTexture(r, (x, y, v) => ((x * 7 + y * 11) % 13 < 3 && x % 14 && y % 14 ? ["#4FE3D6", "#2BB8AC"] : stoneColors)[Math.floor(v * 2)]);
      const bark = pixelTexture(r, (x, y, v) => (x % 4 === 1 ? "#4A3219" : ["#6B4A26", "#5C3F20"][Math.floor(v * 2)]));
      const rings = pixelTexture(r, (x, y) => (Math.round(Math.hypot(x - 7.5, y - 7.5)) % 3 ? "#B8935A" : "#8E6C3C"));
      const planks = pixelTexture(r, (x, y, v) => (y % 4 === 3 ? "#7A5A30" : ["#B08A50", "#A47F48"][Math.floor(v * 2)]));
      // Risse: Pixelpfade von der Mitte nach außen, je Stufe werden mehr gezeigt
      const cracks = [];
      for (let k = 0; k < 7; k++) {
        let x = 8, y = 8;
        const a = k / 7 * TAU + r();
        for (let i = 0; i < 9; i++) {
          x = clamp(x + Math.cos(a) + (r() - 0.5), 0, 15); y = clamp(y + Math.sin(a) + (r() - 0.5), 0, 15);
          cracks.push([Math.floor(x), Math.floor(y)]);
        }
      }
      cracks.sort((a, b) => Math.hypot(a[0] - 8, a[1] - 8) - Math.hypot(b[0] - 8, b[1] - 8));
      // Gelände einmal vorzeichnen, das spart pro Bild über 70 Einzelbilder
      const ground = document.createElement("canvas");
      ground.width = W; ground.height = H;
      const g = ground.getContext("2d");
      for (let i = 0; i * 16 < W; i++) {
        const top = Math.floor(H * 0.64 / 16 + Math.round(Math.sin(i * 0.9) * 1.1)) * 16;
        g.drawImage(turf, i * 16, top);
        for (let y = top + 16, row = 1; y < H; y += 16, row++) g.drawImage(row < 3 ? dirt : stone, i * 16, y);
      }
      return {ground, cracks, lawn, blocks: [{top: lawn, side: turf}, {top: stone, side: stone}, {top: gem, side: gem}, {top: rings, side: bark}, {top: planks, side: planks}]};
    },
    draw(c, W, H, t, s, info) {
      c.imageSmoothingEnabled = false;
      fill(c, 0, 0, W, H, "#7EC0EE");
      fill(c, W * 0.74, 18, 24, 24, "#FFE98A");
      [[20, 30, 42], [110, 14, 54], [168, 44, 34]].forEach(([x, y, w], i) => {
        const cx = ((x + t * (3 + i)) % (W + w)) - w;
        fill(c, Math.round(cx), y, w, 8, "#FFFFFF");
        fill(c, Math.round(cx) + 8, y - 5, w - 18, 5, "#FFFFFF");
      });
      c.drawImage(s.ground, 0, 0);
      const period = 2.6, p = cycle(t, period), block = s.blocks[Math.floor(t / period) % s.blocks.length];
      const hit = Math.abs(Math.sin(t * 9));
      const cx = Math.round(W / 2) - 8, cy = Math.round(H * 0.42), a = 34, b = 17, h = 36;
      const shake = p < 0.85 && hit > 0.92 ? 1 : 0;
      // Eine Blockseite über die Textur abbilden: Ursprung plus die beiden Kantenrichtungen
      const face = (tex, ox, oy, ux, uy, vx, vy, shade, stage) => {
        c.setTransform(ux / 16, uy / 16, vx / 16, vy / 16, ox + shake, oy);
        c.drawImage(tex, 0, 0);
        if (shade) fill(c, 0, 0, 16, 16, `rgba(0, 0, 0, ${shade})`);
        s.cracks.slice(0, stage).forEach(([x, y]) => fill(c, x, y, 1, 1, "rgba(20, 16, 12, 0.85)"));
        c.setTransform(1, 0, 0, 1, 0, 0);
      };
      if (p < 0.85) {
        const stage = Math.floor(p / 0.85 * 7) * 9;
        face(block.top, cx, cy - b, a, b, -a, b, 0, stage);
        face(block.side, cx - a, cy, a, b, 0, h, 0.16, stage);
        face(block.side, cx, cy + b, a, -b, 0, h, 0.34, stage);
        // Spitzhacke schwingt um das Griffende
        const swing = -0.95 + hit * 1.05;
        c.save();
        c.translate(cx + 64, cy + 34);
        c.rotate(swing);
        fill(c, -2, -50, 4, 52, "#7A5A30");
        fill(c, -2, -50, 1, 52, "#96743F");
        shape(c, [[-32, -40], [-16, -52], [16, -52], [32, -40], [16, -46], [-16, -46]], "#A9C2CC");
        shape(c, [[-32, -40], [-16, -52], [-10, -46], [-16, -46]], "#D8E8EE");
        c.restore();
      } else {
        // Zerfällt in kleine Stücke, die in hohem Bogen wegfliegen
        const f = (p - 0.85) / 0.15, r = random(Math.floor(t / period) + 3);
        for (let i = 0; i < 26; i++) {
          const dx = (r() - 0.5) * 92, up = 18 + r() * 34, size = 2 + Math.floor(r() * 4);
          const sy = Math.floor(r() * 12), sx = Math.floor(r() * 12);
          c.drawImage(block.side, sx, sy, 4, 4, cx + dx * f, cy + 6 - up * f + 70 * f * f, size, size);
        }
      }
      // Ablage unten: füllt sich mit dem Fortschritt
      const slots = 8, size = 18, left = Math.round((W - slots * size) / 2), y = H - 56, filled = Math.floor(info.smooth * slots + 0.001);
      for (let i = 0; i < slots; i++) {
        const x = left + i * size;
        fill(c, x, y, size, size, "#1E1A16");
        fill(c, x + 1, y + 1, size - 2, size - 2, "#6F6F6F");
        fill(c, x + 2, y + 2, size - 3, size - 3, "#4D4D4D");
        if (i < filled) c.drawImage(s.blocks[i % s.blocks.length].side, x + 3, y + 3, 12, 12);
      }
      fill(c, 0, H - 30, W, 30, "rgba(0, 0, 0, 0.5)");
    },
  };

  const roblox = {
    tagline: ["Speedrun durch den Arbeitsspeicher.", "Nicht in die Lava, nicht in die Lava …", "Checkpoint gesetzt. Hoffentlich.", "Wer hat hier die Noppen sortiert?"],
    ink: "#FFFFFF", inkMuted: "#FFE3B0",
    draw(c, W, H, t, s, info) {
      const gapX = 178, hop = 0.85;
      const platform = i => ({x: i * gapX, y: H * 0.52 + Math.sin(i * 2.1) * 42 + Math.sin(i * 0.7) * 24,
        color: ["#E2231A", "#F5CD30", "#2F9E44", "#0D69AC"][((i % 4) + 4) % 4]});
      const beat = Math.floor(t / hop), f = (t % hop) / hop, fails = beat % 6 === 5;
      const n = beat - Math.floor((beat + 1) / 6);          // Fehlsprünge bringen nicht weiter
      const from = platform(n), to = platform(n + 1);
      let x, y;
      if (fails) { x = from.x + f * gapX * 0.5; y = from.y - Math.sin(Math.min(f * 2, 1) * Math.PI) * 74 + Math.max(0, f - 0.5) * Math.max(0, f - 0.5) * 1500; }
      else { x = lerp(from.x, to.x, f); y = lerp(from.y, to.y, f) - Math.sin(f * Math.PI) * 118; }
      const camera = (fails ? from.x : x) - W * 0.36;
      fill(c, 0, 0, W, H, linear(c, 0, 0, 0, H * 0.8, [[0, "#6CC8FF"], [1, "#DDF4FF"]]));
      fill(c, W - 112, 34, 62, 62, "#FFE066");
      for (let i = 0; i < 7; i++) {   // Türme in der Ferne, laufen langsamer vorbei
        const span = W + 130, bx = ((i * 134 - camera * 0.3) % span + span) % span - 130, bh = 120 + (i * 53) % 150;
        fill(c, bx, H * 0.78 - bh, 104, bh, ["#A7CDE8", "#BBD9EE", "#9CC4E2"][i % 3]);
        for (let k = 0; k < 4; k++) fill(c, bx + 12 + k * 22, H * 0.78 - bh + 12, 12, 12, "#E4F3FC");
      }
      const first = Math.floor((camera - 120) / gapX);
      for (let i = first; i < first + 7; i++) {
        const plat = platform(i), px = plat.x - camera, top = plat.y + 28, w = 124, depth = 46;
        fill(c, px - w / 2, top, w, depth, plat.color);
        fill(c, px - w / 2, top + depth - 10, w, 10, "rgba(0, 0, 0, 0.25)");
        fill(c, px - w / 2, top, w, 5, "rgba(255, 255, 255, 0.35)");
        for (let k = 0; k < 5; k++) {
          const sx = px - w / 2 + 14 + k * 24;
          fill(c, sx - 8, top - 6, 16, 7, plat.color);
          oval(c, sx, top - 6, 8, 3.5, "rgba(255, 255, 255, 0.4)");
        }
        if (((i % 3) + 3) % 3 === 0) {   // Kontrollpunkt
          line(c, px + 40, top - 8, px + 40, top - 74, "#1B1F27", 4);
          shape(c, [[px + 42, top - 74], [px + 80, top - 62], [px + 42, top - 50]], i <= n ? "#2F9E44" : "#E2231A");
        }
      }
      // Lava
      const lava = H * 0.8;
      c.beginPath();
      c.moveTo(0, H);
      for (let px = 0; px <= W; px += 12) c.lineTo(px, lava + Math.sin(px * 0.03 + t * 3) * 7 + Math.sin(px * 0.011 - t * 2) * 5);
      c.lineTo(W, H);
      c.fillStyle = linear(c, 0, lava, 0, H, [[0, "#FF7A1A"], [1, "#B5170B"]]);
      c.fill();
      for (let i = 0; i < 6; i++) {
        const bubble = cycle(t + i * 0.37, 2.2);
        disc(c, (i * 97 + 40) % W, lava + 40 - bubble * 34, 4 + bubble * 7, `rgba(255, 220, 110, ${0.8 - bubble * 0.7})`);
      }
      // Eigene Spielfigur: kleiner Roboter mit Visier und Antenne
      const bx = x - camera, stand = y + 28, leg = Math.sin(f * Math.PI * 4) * 11, sink = fails && f > 0.82;
      if (!sink) {
        c.lineCap = "butt";
        line(c, bx - 9, stand - 22, bx - 9 - leg, stand - 4, "#3A4150", 10);
        line(c, bx + 9, stand - 22, bx + 9 + leg, stand - 4, "#3A4150", 10);
        card(c, bx - 20, stand - 56, 40, 36, 7, "#FF8A1E");
        line(c, bx - 22, stand - 50, bx - 32, stand - 32 - leg, "#3A4150", 8);
        line(c, bx + 22, stand - 50, bx + 32, stand - 32 + leg, "#3A4150", 8);
        card(c, bx - 18, stand - 88, 36, 32, 8, "#F2F5F8");
        card(c, bx - 13, stand - 80, 26, 12, 5, "#14B8C4");
        line(c, bx, stand - 88, bx, stand - 102, "#3A4150", 3);
        disc(c, bx, stand - 104, 4.5, "#E2231A");
      }
      if (fails && f > 0.45) {
        const pop = clamp((f - 0.45) * 6);
        c.save(); c.translate(W * 0.5, H * 0.26); c.scale(pop, pop); c.rotate(-0.08);
        write(c, "HOPPLA!", 3, 3, "900 54px 'Arial Black', sans-serif", "#1B1F27");
        write(c, "HOPPLA!", 0, 0, "900 54px 'Arial Black', sans-serif", "#FFD23F");
        c.restore();
      }
      // Stand als Kontrollpunkte
      card(c, W / 2 - 112, 18, 224, 38, 10, "#1B1F27");
      write(c, `Kontrollpunkt ${Math.min(info.index + 1, info.total)} / ${info.total}`, W / 2, 37, "800 17px 'Arial Rounded MT Bold', 'Trebuchet MS', sans-serif", "#FFFFFF");
    },
  };

  const whiteMonster = {
    tagline: ["Null Zucker. Null Geduld.", "Koffein-Stand: bedenklich.", "Schlaf ist auch nur ein Ladebalken.", "Eiskalt kalkuliert."],
    ink: "#0C0D0F", inkMuted: "#59626C",
    start(W, H) {
      const r = random(77), frost = document.createElement("canvas");
      frost.width = W; frost.height = H;
      const g = frost.getContext("2d");
      const branch = (x, y, angle, length, depth) => {
        const ex = x + Math.cos(angle) * length, ey = y + Math.sin(angle) * length;
        line(g, x, y, ex, ey, "rgba(120, 190, 225, 0.6)", depth * 0.7 + 0.6);
        if (depth > 0) {
          branch(ex, ey, angle, length * 0.72, depth - 1);
          branch(lerp(x, ex, 0.6), lerp(y, ey, 0.6), angle + 1.05, length * 0.42, depth - 1);
          branch(lerp(x, ex, 0.6), lerp(y, ey, 0.6), angle - 1.05, length * 0.42, depth - 1);
        }
      };
      [[0, 0, 0.1], [W, 0, Math.PI / 2 + 0.2], [0, H * 0.82, -1], [W, H * 0.82, Math.PI + 0.9], [W * 0.1, H * 0.42, 0.3], [W * 0.92, H * 0.5, 2.8]].forEach(([x, y, base]) => {
        for (let i = 0; i < 5; i++) branch(x, y, base + i * 0.42 - 0.4 + r() * 0.2, 70 + r() * 70, 2);
      });
      return {frost, drops: Array.from({length: 16}, () => ({x: r(), y: r(), v: 12 + r() * 30, s: 2 + r() * 3.5})),
        flakes: Array.from({length: 34}, () => ({x: r() * W, y: r() * H, v: 14 + r() * 26, s: 1 + r() * 2.4, p: r() * TAU})),
        bubbles: Array.from({length: 18}, () => ({x: r(), y: r(), v: 40 + r() * 70, s: 1.5 + r() * 3}))};
    },
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, linear(c, 0, 0, W, H, [[0, "#FBFDFE"], [0.5, "#E3E9EF"], [1, "#CDD6DE"]]));
      for (let i = 0; i < 3; i++) {   // Lichtstreifen wie auf gebürstetem Metall
        const x = ((t * 90 + i * 260) % (W + 300)) - 150;
        shape(c, [[x, 0], [x + 70, 0], [x - 90, H], [x - 160, H]], "rgba(255, 255, 255, 0.5)");
      }
      c.globalAlpha = 0.25 + 0.75 * info.smooth;
      c.drawImage(s.frost, 0, 0);
      c.globalAlpha = 1;
      for (const flake of s.flakes) disc(c, flake.x + Math.sin(t + flake.p) * 12, (flake.y + t * flake.v) % H, flake.s, "#FFFFFF");
      const p = cycle(t, 4.2), fizz = p < 0.3, jitter = fizz ? Math.sin(t * 44) * 1.6 : 0;
      const x = W / 2 + jitter, top = H * 0.13, w = 156, bottom = top + 350, half = w / 2;
      oval(c, W / 2, bottom + 4, half * 1.25, 14, "rgba(30, 45, 60, 0.22)");
      const body = () => {
        c.beginPath();
        c.moveTo(x - half * 0.72, top);
        c.lineTo(x + half * 0.72, top);
        c.quadraticCurveTo(x + half, top + 14, x + half, top + 46);
        c.lineTo(x + half, bottom - 24);
        c.quadraticCurveTo(x + half, bottom, x + half * 0.74, bottom);
        c.lineTo(x - half * 0.74, bottom);
        c.quadraticCurveTo(x - half, bottom, x - half, bottom - 24);
        c.lineTo(x - half, top + 46);
        c.quadraticCurveTo(x - half, top + 14, x - half * 0.72, top);
        c.closePath();
      };
      body();
      c.fillStyle = linear(c, x - half, 0, x + half, 0, [[0, "#BAC4CE"], [0.32, "#FFFFFF"], [0.62, "#F1F4F7"], [1, "#B4BEC8"]]);
      c.fill();
      c.save();
      body();
      c.clip();
      // Durchleuchtet: Füllstand ist der Fortschritt
      const level = bottom - 8 - (bottom - top - 62) * Math.max(0.04, info.smooth);
      c.beginPath();
      c.moveTo(x - half, bottom);
      for (let px = x - half; px <= x + half; px += 6) c.lineTo(px, level + Math.sin(px * 0.09 + t * 5) * 3.5);
      c.lineTo(x + half, bottom);
      c.fillStyle = "rgba(95, 200, 240, 0.42)";
      c.fill();
      for (const bubble of s.bubbles) {
        const span = bottom - level;
        if (span > 12) disc(c, x - half + bubble.x * w, bottom - ((bubble.y * span + t * bubble.v) % span), bubble.s, "rgba(255, 255, 255, 0.85)");
      }
      for (const drop of s.drops) oval(c, x - half + drop.x * w, top + 30 + ((drop.y * 300 + t * drop.v) % 300), drop.s * 0.75, drop.s * 1.5, "rgba(255, 255, 255, 0.8)");
      // Aufdruck: eisblaues Zickzack und eigener Schriftzug
      c.lineJoin = "miter";
      c.beginPath();
      for (let i = 0; i <= 8; i++) c.lineTo(x - half + i * w / 8, top + 236 + (i % 2 ? -14 : 14));
      c.lineWidth = 6; c.strokeStyle = "#54C4EC"; c.stroke();
      c.restore();
      c.save();
      c.translate(x, top + 128);
      c.rotate(-Math.PI / 2);
      write(c, "ENERGIE", 0, 0, "italic 900 48px Bahnschrift, Impact, sans-serif", "#0C0D0F");
      c.restore();
      write(c, "NULL ZUCKER", x, top + 276, "800 15px Bahnschrift, sans-serif", "#0C0D0F");
      write(c, "PDA", x, top + 304, "italic 900 26px Bahnschrift, Impact, sans-serif", "#0C0D0F");
      // Deckel und Lasche, die alle paar Sekunden aufschnappt
      oval(c, x, top, half * 0.72, 11, "#9FABB7");
      oval(c, x, top, half * 0.6, 8, "#D5DCE3");
      const open = fizz ? ease(clamp(p / 0.06)) : 0;
      c.save();
      c.translate(x - 4, top);
      c.rotate(-open * 0.7);
      oval(c, 13, 0, 18, 5.5, "#8A96A2");
      oval(c, 18, 0, 8, 2.6, "#D5DCE3");
      c.restore();
      if (fizz) {
        const spray = p / 0.3, r = random(Math.floor(t / 4.2) + 9);
        for (let i = 0; i < 26; i++) {
          const a = -Math.PI / 2 + (r() - 0.5) * 1.5, far = (40 + r() * 130) * spray;
          disc(c, x + Math.cos(a) * far, top + Math.sin(a) * far + 200 * spray * spray * 0.3, 1.5 + r() * 2.5, `rgba(84, 196, 236, ${1 - spray})`);
        }
      }
      write(c, `${Math.round(info.smooth * 100)} % WACH`, W / 2, bottom + 40, "italic 900 30px 'Bahnschrift Condensed', Bahnschrift, Impact, sans-serif", "#0C0D0F");
    },
  };

  function pretzel(c, x, y, size, rot) {
    c.save();
    c.translate(x, y);
    c.rotate(rot);
    c.scale(size, size);
    const loop = () => {
      c.beginPath();
      c.moveTo(-6, 22); c.bezierCurveTo(-34, 2, -46, -30, -18, -32); c.bezierCurveTo(4, -33, 8, -8, 8, 4);
      c.bezierCurveTo(8, 12, 12, 18, 6, 22);
      c.moveTo(6, 22); c.bezierCurveTo(34, 2, 46, -30, 18, -32); c.bezierCurveTo(-4, -33, -8, -8, -8, 4);
      c.bezierCurveTo(-8, 12, -12, 18, -6, 22);
    };
    c.lineCap = "round";
    loop(); c.lineWidth = 11; c.strokeStyle = "#7A4416"; c.stroke();
    loop(); c.lineWidth = 7.5; c.strokeStyle = "#B8702A"; c.stroke();
    [[-30, -16], [-16, -29], [16, -29], [30, -16], [-2, -6], [24, 6], [-24, 6]].forEach(([sx, sy]) => fill(c, sx - 1.2, sy - 1.2, 2.6, 2.6, "#FFFFFF"));
    c.restore();
  }

  const spezi = {
    tagline: ["Halb Cola, halb Orange, ganz viel Geduld.", "A bisserl dauert's no.", "Die Wespe war zuerst da.", "Wird noch richtig gemischt."],
    ink: "#FFF3DC", inkMuted: "#F6D9B0",
    start(W, H) {
      const r = random(31);
      return {leaves: Array.from({length: 46}, () => { const left = r() < 0.5; return {x: left ? r() * 150 : W - r() * 150, y: r() * 120 - 16, r: 18 + r() * 26, c: ["#3E7D3A", "#4B9145", "#35702F"][Math.floor(r() * 3)]}; }),
        bubbles: Array.from({length: 26}, () => ({x: r(), y: r(), v: 30 + r() * 60, s: 1.2 + r() * 2.6}))};
    },
    draw(c, W, H, t, s, info) {
      fill(c, 0, 0, W, H, linear(c, 0, 0, 0, H * 0.72, [[0, "#8FD0F4"], [1, "#EAF7FF"]]));
      for (const leaf of s.leaves) disc(c, leaf.x, leaf.y, leaf.r, leaf.c);
      // Rautenfähnchen an der Leine
      const sag = x => 30 + Math.sin(x / W * Math.PI) * 34;
      c.beginPath();
      for (let x = 0; x <= W; x += 12) c.lineTo(x, sag(x));
      c.lineWidth = 2; c.strokeStyle = "#5A3A20"; c.stroke();
      for (let i = 0; i < 17; i++) {
        const x = 16 + i * 34, y = sag(x), sway = Math.sin(t * 2 + i) * 3;
        shape(c, [[x, y], [x + 14 + sway, y + 18], [x + sway, y + 38], [x - 14 + sway, y + 18]], i % 2 ? "#1F6FB5" : "#FFFFFF");
      }
      // Biertisch
      const table = H * 0.72;
      fill(c, 0, table, W, H - table, "#8A5A30");
      for (let y = table + 28; y < H; y += 44) fill(c, 0, y, W, 2, "#6B4322");
      for (let x = 70; x < W; x += 190) fill(c, x, table, 2, H - table, "#6B4322");
      fill(c, 0, table, W, 6, "#A9743F");
      fill(c, 0, H - 76, W, 76, "rgba(40, 18, 6, 0.42)");
      // Glas: Fortschritt ist der Füllstand, Cola und Orange laufen ineinander
      const xc = W / 2, top = H * 0.2, bottom = table + 16, topHalf = 98, baseHalf = 72;
      oval(c, xc, bottom + 6, 118, 15, "#E9D3AE");
      oval(c, xc, bottom + 6, 92, 11, "#1F6FB5");
      const glass = () => {
        c.beginPath();
        c.moveTo(xc - topHalf, top); c.lineTo(xc + topHalf, top); c.lineTo(xc + baseHalf, bottom);
        c.lineTo(xc - baseHalf, bottom); c.closePath();
      };
      glass();
      c.fillStyle = "rgba(255, 255, 255, 0.34)";
      c.fill();
      const level = lerp(bottom - 14, top + 30, Math.max(0.1, info.smooth));
      c.save();
      glass();
      c.clip();
      fill(c, xc - 120, level, 240, bottom - level, linear(c, 0, level, 0, bottom, [[0, "#F7A23B"], [1, "#D9700F"]]));
      const span = bottom - level;
      // Cola zieht in welligen Schlieren durchs Orange, nach unten immer dichter
      for (let k = 0; k < 5; k++) {
        const bandY = level + (k + 0.45) / 5 * span, thick = 8 + k * 5;
        c.beginPath();
        for (let px = xc - 120; px <= xc + 120; px += 8) c.lineTo(px, bandY + Math.sin(px * 0.04 + t * 1.6 + k * 2) * 13);
        for (let px = xc + 120; px >= xc - 120; px -= 8) c.lineTo(px, bandY + thick + Math.sin(px * 0.03 - t * 1.1 + k) * 10);
        c.closePath();
        c.fillStyle = "rgba(74, 34, 16, 0.78)";
        c.fill();
      }
      for (const bubble of s.bubbles) disc(c, xc - 90 + bubble.x * 180, bottom - ((bubble.y * span + t * bubble.v) % span), bubble.s, "rgba(255, 240, 210, 0.75)");
      for (let i = 0; i < 12; i++) disc(c, xc - 104 + i * 19, level + Math.sin(t * 4 + i) * 2.5, 11 + (i * 5) % 6, "#FFF1D6");
      c.restore();
      // Zwei Strahlen von oben, solange noch nachgeschenkt wird
      line(c, xc - 26, 0, xc - 26, level, "rgba(74, 34, 16, 0.92)", 9);
      line(c, xc + 26, 0, xc + 26, level, "rgba(242, 140, 30, 0.95)", 9);
      glass();
      c.lineWidth = 4; c.strokeStyle = "rgba(255, 255, 255, 0.9)"; c.lineJoin = "round"; c.stroke();
      shape(c, [[xc - topHalf + 16, top + 14], [xc - topHalf + 34, top + 14], [xc - baseHalf + 30, bottom - 22], [xc - baseHalf + 12, bottom - 22]], "rgba(255, 255, 255, 0.34)");
      pretzel(c, W * 0.17, table + 4, 1.55, Math.sin(t * 1.2) * 0.1 - 0.2);
      // Die Wespe umkreist das Glas und setzt sich ab und zu an den Rand
      const rest = cycle(t, 7) > 0.8;
      const wx = rest ? xc + topHalf - 6 : xc + Math.cos(t * 1.9) * 168 + Math.sin(t * 5.3) * 12;
      const wy = rest ? top - 8 : H * 0.36 + Math.sin(t * 2.7) * 86 + Math.cos(t * 7) * 8;
      const flap = rest ? 4 : 5 + Math.abs(Math.sin(t * 40)) * 7;
      oval(c, wx - 4, wy - 9, flap, 4, "rgba(255, 255, 255, 0.85)", -0.6);
      oval(c, wx + 5, wy - 9, flap, 4, "rgba(255, 255, 255, 0.85)", 0.6);
      oval(c, wx, wy, 13, 7, "#FFC61A");
      for (const dx of [-5, 1, 7]) fill(c, wx + dx, wy - 6, 3, 12, "#1B1208");
      disc(c, wx - 12, wy, 4.5, "#1B1208");
    },
  };

  const scenes = {night, graphite, light, forest, sand, classic, apple, "apple-dark": appleDark, glass, clay, material, depth, neumorph,
    gameboy, win95, terminal, vapor, newspaper, deco, maximal, brutal, comic, bauhaus, cyber, eco, paper, blueprint, reader, contrast,
    minecraft, roblox, "white-monster": whiteMonster, spezi};

  return {get: id => scenes[id] || scenes.night, ids: Object.keys(scenes)};
})();
