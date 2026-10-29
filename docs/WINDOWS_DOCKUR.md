# SOLARIS ONE v4 — Windows with dockur/windows + Samba Active Directory

This is an **optional QEMU/KVM virtual-machine layer** in a Docker Compose profile. `dockurr/windows` is **not a native Windows container** and does not eliminate the need for Windows licensing or hardware virtualization. Each of the three services below installs a full Windows guest and runs as an isolated QEMU process *inside* a Docker container.

**Status:** Configurations and static tests verified, **not end-to-end boot-tested** here: this build environment has no `/dev/kvm` or Docker. Run the verification scripts on your Linux Docker host and complete domain joins inside the Windows guests.

## Architecture

| Service / Windows name | Zone / Linux Docker container address | Windows release | DC / domain | Browser desktop on Docker host | RDP on Docker host |
|---|---|---|---|---|---|
| `win-it` / SOLAR-IT-WS01 | L4 / `10.0.0.40` | Windows 11 **Pro** | `10.0.0.10` / `CORP.OTLAB.TEST` | `http://127.0.0.1:8006` | `127.0.0.1:33891` |
| `win-server` / SOLAR-FILE01 | L4 / `10.0.0.41` | Windows Server 2022 | `10.0.0.10` / `CORP.OTLAB.TEST` | `http://127.0.0.1:8007` | `127.0.0.1:33892` |
| `win-ot` / SOLAR-ENG-WS01 | L3 / `172.18.10.40` | Windows 11 **Pro** | `172.18.10.10` / `ICS.OTLAB.TEST` | `http://127.0.0.1:8008` | `127.0.0.1:33893` |

The container-side static address belongs to the **dockur hypervisor container**, not the QEMU Windows guest; dockur NAT gives the Windows guest its *own* address, generally on a nested guest subnet. Do not assume Windows has the same IP as its container. Docker's named-bridge network permits the Windows guest to **initiate** connections to Samba DC and permitted application services through dockur NAT; other Docker devices cannot necessarily initiate connections to the Windows guest. For direct routable Windows guest addresses, design a VLAN/macvtap network separately and retest the isolation policy. The quick-start does **not** create multi-homed Windows machines or attach them to L0/L1.

**Samba DCs remain Linux containers.** A genuine Windows Server 2022 guest can be joined as a member server, but it is not automatically promoted to an AD DC and should not be promoted as part of this independent Samba AD demo. No trust or replication is configured across the two domains.

## 1. Host requirements

* Linux Docker Engine + Compose v2 (not a Docker Desktop installation without KVM access).
* `/dev/kvm` and `/dev/net/tun` available **inside the Linux Docker host VM**.
* If the Docker host is itself a Proxmox VM, configure its CPU type as `host`, ensure nested virtualization is enabled on the Proxmox node and verify `/dev/kvm` inside the guest. This is **nested KVM/QEMU** and adds additional complexity/overhead compared with running Windows directly in Proxmox.
* Recommended **8 GB RAM for basic solar services plus 4 GB per Windows guest plus host overhead**, e.g. at least **24 GB dedicated to Docker host** for all three Windows guests and SOC optional services; use more for normal responsiveness. Real needs depend on software.
* Allow >=64 GB virtual disk per Windows guest plus space for ISOs, images, updates, and application installs. Provision at least 160–220 GB free disk for all three for a comfortable lab (sparse disks can consume less initially).
* Local Windows install media and valid licenses. Windows 11 **Home** cannot join an AD domain; use Windows 11 Pro/Enterprise/Education. For Server 2022 use a Desktop Experience edition if you need a GUI.
* Expose only **loopback web/RDP bindings** on the Docker host. Use `ssh -L 8006:127.0.0.1:8006 user@docker-host` from a remote laptop, then access `http://127.0.0.1:8006` locally. Repeat with ports 8007/8008 as needed. Keep Docker's control API/socket inaccessible.

Verify KVM inside the Linux guest:

```bash
ls -l /dev/kvm /dev/net/tun
sudo apt-get install -y cpu-checker
sudo kvm-ok
```

