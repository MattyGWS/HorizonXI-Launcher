#!/usr/bin/env bash
set -euo pipefail
sudo dnf install -y flatpak flatpak-builder
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install -y flathub org.gnome.Platform//46 org.gnome.Sdk//46 org.winehq.Wine//stable-25.08 || true
