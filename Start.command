#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
    printf '%s\n' 'Bitte zuerst die Python-Umgebung einrichten (siehe README.md).'
    exit 1
fi
exec .venv/bin/python main.py