If unavailable, **do not** force software-emulated Windows as a fallback. It is substantially slower and unverified in this lab. Instead run Windows Proxmox VMs with appropriately routed/isolated networks.

## 2. Supply the Windows ISOs

The OT/corporate zone networks are `internal: true`, so dockur **cannot download Microsoft ISO files at runtime**. Place your own **official, locally acquired** ISOs at:

```text
windows-media/windows11.iso          # Windows 11 Pro, used for IT + OT guests
windows-media/windowsserver2022.iso  # Windows Server 2022 member server
```

Only those guests for which an ISO is available can start. `./scripts/windows-up.sh` refuses to start if the corresponding ISO is missing. This is intentional; do not add an internet uplink to `level3` or `level4` just to download Windows. Store the ISOs in this ignored directory; never commit or redistribute them.

## 3. Start the base solar range and Windows guests

```bash
sudo apt-get install -y python3-yaml
./scripts/setup.sh
./scripts/up.sh
./scripts/check_lab.sh
./scripts/windows-up.sh it       # one corporate Windows 11 VM
./scripts/windows-up.sh server   # optional Windows Server 2022 member VM
./scripts/windows-up.sh ot       # optional OT Windows 11 engineering VM
# or ./scripts/windows-up.sh all, if CPU/RAM/ISOs suffice
./scripts/windows-doctor.sh
```

The first Windows boot provisions Windows from the **local ISO** and creates a persistent virtual disk under `windows-data/`. Never use `docker compose down -v` on a volume containing production data. The Windows disk paths remain on the Docker host; deleting them destroys installed OS state.

## 4. Join AD securely *after installation*

Automatic domain join exists in dockur, but its `DOMAIN/USERNAME/PASSWORD` parameters would place domain-join account credentials into Docker's configuration. This package **deliberately avoids storing AD administrator credentials inside Windows container environment variables** and uses manual joining instead.

Inside the Windows guest, open **PowerShell as Administrator** and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
& 'Z:\Join-LabDomain.ps1' -Zone Corporate    # win-it or win-server
# OR
& 'Z:\Join-LabDomain.ps1' -Zone OT           # win-ot
```

The `/shared` bind mount makes the `windows-tools/` directory available as Windows `Z:\` when the dockur shared-folder component is working. If not, copy the script into the guest using RDP or a temporary restricted file-transfer method.

The script sets Windows guest DNS to the relevant Samba DC, verifies `_ldap._tcp.dc._msdcs` DNS records and DC TCP ports 88/389/445, prompts for `CORP\Administrator` or `ICS\Administrator` credentials *without storing them*, joins the domain, and restarts Windows. Get the relevant domain admin password on the Linux Docker host (never paste into screenshots or chat):

```bash
sed -n '/^CORP_AD_ADMIN_PASSWORD=/p' .env
sed -n '/^ICS_AD_ADMIN_PASSWORD=/p' .env
```

Inside the Windows guest, **first run** the check-only variant if uncertain:

```powershell
& 'Z:\Join-LabDomain.ps1' -Zone Corporate -CheckOnly
& 'Z:\Test-LabConnectivity.ps1' -Zone Corporate
& 'Z:\Add-Solar-Shortcuts.ps1' -Zone Corporate
```

After reboot, check `Get-CimInstance Win32_ComputerSystem | Select Name,Domain,PartOfDomain`. In Samba, confirm the new machine account:

```bash
docker compose exec dc01 samba-tool computer list
docker compose exec ics-dc01 samba-tool computer list
```

## 5. Realistic, permitted plant workflows from Windows

* From **Level 4** Windows guest, work orders at `http://10.0.0.31:8080` and the read-only historian API at `http://10.0.0.30:8080/api/devices/latest`. Historian returns 401 without valid corporate AD credentials. The API is intentionally lab-only HTTP Basic, **not** production HTTPS/SSO. Windows corporate guests have **no** Level 1/Level 2 NIC.
* From **Level 3** Windows engineering guest, read-only L2 SCADA page and `/api/state` at `http://172.18.10.31:8080`. This conduit allows **GET only**, not POST `/api/control`; the engineering desktop cannot dispatch PPC power commands through this route. OT domain account authentication works only against `ICS.OTLAB.TEST`; there is no corporate cross-domain trust.
* A Windows Server guest can be used as an administrative/file/application server after manually installing roles; no Windows roles or Microsoft SQL Server are preinstalled. The existing DB01 in the lab is PostgreSQL, and the existing CA01 is **not** Microsoft AD CS.

