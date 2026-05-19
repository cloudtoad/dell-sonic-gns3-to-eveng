#!/usr/bin/env python3
"""Convert a GNS3 appliance into an EVE-NG installable bundle.

Two input modes:
    1. .gns3a file        -> prints the EVE-NG template YAML to stdout
    2. .zip (Dell-style)  -> writes a zipped EVE-NG install bundle that
       contains the template YAML, the renamed disk image, and an
       INSTALL.sh to be run on the EVE-NG host.

Usage:
    ./gns3a_to_eveng.py path/to/foo.gns3a [-o out.yml] [--id dellsonic]
    ./gns3a_to_eveng.py path/to/sonic_4.5.2.zip [-o out.zip] [--id dellsonic]
"""

import argparse
import json
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path

DISK_FILENAME = {
    "virtio": "virtioa.qcow2",
    "ide": "hda.qcow2",
    "sata": "sataa.qcow2",
    "scsi": "scsia.qcow2",
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def build_template_yaml(app: dict) -> tuple[str, str]:
    """Return (yaml_text, disk_filename) for the EVE-NG template."""
    q = app.get("qemu", {})
    name = app["name"]
    iface = q.get("hda_disk_interface", "ide")
    disk_name = DISK_FILENAME.get(iface, "hda.qcow2")

    lines = [
        f"# Converted from GNS3 appliance: {name}",
        "type: qemu",
        f"name: {name}",
        f"description: {app.get('description', name)}",
        "icon: Switch.png",
        "cpulimit: 1",
        f"cpu: {q.get('cpus', 1)}",
        f"ram: {q.get('ram', 1024)}",
        f"ethernet: {q.get('adapters', 1)}",
        f"console: {q.get('console_type', 'telnet')}",
        f"qemu_arch: {q.get('arch', 'x86_64')}",
        f"qemu_nic: {q.get('adapter_type', 'virtio-net-pci')}",
        "qemu_options: -machine type=pc,accel=kvm -serial mon:stdio "
        "-nographic -no-user-config -nodefaults -display none -rtc base=utc",
    ]

    fmt = app.get("port_name_format")
    if fmt:
        lines.append(f"eth_format: {fmt.replace('{port1}', '{1}')}")
    first = app.get("first_port_name")
    if first:
        n = q.get("adapters", 1)
        eth_names = [first] + [
            (fmt or "eth{port1}").replace("{port1}", str(i)) for i in range(1, n)
        ]
        lines.append("eth_name:")
        lines += [f"- {e}" for e in eth_names]

    return "\n".join(lines) + "\n", disk_name


INSTALL_SH = """#!/bin/bash
# Install this appliance on an EVE-NG host. Run as root.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d /opt/unetlab ]; then
    echo "ERROR: /opt/unetlab not found. Is this an EVE-NG host?" >&2
    exit 1
fi

echo "Installing template: ${TEMPLATE_ID}"
cp -v "$HERE/html/templates/intel/${TEMPLATE_ID}.yml" \
      /opt/unetlab/html/templates/intel/

mkdir -p "/opt/unetlab/addons/qemu/${TEMPLATE_ID}-${VERSION}"
cp -v "$HERE/addons/qemu/${TEMPLATE_ID}-${VERSION}/${DISK_NAME}" \
      "/opt/unetlab/addons/qemu/${TEMPLATE_ID}-${VERSION}/"

/opt/unetlab/wrappers/unl_wrapper -a fixpermissions
echo "Done. Appliance '${TEMPLATE_ID}' is now available in EVE-NG."
"""


def write_install_bundle(zip_in: Path, out_path: Path, template_id: str | None):
    with zipfile.ZipFile(zip_in) as zin:
        gns3a_names = [n for n in zin.namelist() if n.endswith(".gns3a")]
        img_names = [n for n in zin.namelist() if n.endswith(".img") or n.endswith(".qcow2")]
        if not gns3a_names or not img_names:
            sys.exit(f"ERROR: input zip must contain a .gns3a and a .img/.qcow2 (got {zin.namelist()})")
        gns3a_name, img_name = gns3a_names[0], img_names[0]

        app = json.loads(zin.read(gns3a_name))
        tid = template_id or slugify(app["name"])
        version = app.get("versions", [{}])[0].get("name", "1.0")
        yaml_text, disk_name = build_template_yaml(app)

        install = (INSTALL_SH
                   .replace("${TEMPLATE_ID}", tid)
                   .replace("${VERSION}", version)
                   .replace("${DISK_NAME}", disk_name))

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as zout:
            zout.writestr("INSTALL.sh", install)
            # mark executable
            info = zout.getinfo("INSTALL.sh")
            info.external_attr = (0o755 & 0xFFFF) << 16
            zout.writestr(f"html/templates/intel/{tid}.yml", yaml_text)

            # Stream the image without buffering all 3GB into memory.
            image_arc = f"addons/qemu/{tid}-{version}/{disk_name}"
            with zin.open(img_name) as src, zout.open(image_arc, "w", force_zip64=True) as dst:
                while chunk := src.read(8 * 1024 * 1024):
                    dst.write(chunk)

        return tid, version, disk_name, img_name


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path, help=".gns3a file or Dell-style .zip")
    p.add_argument("-o", "--out", type=Path)
    p.add_argument("--id", help="EVE-NG template id (default: slug of name)")
    args = p.parse_args()

    if args.input.suffix == ".zip":
        out = args.out or Path(f"{args.input.stem}-eveng.zip")
        tid, version, disk, src_img = write_install_bundle(args.input, out, args.id)
        print(f"Wrote: {out}", file=sys.stderr)
        print(f"  template_id : {tid}", file=sys.stderr)
        print(f"  version     : {version}", file=sys.stderr)
        print(f"  disk        : {disk}  (renamed from {src_img})", file=sys.stderr)
        print("", file=sys.stderr)
        print("On the EVE-NG host:", file=sys.stderr)
        print(f"  unzip {out.name} -d /tmp/eveng-pkg && sudo bash /tmp/eveng-pkg/INSTALL.sh", file=sys.stderr)
        return

    # .gns3a mode
    app = json.loads(args.input.read_text())
    tid = args.id or slugify(app["name"])
    yaml_text, disk_name = build_template_yaml(app)
    version = app.get("versions", [{}])[0].get("name", "1.0")
    src_img = app.get("versions", [{}])[0].get("images", {}).get("hda_disk_image", "<image>")

    if args.out:
        args.out.write_text(yaml_text)
    else:
        sys.stdout.write(yaml_text)

    print("", file=sys.stderr)
    print(f"Template id : {tid}", file=sys.stderr)
    print(f"Install YAML: /opt/unetlab/html/templates/intel/{tid}.yml", file=sys.stderr)
    print(f"Place image : /opt/unetlab/addons/qemu/{tid}-{version}/{disk_name}", file=sys.stderr)
    print(f"  (rename {src_img} -> {disk_name})", file=sys.stderr)
    print("Then on EVE-NG host: /opt/unetlab/wrappers/unl_wrapper -a fixpermissions", file=sys.stderr)


if __name__ == "__main__":
    main()
