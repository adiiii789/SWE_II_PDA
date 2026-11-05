"""Startet bei Bedarf den lokalen Ollama-Zugang; lädt selbst keine Modelle herunter."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)


def find_ollama() -> str | None:
    executable = shutil.which("ollama")
    if executable:
        return executable
    paths = ([Path("/opt/homebrew/bin/ollama"), Path("/usr/local/bin/ollama"),
              Path("/Applications/Ollama.app/Contents/Resources/ollama")]
             if sys.platform == "darwin" else
             [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"])
    return next((str(path) for path in paths if path.is_file()), None)


class OllamaService:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.process: subprocess.Popen | None = None

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/api/version", timeout=0.3) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def start(self) -> None:
        if urllib.parse.urlparse(self.url).hostname not in {"localhost", "127.0.0.1", "::1"}:
            return
        if self.available():
            return
        executable = find_ollama()
        if executable is None:
            log.info("Ollama fehlt. Bitte installieren und einmal mit 'ollama signin' anmelden.")
            return
        try:
            self.process = subprocess.Popen(
                [executable, "serve"], env={**os.environ, "OLLAMA_HOST": self.url},
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if self.available():
                    return
                if self.process.poll() is not None:
                    break
                time.sleep(0.1)
            log.warning("Ollama ist noch nicht bereit. Bitte den Dienst prüfen.")
        except OSError:
            log.exception("Ollama konnte nicht gestartet werden")

    def close(self) -> None:
        # Ein bereits vor dem Programmstart laufender Dienst gehört nicht dieser Anwendung.
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
