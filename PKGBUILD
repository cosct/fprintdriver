# libfprint with the experimental EgisTec EH575 (1c7a:0575) driver
# from the fprintdriver research project.
#
# LOCAL DEVELOPMENT packaging: builds from the working tree at ../libfprint
# (upstream master + egis0575 driver). End users should install the AUR
# package of the same name, which builds from the published release tag:
#   yay -S libfprint-egis0575
#
# Build & install (will ask for sudo password at install step):
#   makepkg -f -i

pkgname=libfprint-egis0575
pkgver=0.2.0
pkgrel=1
pkgdesc="EgisTec EH575 (1c7a:0575) fingerprint driver on current libfprint (fprintdriver research build)"
arch=(x86_64)
url="https://github.com/cosct/libfprint-egis0575"
license=(LGPL-2.1-or-later)
# vendored libfprint builds all drivers by default: uru4000 needs openssl
# at build time and links libssl/libcrypto at runtime; nothing needs nss.
depends=(libusb libgusb openssl pixman glib2 libgudev)
makedepends=(meson ninja git gobject-introspection gtk-doc)
# 1.94.100 = bundled libfprint base; soversion 2 -> libfprint-2.so=2-64
provides=(libfprint=1.94.100 libfprint-2.so=2-64)
conflicts=(libfprint libfprint-egis-0575 libfprint-egis0575-experimental)
replaces=(libfprint-egis-0575 libfprint-egis0575-experimental)
options=(!strip)

prepare() {
  rm -rf "$srcdir/libfprint"
  cp -a "$startdir/libfprint" "$srcdir/libfprint"
  rm -rf "$srcdir/libfprint/builddir" "$srcdir/libfprint/builddir-verify"
}

build() {
  arch-meson libfprint build
  meson compile -C build
}

package() {
  meson install -C build --destdir "$pkgdir"
}
