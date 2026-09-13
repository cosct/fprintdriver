#!/bin/sh
# Build a .deb of libfprint + the egis0575 driver from a release tag.
#
# Runs inside a Debian container; installs build deps itself:
#   ./build-deb.sh <version>            # e.g. ./build-deb.sh 0.2.0
# Produces libfprint-egis0575_<libfprint-base>+egis0575.<version>-1_amd64.deb.
set -eu

VER="${1:?usage: build-deb.sh <version>}"
TAG="egis0575-v$VER"
SRC="libfprint-egis0575-$TAG"
# The deb version carries the bundled libfprint base so that
# Provides: libfprint-2-2 (= $LFVER) stays Debian-policy-compliant
# (provide <= own version) and satisfies fprintd's libfprint-2-2 (>= 1.9x).
LFVER=1.94.100
FULLVER="$LFVER+egis0575.$VER"

apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  build-essential meson ninja-build ca-certificates curl xz-utils \
  libglib2.0-dev libgusb-dev libpixman-1-dev libusb-1.0-0-dev libudev-dev libssl-dev libgudev-1.0-dev

curl -fsSLO "https://github.com/cosct/libfprint-egis0575/archive/refs/tags/$TAG.tar.gz"
tar xf "$TAG.tar.gz"

meson setup "$SRC/build" "$SRC" --prefix=/usr -D introspection=false -D doc=false \
  -D installed-tests=false -D gtk-examples=false \
  -D udev_rules_dir=/usr/lib/udev/rules.d -D udev_hwdb_dir=/usr/lib/udev/hwdb.d
meson compile -C "$SRC/build"
DESTDIR="$PWD/stage" meson install -C "$SRC/build"

mkdir -p stage/DEBIAN
cat > stage/DEBIAN/control <<EOF
Package: libfprint-egis0575
Version: $FULLVER-1
Section: libs
Priority: optional
Architecture: amd64
Maintainer: cosct <cosct@outlook.com>
Depends: libglib2.0-0, libgusb2, libpixman-1-0, libusb-1.0-0, libgudev-1.0-0, libssl3 | libssl3t64
Provides: libfprint-2-2 (= $LFVER)
Conflicts: libfprint-2-2
Replaces: libfprint-2-2
Description: libfprint with the experimental EgisTec EH575 (1c7a:0575) driver
 libfprint plus the egis0575 press-snapshot driver with a Windows-engine
 matcher port, for the EgisTec EH575 (1c7a:0575) fingerprint sensor.
 Replaces the distribution libfprint-2-2 for devices that need this driver.
EOF
# refresh the dynamic-linker cache after install/upgrade/removal
echo "activate-noawait ldconfig" > stage/DEBIAN/triggers

dpkg-deb --build --root-owner-group stage "libfprint-egis0575_${FULLVER}-1_amd64.deb"
echo "built: libfprint-egis0575_${FULLVER}-1_amd64.deb"
