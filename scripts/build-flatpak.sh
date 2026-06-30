#!/usr/bin/env bash
set -euo pipefail

rm -rf flatpak/repo

flatpak-builder \
  --force-clean \
  --user \
  --install \
  --repo=flatpak/repo \
  .flatpak-build \
  flatpak/io.github.mattyws.HorizonXILauncher.yml
