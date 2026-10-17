#!/usr/bin/env bash
# AquaOS-Beta Bootable Immutable Live/Install ISO Builder (build-iso.sh)
# Produces dist/aquaos-1.0-amd64.iso using debootstrap + SquashFS + GRUB2 (BIOS & UEFI)

set -euo pipefail

WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="/tmp/aquaos-iso-build"
CHROOT_DIR="${BUILD_ROOT}/chroot"
ISO_STAGING="${BUILD_ROOT}/iso"
DIST_DIR="${WORKSPACE_DIR}/dist"
ISO_OUTPUT="${DIST_DIR}/aquaos-1.0-amd64.iso"
DEBIAN_RELEASE="${DEBIAN_RELEASE:-bookworm}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-http://deb.debian.org/debian}"

echo "=================================================================="
echo "  Building AquaOS 1.0 Beta (Sonoma-AI • Virus-Proof Edition) ISO  "
echo "=================================================================="

mkdir -p "${BUILD_ROOT}" "${ISO_STAGING}/live" "${ISO_STAGING}/boot/grub" "${DIST_DIR}"

# 1. Bootstrap minimal Debian/Ubuntu base system
if [ ! -f "${CHROOT_DIR}/bin/bash" ]; then
    echo "[1/6] Running debootstrap (${DEBIAN_RELEASE})..."
    debootstrap --arch=amd64 --variant=minbase "${DEBIAN_RELEASE}" "${CHROOT_DIR}" "${DEBIAN_MIRROR}"
fi

# 2. Configure chroot package installation (Kernel, Wayland/X11, GTK4 Layer Shell, Bubblewrap, Wine, Flatpak)
echo "[2/6] Installing Linux Kernel, Aqua Desktop dependencies, Security & AI runtimes..."
cat << 'EOF' > "${CHROOT_DIR}/tmp/setup-chroot.sh"
#!/usr/bin/env bash
set -e
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
    linux-image-amd64 \
    live-boot \
    systemd-sysv \
    network-manager \
    pipewire \
    pipewire-pulse \
    wireplumber \
    wayland-protocols \
    labwc \
    wlr-randr \
    swaybg \
    openbox \
    picom \
    xorg \
    lightdm \
    python3 \
    python3-gi \
    gir1.2-gtk-4.0 \
    libgtk4-layer-shell0 \
    bubblewrap \
    apparmor \
    nftables \
    flatpak \
    p7zip-full \
    foot \
    nautilus \
    firefox-esr \
    curl \
    sudo \
    ca-certificates \
    zram-tools

# Create live user 'aqua' with password 'aqua'
if ! id -u aqua >/dev/null 2>&1; then
    useradd -m -s /bin/bash -G sudo,video,render,audio,netdev aqua
    echo "aqua:aqua" | chpasswd
    echo "aqua ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/aqua
fi

# Configure OS identity
cat << 'OSREL' > /etc/os-release
PRETTY_NAME="AquaOS 1.0 Beta (Sonoma-AI)"
NAME="AquaOS"
VERSION_ID="1.0"
VERSION="1.0 Beta (Sonoma-AI • Virus-Proof Edition)"
ID=aquaos
ID_LIKE=debian
HOME_URL="https://aquaos.local"
OSREL

echo "aquaos-macbook" > /etc/hostname

# Enable Zero-Trust Firewall & NetworkManager
systemctl enable nftables || true
systemctl enable NetworkManager || true

