#!/usr/bin/env bash
# Windows 11 ARM64 test VM for WinWhisper on Apple Silicon (QEMU + HVF).
#
#   vm/vm.sh install     # first run: unattended Windows install (~20-40 min)
#   vm/vm.sh start       # boot the installed VM headless
#   vm/vm.sh ssh [cmd]   # PowerShell over SSH (port 2222)
#   vm/vm.sh ps < x.ps1  # run a local PowerShell script in the VM
#   vm/vm.sh shot out.png  # screenshot of the VM display
#   vm/vm.sh keys ret ret  # send keys through the QEMU monitor
#   vm/vm.sh stop
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VM="${WINWHISPER_VM_DIR:-$HOME/winwhisper-vm}"
WIN_ISO="$VM/win11arm64-eval.iso"
VIRTIO_ISO="$VM/virtio-win.iso"
FIRMWARE="$(brew --prefix qemu)/share/qemu/edk2-aarch64-code.fd"
VARS_TEMPLATE="$(brew --prefix qemu)/share/qemu/edk2-arm-vars.fd"
SSH_PORT=2222

monitor() { printf '%s\n' "$@" | nc -U "$VM/mon.sock" >/dev/null; }

build_unattend_iso() {
  local dir="$VM/unattend"
  rm -rf "$dir" "$VM/unattend.iso"
  mkdir -p "$dir"
  cp "$HERE/autounattend.xml" "$HERE/setup.ps1" "$dir/"
  cp "$VM/ssh_key.pub" "$dir/authorized_keys"
  hdiutil makehybrid -quiet -iso -joliet -default-volume-name UNATTEND -o "$VM/unattend.iso" "$dir"
}

run_qemu() {
  local extra=("$@")
  qemu-system-aarch64 \
    -name winwhisper-vm \
    -M virt,highmem=on -accel hvf -cpu host -smp 6 -m 8G \
    -drive if=pflash,format=raw,readonly=on,file="$FIRMWARE" \
    -drive if=pflash,format=raw,file="$VM/vars.fd" \
    -device ramfb \
    -device qemu-xhci,id=xhci -device usb-kbd -device usb-tablet \
    -drive if=none,id=disk0,format=qcow2,file="$VM/disk.qcow2" \
    -device nvme,drive=disk0,serial=winwhisper0,bootindex=1 \
    -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22 \
    -rtc base=localtime \
    -monitor unix:"$VM/mon.sock",server,nowait \
    -qmp unix:"$VM/qmp.sock",server,nowait \
    -display none -vnc 127.0.0.1:5 \
    -daemonize -pidfile "$VM/qemu.pid" \
    "${extra[@]}"
}

case "${1:-}" in
  install)
    [ -f "$WIN_ISO" ] && [ -f "$VIRTIO_ISO" ] || { echo "ISOs missing in $VM"; exit 1; }
    [ -f "$VM/ssh_key" ] || ssh-keygen -t ed25519 -N "" -f "$VM/ssh_key" -C winwhisper-vm -q
    build_unattend_iso
    rm -f "$VM/disk.qcow2"
    qemu-img create -q -f qcow2 "$VM/disk.qcow2" 80G
    cp "$VARS_TEMPLATE" "$VM/vars.fd"
    run_qemu \
      -drive if=none,id=cd0,media=cdrom,readonly=on,file="$WIN_ISO" \
      -device usb-storage,drive=cd0,removable=true,bootindex=0 \
      -drive if=none,id=cd1,media=cdrom,readonly=on,file="$VIRTIO_ISO" \
      -device usb-storage,drive=cd1,removable=true \
      -drive if=none,id=cd2,media=cdrom,readonly=on,file="$VM/unattend.iso" \
      -device usb-storage,drive=cd2,removable=true
    # Get past "Press any key to boot from CD or DVD" (more presses would hit Setup's Cancel).
    for _ in $(seq 1 6); do sleep 1; monitor "sendkey ret"; done
    echo "installing; watch with: open vnc://127.0.0.1:5905  or  vm/vm.sh shot"
    ;;
  start)
    run_qemu \
      -drive if=none,id=cd1,media=cdrom,readonly=on,file="$VIRTIO_ISO" \
      -device usb-storage,drive=cd1,removable=true
    ;;
  ssh)
    shift
    exec ssh -q -i "$VM/ssh_key" -p $SSH_PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=5 ww@127.0.0.1 "$@"
    ;;
  ps)
    # PowerShell script from stdin (saved with a BOM so Windows PowerShell reads UTF-8).
    { printf '\xef\xbb\xbf'; cat; } > "$VM/_stdin.ps1"
    "$0" scp "$VM/_stdin.ps1" ww@127.0.0.1:C:/Users/ww/_stdin.ps1
    exec "$0" ssh "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\Users\\ww\\_stdin.ps1"
    ;;
  scp)
    shift
    exec scp -q -i "$VM/ssh_key" -P $SSH_PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$@"
    ;;
  shot)
    out="$(cd "$(dirname "${2:-shot.png}")" && pwd)/$(basename "${2:-shot.png}")"
    monitor "screendump ${out%.png}.ppm"
    sleep 1
    sips -s format png "${out%.png}.ppm" --out "$out" >/dev/null && rm -f "${out%.png}.ppm"
    echo "$out"
    ;;
  keys)
    shift
    for key in "$@"; do monitor "sendkey $key"; sleep 0.2; done
    ;;
  stop)
    monitor "system_powerdown" || true
    ;;
  kill)
    [ -f "$VM/qemu.pid" ] && kill "$(cat "$VM/qemu.pid")" || true
    ;;
  *)
    sed -n '2,10p' "$0"; exit 1 ;;
esac
