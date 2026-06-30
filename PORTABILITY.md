# Portability notes

The launcher now prefers `aria2c` for magnet/torrent downloads. This avoids Python binary `libtorrent` bindings for the release build.

## Native development

Install the normal Python/GTK dependencies plus aria2:

```bash
sudo dnf install aria2 python3-gobject gtk4 libadwaita
```

`rb_libtorrent-python3` is optional now. It is only used as a fallback if aria2c is not available.

## Flatpak

The Flatpak manifest builds/bundles aria2 inside the app, so users should not need to install aria2 or libtorrent on the host.

Build locally:

```bash
./scripts/install-flatpak-tools-fedora.sh
./scripts/build-flatpak.sh
./scripts/run-flatpak.sh
```
