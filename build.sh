#!/usr/bin/env bash
# build.sh — one-command macOS/Linux build for The Vassal.
# On macOS this produces dist/The Vassal.app (double-click to run).
# MUST be run ON a Mac to produce a Mac build (no cross-compile from Windows).
#
# Prereqs (one time):  pip3 install pywebview pyinstaller
# Usage:               ./build.sh
set -euo pipefail
cd "$(dirname "$0")"
echo "Building The Vassal (one-file) ..."
echo "Staging game assets..."
python3 build_stage.py
pyinstaller --noconfirm --clean thevassal.spec
if [ -e "dist/Legality Engine for VASSAL.app" ]; then
  echo "OK  ->  dist/Legality Engine for VASSAL.app"
  echo "Gatekeeper will block an unsigned app: right-click -> Open the first time,"
  echo "or notarize with an Apple Developer account. See RELEASE_README.md."
elif [ -e "dist/Legality Engine for VASSAL" ]; then
  echo "OK  ->  dist/Legality Engine for VASSAL"
else
  echo "BUILD FAILED — no app produced." >&2
  exit 1
fi
