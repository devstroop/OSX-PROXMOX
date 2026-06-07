#!/usr/bin/env python3
"""
Download full macOS recovery image for Proxmox VM.
Delegates to macrecovery.py for BaseSystem, then builds a bootable FAT32 ISO.
"""

import os
import subprocess
import sys
import shutil

SELF_DIR = os.path.dirname(os.path.realpath(__file__))
MACRECOVERY = os.path.join(SELF_DIR, 'macrecovery', 'macrecovery.py')


def run(cmd, **kwargs):
    print("Running: " + " ".join(cmd))
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f'Error: command failed with code {result.returncode}')
        sys.exit(1)
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Download macOS recovery & build ISO')
    parser.add_argument('-b', '--board-id', default='Mac-827FAC58A8FDFA22')
    parser.add_argument('-m', '--mlb', default='00000000000000000')
    parser.add_argument('-os', '--os-type', default='default', choices=['default', 'latest'])
    parser.add_argument('-o', '--output', default=None,
                        help='Output ISO path (default: recovery-<name>.iso)')
    parser.add_argument('--iso-label', default=None,
                        help='FAT32 volume label (default: derived from board-id)')
    parser.add_argument('--keep-files', action='store_true',
                        help='Keep downloaded files after building ISO')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    work_dir = f'/tmp/recovery_work_{args.board_id.split(",")[0]}'
    recovery_dir = os.path.join(work_dir, 'com.apple.recovery.boot')
    os.makedirs(recovery_dir, exist_ok=True)

    # Step 1: Download recovery using macrecovery.py
    print('=== Step 1: Downloading recovery via macrecovery.py ===')
    mac_cmd = [
        sys.executable, MACRECOVERY,
        '-b', args.board_id,
        '-m', args.mlb,
        'download', '-o', recovery_dir,
    ]
    if args.os_type == 'latest':
        mac_cmd.insert(5, '-os')
        mac_cmd.insert(6, 'latest')
    if args.verbose:
        mac_cmd.append('-v')

    run(mac_cmd)

    # List downloaded files
    files = [f for f in os.listdir(recovery_dir) if os.path.isfile(os.path.join(recovery_dir, f))]
    print(f'\nDownloaded files: {files}')

    # Step 2: Check total size
    total_mb = sum(os.path.getsize(os.path.join(recovery_dir, f))
                   for f in files) / (2**20)
    iso_size_mb = max(int(total_mb * 1.05) + 10, 800)
    print(f'Estimated ISO size: {iso_size_mb} MB')

    # Step 3: Build ISO
    print('\n=== Step 2: Building recovery ISO ===')
    label = args.iso_label or args.board_id.split('-')[0][:11]
    iso_path = args.output or os.path.join(
        os.path.dirname(os.path.abspath(recovery_dir)),
        f'recovery-{label.lower()}.iso'
    )

    tmp_iso = iso_path + '.tmp'
    run(['fallocate', '-x', '-l', f'{iso_size_mb}M', tmp_iso])
    run(['mkfs.msdos', '-F', '32', tmp_iso, '-n', label.upper()[:11]])

    loopdev = run(['losetup', '-f', '--show', tmp_iso],
                  capture_output=True, text=True).stdout.strip()
    mount_pt = f'/mnt/recovery_iso_{label}'
    os.makedirs(mount_pt, exist_ok=True)

    run(['mount', loopdev, mount_pt])
    boot_dir = os.path.join(mount_pt, 'com.apple.recovery.boot')
    os.makedirs(boot_dir, exist_ok=True)

    for fname in files:
        shutil.copy2(os.path.join(recovery_dir, fname), boot_dir)

    run(['sync'])
    run(['umount', mount_pt])
    run(['losetup', '-d', loopdev])
    os.rmdir(mount_pt)
    os.rename(tmp_iso, iso_path)

    print(f'\nISO created: {iso_path} ({iso_size_mb} MB)')
    print(f'  Files included: {files}')

    if not args.keep_files:
        shutil.rmtree(work_dir)

    return 0


if __name__ == '__main__':
    sys.exit(main())