apt-get clean
rm -rf /var/lib/apt/lists/*
EOF

chmod +x "${CHROOT_DIR}/tmp/setup-chroot.sh"
chroot "${CHROOT_DIR}" /tmp/setup-chroot.sh
rm -f "${CHROOT_DIR}/tmp/setup-chroot.sh"

# 3. Install AquaOS Desktop, Universal Runtime, Security & AI Subsystem into /opt/aquaos
echo "[3/6] Installing Aqua Desktop, Aqua Intelligence, and Aqua Shield into rootfs..."
mkdir -p "${CHROOT_DIR}/opt/aquaos" "${CHROOT_DIR}/Applications"
cp -r "${WORKSPACE_DIR}/aqua-desktop/"* "${CHROOT_DIR}/opt/aquaos/"

# Install Kernel AI Tuning & Hardening Policies
cp -f "${WORKSPACE_DIR}/iso-builder/security/98-aquaos-ai-tuning.conf" "${CHROOT_DIR}/etc/sysctl.d/"
cp -f "${WORKSPACE_DIR}/iso-builder/security/99-aquaos-hardening.conf" "${CHROOT_DIR}/etc/sysctl.d/"
cp -f "${WORKSPACE_DIR}/iso-builder/security/nftables.conf" "${CHROOT_DIR}/etc/nftables.conf"

# Create CLI wrappers in /usr/local/bin
install -m 0755 "${WORKSPACE_DIR}/aqua-desktop/session/aqua-session" "${CHROOT_DIR}/usr/local/bin/aqua-session"

cat << 'EOF' > "${CHROOT_DIR}/usr/local/bin/aqua-run"
#!/usr/bin/env bash
exec python3 /opt/aquaos/universal/aqua_run.py "$@"
EOF
chmod +x "${CHROOT_DIR}/usr/local/bin/aqua-run"

cat << 'EOF' > "${CHROOT_DIR}/usr/local/bin/aqua-pkg"
#!/usr/bin/env bash
exec python3 /opt/aquaos/universal/aqua_pkg.py "$@"
EOF
chmod +x "${CHROOT_DIR}/usr/local/bin/aqua-pkg"

# Register Wayland and X11 session entries + LightDM autologin
mkdir -p "${CHROOT_DIR}/usr/share/wayland-sessions" "${CHROOT_DIR}/usr/share/xsessions"
cp -f "${WORKSPACE_DIR}/aqua-desktop/session/aquaos.desktop" "${CHROOT_DIR}/usr/share/wayland-sessions/aquaos.desktop"
cp -f "${WORKSPACE_DIR}/aqua-desktop/session/aquaos.desktop" "${CHROOT_DIR}/usr/share/xsessions/aquaos.desktop"

# 4. Compress Immutable RootFS into SquashFS
echo "[4/6] Compressing immutable read-only SquashFS image..."
mksquashfs "${CHROOT_DIR}" "${ISO_STAGING}/live/filesystem.squashfs" -comp xz -b 1M -noappend

# 5. Copy Kernel & Initramfs and Configure GRUB2 Bootloader
echo "[5/6] Configuring GRUB2 Bootloader (Immutable Safe Mode, Persistent Mode & AI Boost Mode)..."
cp -f "${CHROOT_DIR}"/boot/vmlinuz-* "${ISO_STAGING}/boot/vmlinuz"
cp -f "${CHROOT_DIR}"/boot/initrd.img-* "${ISO_STAGING}/boot/initrd.img"

cat << 'EOF' > "${ISO_STAGING}/boot/grub/grub.cfg"
set default="0"
set timeout=5

menuentry "AquaOS 1.0 Beta (Sonoma-AI • Immutable Virus-Proof Mode)" {
    linux /boot/vmlinuz boot=live components quiet splash lockdown=integrity transparent_hugepage=madvise
    initrd /boot/initrd.img
}

menuentry "AquaOS 1.0 Beta (AI Neural Boost • Maximum VRAM/RAM Mode)" {
    linux /boot/vmlinuz boot=live components quiet splash transparent_hugepage=always mitigations=off
    initrd /boot/initrd.img
}

menuentry "AquaOS 1.0 Beta (Clean Factory Reset / Forensic RAM-Only Session)" {
    linux /boot/vmlinuz boot=live toram nopersistence quiet
    initrd /boot/initrd.img
}
EOF

# 6. Build Hybrid BIOS/UEFI Bootable ISO
echo "[6/6] Generating bootable ISO at ${ISO_OUTPUT}..."
grub-mkrescue -o "${ISO_OUTPUT}" "${ISO_STAGING}"

echo "=================================================================="
echo "  SUCCESS! Bootable ISO created at: ${ISO_OUTPUT}"
echo "  SHA-256: $(sha256sum "${ISO_OUTPUT}" | awk '{print $1}')"
echo "=================================================================="
