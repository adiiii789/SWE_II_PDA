// Geschlossene Schalen und gewölbte Einsätze des Roboters in Modellkoordinaten.
function buildRobotModel() {
  const meshes = [];
  const shell = [.91, .93, .99];
  const visor = [.12, .15, .23];
  const blue = [.22, .59, 1];
  const rose = [1, .35, .47];

  function mesh(rows, columns, sample, color, gloss, emission = 0) {
    const vertices = [];
    const indices = [];
    for (let row = 0; row <= rows; row++) {
      for (let column = 0; column <= columns; column++) {
        vertices.push(...sample(row / rows, column / columns * 2 * Math.PI));
      }
    }
    for (let row = 0; row < rows; row++) {
      for (let column = 0; column < columns; column++) {
        const a = row * (columns + 1) + column;
        const b = a + columns + 1;
        indices.push(a, b, a + 1, a + 1, b, b + 1);
      }
    }
    meshes.push({
      vertices: new Float32Array(vertices), indices: new Uint16Array(indices),
      color, gloss, emission
    });
  }

  function shellMesh(shape, color, gloss) {
    const {x, y, z, rx, ry, rz, taper = 0, tilt = 0} = shape;
    const c = Math.cos(tilt), s = Math.sin(tilt);
    mesh(28, 48, (v, phi) => {
      const latitude = v * Math.PI;
      const height = Math.cos(latitude);
      const radial = Math.sin(latitude);
      const u = radial * Math.cos(phi), w = radial * Math.sin(phi);
      const spread = 1 + taper * height;
      const px = rx * u * spread, py = ry * height;
      const nx = u / (rx * spread), nz = w / (rz * spread);
      const ny = (height - taper * radial * radial / spread) / ry;
      return [
        x + c * px - s * py, y + s * px + c * py, z + rz * w * spread,
        c * nx - s * ny, s * nx + c * ny, nz
      ];
    }, color, gloss);
  }

  // Das Visier und die Lichter folgen der Krümmung der Schale, auch von der Seite.
  function inset(shape, x, y, rx, ry, tilt, offset, color, gloss, emission) {
    const c = Math.cos(tilt), s = Math.sin(tilt);
    mesh(10, 48, (r, phi) => {
      const dx = rx * r * Math.cos(phi), dy = ry * r * Math.sin(phi);
      const px = x + dx * c - dy * s, py = y + dx * s + dy * c;
      const h = (py - shape.y) / shape.ry;
      const spread = 1 + (shape.taper || 0) * h;
      const u = (px - shape.x) / (shape.rx * spread);
      const w = Math.sqrt(Math.max(0, 1 - h * h - u * u));
      return [
        px, py, shape.z + shape.rz * spread * w + offset,
        u / shape.rx, h / shape.ry, w / shape.rz
      ];
    }, color, gloss, emission);
  }

  const head = {x: 0, y: .64, z: 0, rx: .69, ry: .48, rz: .47};
  const body = {x: 0, y: -.48, z: -.035, rx: .51, ry: .62, rz: .405, taper: .22};
  shellMesh(head, shell, .29);
  shellMesh(body, shell, .27);
  for (const side of [-1, 1]) {
    shellMesh({
      x: side * .55, y: -.40, z: -.045, rx: .115, ry: .46, rz: .20,
      taper: .22, tilt: side * -.16
    }, shell, .28);
  }
  inset(head, 0, .625, .574, .337, 0, .012, visor, .27, .05);
  for (const side of [-1, 1]) {
    inset(head, side * .193, .62, .137, .080, side * .37, .020, blue, .18, .86);
  }
  inset(body, -.171, -.28, .071, .071, 0, .012, rose, .18, .64);
  return meshes;
}
