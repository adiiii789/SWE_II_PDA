# Modelle für den Begleiter

Jede `.glb`/`.gltf` in diesem Ordner steht unter **Einstellungen → Begleiter → Figur** zur Auswahl
(dazu immer die eingebaute Figur). Ohne Auswahl startet `companion.glb`; die Umgebungsvariable
`PDA_COMPANION_MODEL` kann auf eine andere Datei zeigen.

## Anpassen: gleichnamige .json neben dem Modell

```json
{
  "title": "Lightning McQueen",
  "yaw": 35,
  "size": 0.85,
  "lift": -0.17,
  "hover": false,
  "eyes": "iris",
  "iris_hue": [160, 260]
}
```

| Feld | Bedeutung | Standard |
|---|---|---|
| `title` | Name in den Einstellungen | Dateiname |
| `yaw` | zusätzlich drehen (Grad), gespiegelt je nach Seite - schaut immer zum Popup | 0 |
| `size` | Größe relativ zur eingebauten Figur (0.2-3) | 1 |
| `lift` | höher (+) / tiefer (-), in Figurhöhen (-1 bis 1) | 0 |
| `hover` | schweben; `false` = steht, wippt nur leicht | true |
| `eyes` | `glow`: Augen-Textur als Leuchtmaske (Farbe je Zustand, blinzeln, Denkpunkte) - für Displays/Visiere. `iris`: nur die Iris (Farbton in `iris_hue`) nimmt die Zustandsfarbe an - für echte Augen. `keep`: unverändert | glow |
| `iris_hue` | Farbtonbereich der Iris in Grad, z. B. blau `[160, 260]` | [160, 260] |

## Was automatisch passiert (`frontend/companion.js`)
- Ausrichten: Das Gesicht (Material/Objekt mit `face`, `screen`, `display` oder `eye` im Namen) schaut zur Kamera.
- Größe und Stand über dem Lichtschein am Boden.
- Teile namens `Head`/`Kopf`, `Arm_L`/`Arm_R` bewegen sich einzeln; sonst bewegt sich das Modell als Ganzes.
- Leuchtende Materialien (Emission oder `light`, `glow`, `led` im Namen) bekommen die Zustandsfarbe.
- Mitgelieferte Animationen laufen (`idle`/`hover`/`float` im Namen bevorzugt).

Tipp: unter ~30.000 Polygonen und Texturen bis 1-2K bleiben. Draco-komprimierte Modelle gehen nicht.
