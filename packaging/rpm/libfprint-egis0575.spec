# libfprint + the experimental EgisTec EH575 (1c7a:0575) driver.
# Research project: https://github.com/cosct/fprintdriver
# Release CI builds this spec with --define "version <driver-version>".
%define drvver %{?version}%{!?version:0.2.0}
# libfprint base bundled with the driver (root meson.build version:)
%define lfver 1.94.100

Name:           libfprint-egis0575
Version:        %{drvver}
Release:        1%{?dist}
Summary:        libfprint with the experimental EgisTec EH575 (1c7a:0575) driver
License:        LGPL-2.1-or-later
URL:            https://github.com/cosct/libfprint-egis0575
Source0:        %{url}/archive/refs/tags/egis0575-v%{drvver}.tar.gz
ExclusiveArch:  x86_64

BuildRequires:  meson ninja-build gcc gcc-c++
BuildRequires:  glib2-devel libgusb-devel pixman-devel libusb1-devel
BuildRequires:  systemd-devel openssl-devel libgudev-devel

Provides:       libfprint = %{lfver}
Provides:       libfprint%{?_isa} = %{lfver}
Provides:       libfprint-2.so.2()(64bit)
Conflicts:      libfprint

%description
libfprint plus the egis0575 press-snapshot driver with a Windows-engine
matcher port, for the EgisTec EH575 (1c7a:0575) fingerprint sensor.
Replaces the distribution libfprint for devices that need this driver.

%prep
%setup -q -n libfprint-egis0575-egis0575-v%{drvver}

%build
%meson -D introspection=false -D doc=false -D installed-tests=false \
  -D gtk-examples=false \
  -D udev_rules_dir=/usr/lib/udev/rules.d -D udev_hwdb_dir=/usr/lib/udev/hwdb.d
%meson_build

%install
%meson_install

%post -p /sbin/ldconfig
%postun -p /sbin/ldconfig

%files
%license COPYING
%{_libdir}/libfprint-2.so
%{_libdir}/libfprint-2.so.*
%{_libdir}/pkgconfig/libfprint-2.pc
%{_includedir}/libfprint-2/
/usr/lib/udev/rules.d/70-libfprint-2.rules
/usr/lib/udev/hwdb.d/60-autosuspend-libfprint-2.hwdb
%{_datadir}/metainfo/org.freedesktop.libfprint.metainfo.xml

%changelog
* Sun Sep 13 2026 cosct <cosct@outlook.com> - 0.2.0-1
- Initial packaging of the egis0575 experimental driver (libfprint 1.94.100 + EH575).
