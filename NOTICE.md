# Project and attribution notice

The `assets/reference_topology.png` file was provided by the requester. All compose files, scripts, and Python simulators in this extension were newly authored for this package. Original mrhOTshOT project source is not bundled; cloning it onto the host via `scripts/setup.sh` remains subject to the upstream Apache-2.0 license and NOTICE/attribution requirements. The user-supplied reference image remains subject to its existing rights.

References:
- `https://github.com/AsherDLL/mrhOTshOT_Docker_pub` — original lab by Asher Davila and Malav Vyas.
- `https://helgeklein.com/blog/samba-active-directory-in-a-docker-container-installation-guide/` — architectural background for Dockerized Samba AD.

Do not commit `.env` or publish original upstream lab configuration files containing sample credentials.


### Optional dockur/windows integration (v4)

This project supplies original Docker Compose configuration and PowerShell helper scripts
for the external open-source `dockurr/windows` QEMU/KVM VM-in-a-container project,
https://github.com/dockur/windows (MIT-licensed repository). Its source code,
Docker images, Microsoft Windows ISOs, activation keys, and licenses are NOT
redistributed in this ZIP. Users must separately supply legally obtained Windows
installation media and license entitlement.
