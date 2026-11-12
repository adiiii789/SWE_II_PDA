"""3D-Modelle für den Begleiter (frontend/companion.js): alle .glb/.gltf in frontend/models.

Neben einem Modell kann eine gleichnamige .json liegen, die es anpasst (alles optional):

    {
      "title": "Roboter",       Name in den Einstellungen (sonst der Dateiname)
      "yaw": -35,               zusätzlich drehen, in Grad (nach dem automatischen Ausrichten zum Gesicht)
      "size": 1.0,              Größe relativ zur eingebauten Figur
      "lift": 0.0,              höher (+) oder tiefer (-) stellen, in Figurhöhen
      "hover": true,            schweben (false: steht still, wippt nur leicht - z. B. ein Auto)
      "eyes": "glow",           "glow": Augen-Textur als Leuchtmaske (Form bleibt, Farbe = Zustand,
                                blinzeln, Denkpunkte); "iris": nur die Iris (Farbton in iris_hue)
                                nimmt die Zustandsfarbe an; "keep": Augen unverändert
      "iris_hue": [160, 260]    Farbtonbereich der Iris in Grad (nur für "iris")
    }
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QUrl

log = logging.getLogger(__name__)

BUILT_IN = "builtin"   # Kennung der eingebauten Figur (ohne Modelldatei)
EYE_MODES = ("glow", "iris", "keep")
DEFAULTS: dict[str, Any] = {"yaw": 0.0, "size": 1.0, "lift": 0.0, "hover": True, "eyes": "glow",
                            "iris_hue": [160.0, 260.0]}


def model_options(raw: Any) -> dict[str, Any]:
    """Einstellungen aus der .json prüfen; Ungültiges fällt auf den Standard zurück."""
    options = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return options
    for key in ("yaw", "size", "lift"):
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            options[key] = float(value)
    options["size"] = min(3.0, max(0.2, options["size"]))
    options["lift"] = min(1.0, max(-1.0, options["lift"]))
    if isinstance(raw.get("hover"), bool):
        options["hover"] = raw["hover"]
    if raw.get("eyes") in EYE_MODES:
        options["eyes"] = raw["eyes"]
    hue = raw.get("iris_hue")
    if (isinstance(hue, list) and len(hue) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in hue)):
        options["iris_hue"] = [float(hue[0]) % 360, float(hue[1]) % 360]
    return options


def is_model(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in (".glb", ".gltf")


def model_entry(path: Path) -> dict[str, Any]:
    """Ein Modell mit seinen Einstellungen: {"id", "title", "url", "options"}."""
    raw: Any = {}
    sidecar = path.with_suffix(".json")
    if sidecar.is_file():
        try:
            raw = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            log.warning("Einstellungen für %s nicht lesbar: %s", path.name, error)
    title = raw.get("title") if isinstance(raw, dict) and isinstance(raw.get("title"), str) else ""
    return {"id": path.name, "title": title.strip() or path.stem.replace("_", " "),
            "url": QUrl.fromLocalFile(str(path.resolve())).toString(), "options": model_options(raw)}


def list_models(folder: Path) -> list[dict[str, Any]]:
    """Alle Modelle im Ordner, nach Titel sortiert."""
    if not folder.is_dir():
        return []
    models = [model_entry(path) for path in folder.iterdir() if is_model(path)]
    return sorted(models, key=lambda model: model["title"].lower())
