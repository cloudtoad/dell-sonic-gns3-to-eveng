# dell-sonic-gns3-to-eveng

Convert the **Dell Enterprise SONiC** GNS3 download into an installable
EVE-NG appliance bundle.

## What it does

Dell ships its Enterprise SONiC GNS3 appliance as a zip containing a
`.gns3a` metadata file and an `.img` disk image. EVE-NG can't import
that format directly. This script takes the Dell zip and emits a new
zip that mirrors the `/opt/unetlab/` directory layout, with:

- the EVE-NG template YAML
- the disk image renamed to what EVE-NG expects (`virtioa.qcow2`)
- an `INSTALL.sh` to drop everything into place and fix permissions

## Usage

```
python3 gns3a_to_eveng.py sonic_4.5.2.zip --id dellsonic
```

Writes `sonic_4.5.2-eveng.zip` in the current directory.

## Install on an EVE-NG host

```
unzip sonic_4.5.2-eveng.zip -d /tmp/eveng-pkg \
    && bash /tmp/eveng-pkg/INSTALL.sh'
```

`INSTALL.sh` copies the template YAML into
`/opt/unetlab/html/templates/intel/`, the disk image into
`/opt/unetlab/addons/qemu/<id>-<version>/`, and runs
`unl_wrapper -a fixpermissions`. Refresh the EVE-NG web UI and the
appliance appears in the node-add menu.

## Tested

- EVE-NG Community 6.2.0-4
- Dell Enterprise SONiC 4.5.1 and 4.5.2
- Two-node lab with LLDP neighbor discovery between converted nodes

## Caveats

- `qemu_options` uses a generic kvm/serial line; tune the emitted YAML
  if your environment needs specific flags (e.g. `-cpu host`, `-smp`).
- KVM is required on the EVE-NG host (nested virt counts).
- Icon defaults to `Switch.png`. Edit the YAML if you want a different
  icon from `/opt/unetlab/html/images/icons/`.

## License

MIT
