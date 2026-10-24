#!/usr/bin/env bash
# ZCF Distribution Package & Hierarchy Staging Builder
# Packages ZCF for Debian/Ubuntu, Arch, Fedora, and staged /usr hierarchy

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/staged_root"

echo "=========================================================="
echo "  Building Zyntrix Compatibility Fabric (ZCF) Packages"
echo "=========================================================="
echo "Project Root: $ROOT_DIR"
echo "Build Root:   $BUILD_DIR"

# Clean previous build
rm -rf "$BUILD_DIR" "$ROOT_DIR/dist"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/lib/binfmt.d"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/mime/packages"
mkdir -p "$BUILD_DIR/usr/share/metainfo"
mkdir -p "$BUILD_DIR/usr/share/man/man1"
mkdir -p "$BUILD_DIR/usr/share/bash-completion/completions"
mkdir -p "$BUILD_DIR/usr/share/zsh/site-functions"
mkdir -p "$BUILD_DIR/usr/share/fish/vendor_completions.d"
mkdir -p "$BUILD_DIR/usr/lib/systemd/system"
mkdir -p "$BUILD_DIR/usr/lib/python3/dist-packages"

echo "[1/6] Installing Python Source Packages..."
cp -r "$ROOT_DIR/src/zcf" "$BUILD_DIR/usr/lib/python3/dist-packages/"

echo "[2/6] Generating /usr/bin Executable Wrappers..."
cat << 'EOF' > "$BUILD_DIR/usr/bin/zcf"
#!/usr/bin/env python3
import sys
from zcf.cli.main import main
if __name__ == "__main__":
    main()
EOF
chmod 755 "$BUILD_DIR/usr/bin/zcf"

cat << 'EOF' > "$BUILD_DIR/usr/bin/zcf-runner"
#!/usr/bin/env python3
import sys
from zcf.cli.runner_entry import main
if __name__ == "__main__":
    main()
EOF
chmod 755 "$BUILD_DIR/usr/bin/zcf-runner"

cat << 'EOF' > "$BUILD_DIR/usr/bin/zcf-gui"
#!/usr/bin/env python3
import sys
from zcf.gui.main import main
if __name__ == "__main__":
    main()
EOF
chmod 755 "$BUILD_DIR/usr/bin/zcf-gui"

echo "[3/6] Installing binfmt_misc & Systemd Units..."
cp "$ROOT_DIR/data/binfmt.d/zcf.conf" "$BUILD_DIR/usr/lib/binfmt.d/"
cp "$ROOT_DIR/data/systemd/zcf-binfmt.service" "$BUILD_DIR/usr/lib/systemd/system/"
cp "$ROOT_DIR/data/systemd/zcf-prefix-cleaner.service" "$BUILD_DIR/usr/lib/systemd/system/"
cp "$ROOT_DIR/data/systemd/zcf-prefix-cleaner.timer" "$BUILD_DIR/usr/lib/systemd/system/"

echo "[4/6] Installing Freedesktop Desktop, MIME, and AppStream Metadata..."
cp "$ROOT_DIR/data/desktop/org.zyntrix.zcf.desktop" "$BUILD_DIR/usr/share/applications/"
cp "$ROOT_DIR/data/desktop/org.zyntrix.zcf.controlcenter.desktop" "$BUILD_DIR/usr/share/applications/"
cp "$ROOT_DIR/data/mime/org.zyntrix.zcf.xml" "$BUILD_DIR/usr/share/mime/packages/"
cp "$ROOT_DIR/data/metainfo/org.zyntrix.zcf.metainfo.xml" "$BUILD_DIR/usr/share/metainfo/"

echo "[5/6] Installing Manual Pages and Shell Completions..."
cp "$ROOT_DIR/docs/man/zcf.1" "$BUILD_DIR/usr/share/man/man1/"
cp "$ROOT_DIR/data/completions/bash/zcf" "$BUILD_DIR/usr/share/bash-completion/completions/"
cp "$ROOT_DIR/data/completions/zsh/_zcf" "$BUILD_DIR/usr/share/zsh/site-functions/"
cp "$ROOT_DIR/data/completions/fish/zcf.fish" "$BUILD_DIR/usr/share/fish/vendor_completions.d/"

echo "[6/6] Generating Debian .deb Package..."
DEB_DIR="/tmp/zcf_deb_build"
rm -rf "$DEB_DIR"
mkdir -p "$DEB_DIR/DEBIAN"
cp -r "$BUILD_DIR/usr" "$DEB_DIR/"
chmod 755 "$DEB_DIR"
chmod 755 "$DEB_DIR/DEBIAN"

cat << 'EOF' > "$DEB_DIR/DEBIAN/control"
Package: zcf
Version: 0.2.0-1
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), bubblewrap
Recommends: wine | wine64, qemu-user, xvfb
Maintainer: Zyntrix Labs Engineering <engineering@zyntrixlabs.org>
Description: Universal application compatibility fabric and runtime orchestrator
 ZCF coordinates existing compatibility engines (Wine, Proton, QEMU, Box64),
 investigates software behavior, diagnoses incompatibilities, applies reproducible
 fixes, and provides seamless binfmt_misc and desktop launcher integration.
EOF

chmod -R u=rwX,go=rX "$DEB_DIR"
chmod 755 "$DEB_DIR/usr/bin/zcf"
chmod 755 "$DEB_DIR/usr/bin/zcf-runner"
chmod 755 "$DEB_DIR/usr/bin/zcf-gui"
chmod 755 "$DEB_DIR/DEBIAN"

dpkg-deb --build "$DEB_DIR" "$ROOT_DIR/build/zcf_0.2.0-1_all.deb"
echo "Debian Package Built Successfully: $ROOT_DIR/build/zcf_0.2.0-1_all.deb"
echo "=========================================================="
echo "  Build Completed Successfully!"
echo "=========================================================="
