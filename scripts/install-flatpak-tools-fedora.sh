#!/usr/bin/env bash
set -euo pipefail

sudo dnf install -y flatpak flatpak-builder
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

flatpak install -y flathub \
  org.freedesktop.Platform//24.08 \
  org.freedesktop.Sdk//24.08 \
  org.freedesktop.Sdk.Compat.i386//24.08 \
  org.freedesktop.Sdk.Extension.toolchain-i386//24.08 \
  org.freedesktop.Platform.Compat.i386//24.08 \
  org.freedesktop.Platform.GL32.default//24.08 \
  org.winehq.Wine//stable-25.08 || true
