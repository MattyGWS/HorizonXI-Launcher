#!/usr/bin/env bash
set -euo pipefail

VERSION="0.3.0"

flatpak build-bundle \
    flatpak/repo \
    "HorizonXI-Launcher-${VERSION}.flatpak" \
    io.github.mattyws.HorizonXILauncher

echo
echo "=================================================="
echo "Bundle created:"
echo "HorizonXI-Launcher-${VERSION}.flatpak"
echo "=================================================="