## 6. Troubleshooting

| Symptom | Check |
|---|---|
| `/dev/kvm` missing | Proxmox nested virtualization, host CPU type, VM KVM modules, guest device permissions |
| Windows installer never starts | Missing or invalid ISO, wrong edition, insufficient disk/RAM; `docker compose -f compose.yaml -f compose.windows.yaml logs win-it` |
| Domain join: domain not found | Windows adapter DNS must be `10.0.0.10` or `172.18.10.10`; run `Resolve-DnsName -Type SRV _ldap._tcp.dc._msdcs.corp.otlab.test -Server 10.0.0.10` |
| DNS works but AD join fails | Samba process and DNS/Kerberos/LDAP/SMB ports; host clock difference (Kerberos typically requires <=5 min skew), Windows SKU/domain credential |
| Windows web viewer fails | Check loopback port conflicts and Docker container logs; do not publicly publish web viewer |
| Windows can't open Level 4 application | Check `docker compose ps corp-portal it-access`; the corporate guest talks to container IPs through NAT |
| Windows guest has DNS but cannot browse Internet | Expected: Docker L3/L4 networks are internal-only; installation ISOs and update packages are staged offline |
| RDP won't connect | Windows RDP capability/edition, Windows firewall, and dockur port mapping; browser VNC viewer is initial fallback |

**Source:** [dockur/windows](https://github.com/dockur/windows), [environment options](https://github.com/dockur/windows/blob/master/docs/environment.md). Its `DOMAIN` feature assumes working DC DNS and connectivity, which these scripts test. `dockurr/windows` is an external dependency, not vendored in this ZIP.


## v5 operational Windows roles — manual guest installation

These three dockurr/windows services boot Windows **VMs**, but Docker **does not configure Windows Server roles or engineering software by itself**. After Windows is installed and joined to the correct domain, open PowerShell inside each guest:

* `win-server` (Windows Server 2022, CORP domain): run elevated `Z:\Install-SolarFileServer.ps1`. Installs the native `FS-FileServer` feature and creates `\\SOLAR-FILE01\SolarMaintenance` for corporate maintenance report exchange. Verify `Get-SmbShare SolarMaintenance` and SMB TCP/445 connectivity within L4.
* `win-it` (Windows 11, CORP domain): run `Z:\Install-SolarWorkstation.ps1 -Role IT` to create the portal shortcut; run `Z:\Get-SolarMaintenance.ps1` to export real DB01 work orders (including auto-generated PV faults). It writes a local CSV and copies it to the share if reachable.
* `win-ot` (Windows 11, ICS domain): run `Z:\Install-SolarWorkstation.ps1 -Role OT`; run `Z:\Get-SolarEngineeringSnapshot.ps1 -Samples 12 -Seconds 5` to record actual SCADA telemetry as a CSV. It can GET only the L3 read-only SCADA relay, **not** the PPC control endpoint or L1 inverters.

Windows guest addressing is managed by dockurr's QEMU guest network, **not** the Docker container's advertised IP. Domain join and visibility need verification inside the guest with `ipconfig /all`, `Resolve-DnsName _ldap._tcp.corp.otlab.test -Type SRV` / ICS equivalent, `Test-NetConnection`, and `whoami /fqdn`. Scripts cannot guarantee host reachability because dockurr networking depends on its QEMU adapter, DHCP and container bridge; test the guest routes before treating the role as operational.

The scripts above use PowerShell and Windows features; no proprietary SCADA engineering packages or commercial Windows licenses are bundled. Corporate and OT domains have no trust and no cross-network SMB access.
