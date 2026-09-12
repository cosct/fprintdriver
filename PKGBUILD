# libfprint with the experimental EgisTec EH575 (1c7a:0575) driver
# from the fprintdriver research project.
#
# Replaces the system libfprint (incl. topni1's libfprint-egis-0575 AUR
# package). Built from the local tree at ../libfprint (upstream master +
# egis0575 driver + Windows-engine matcher port).
#
# Build & install (will ask for sudo password at install step):
#   makepkg -f -i

pkgname=libfprint-egis0575-experimental
pkgver=0.2.0
pkgrel=1
pkgdesc="EgisTec EH575 (1c7a:0575) fingerprint driver on current libfprint (fprintdriver research build)"
arch=(x86_64)
url="https://gitlab.freedesktop.org/libfprint/libfprint"
license=(LGPL-2.1-or-later)
depends=(libusb libgusb nss pixman glib2)
makedepends=(meson ninja git gobject-introspection)
provides=(libfprint libfprint-2.so)
conflicts=(libfprint libfprint-egis-0575)
replaces=(libfprint-egis-0575)
options=(!strip)

prepare() {
  rm -rf "$srcdir/libfprint"
  cp -a "$startdir/libfprint" "$srcdir/libfprint"
  rm -rf "$srcdir/libfprint/builddir"
}

build() {
  arch-meson libfprint build
  meson compile -C build
}

package() {
  meson install -C build --destdir "$pkgdir"
}
