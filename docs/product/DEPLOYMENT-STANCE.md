# Deployment Stance

> Current implementation warning: these are accepted target architectures. The Docker Sandboxes
> adapter, desktop broker, desktop installer, Linux guest installer, and Proxmox helper are not
> implemented yet.

The official installer entry point is the ADR-099/SPEC-209 web configurator. It emits a stable
bootstrap command referencing a signed, secret-free declarative manifest; it never generates
arbitrary shell from wizard input.

## The Guiding Rule

> Official installs always include VM-grade sandbox execution.
> Hive is optional. UI is optional.
> Workerless execution is never supported in production.
> Partial/control-plane-only installs are source-only paths.

## Default Installation Envelopes

| Environment | Default path |
|-------------|--------------|
| Windows/macOS | Docker Desktop + signed host sandbox broker + complete Maistro application in trusted Linux containers + Docker Sandbox workers |
| Linux, including Proxmox | Complete Maistro installation inside an Ubuntu Server 24.04 LTS x86-64 VM with nested KVM + Docker Sandbox workers |
| Unsupported environment | Fail preflight and explain the required desktop or Ubuntu VM envelope |

The default installer never silently replaces Docker Sandboxes with a shared-kernel container or
host subprocess.

## Desktop Boundary

On Windows and macOS:

- Maistro application services run in trusted Linux containers.
- A small signed native broker is the only Maistro component allowed to invoke `docker sandbox`/`sbx`
  or access explicitly registered source paths.
- Maistro containers receive a narrow mutually authenticated broker API, never the host Docker
  socket, arbitrary host paths, Docker credentials, or general Docker authority.
- Project registration is host-local and user-mediated. Runtime requests use opaque project IDs.
- Native Windows/macOS Maistro and WSL-based Maistro are custom/development paths.

See ADR-098 and SPEC-208.

## Linux and Hypervisor Boundary

On Linux and hypervisors:

- The complete Maistro installation runs inside a supported Ubuntu Server VM.
- Docker Sandboxes runs inside that VM using nested KVM.
- The Proxmox helper only provisions/configures the Ubuntu VM and invokes the common guest installer.
- Maistro is not installed directly on the Proxmox host and the default helper does not create
  per-campaign sibling VMs.

See ADR-097 and SPEC-207.

## Target Official Profiles

| Profile | Components | Use case |
|---------|------------|----------|
| `desktop-docker-sbx` | Docker Desktop + host broker + containerized Maistro + Docker Sandboxes | Windows/macOS default |
| `linux-ubuntu-vm-sbx` | Ubuntu Server VM + complete Maistro + Docker Sandboxes | Linux/hypervisor default |
| `full-ui` | API + worker + Hive + persistence inside the selected envelope | Full deployment |
| `full-headless` | API + worker + persistence inside the selected envelope | API-only deployment |

## Not Supported by the Default Installer

| Configuration | Reason | Path |
|---------------|--------|------|
| Native Windows/macOS Maistro | Expands native application authority | Custom/development only |
| WSL-based Maistro | Weaker host integration boundary and separate support path | Custom/development only |
| Direct Proxmox-host install | Expands the trusted hypervisor host | Use the Ubuntu VM helper |
| Host Docker socket mount | Effectively root/general Docker authority | Never production |
| Shared-kernel fallback | Changes security posture by environment | Explicit trusted custom workload only |
| Bare subprocess | No isolation | Never untrusted execution |
| Serverless/workerless production | No persistent safe execution worker | Never |

## Sandbox Ownership

- **Sandbox policy** lives in `maistro-core`.
- **Sandbox execution protocol** lives behind `maistro.sandbox.SandboxProtocol`.
- **Desktop host authority** lives only in the signed Maistro Sandbox Broker.
- **Sandbox display** lives in Hive Conductor.
- **Docker socket access** is prohibited for Maistro application containers and builder sandboxes.

## Backlogged Custom Providers

- Proxmox API-managed sibling builder VMs.
- Incus/libvirt/KVM VMs.
- gVisor, Kata, Firecracker, Hyperlight, and managed sandbox providers.
- Kubernetes/cloud-native automation.
- Bare-metal and non-Ubuntu direct installs.
- Trusted-workload rootless containers.

Custom providers must pass the common conformance suite and report their actual isolation tier.

## Target Installer Preflight

### Windows/macOS

- [ ] Supported Docker Desktop and Docker Sandboxes versions.
- [ ] Signed broker installed with authenticated local-only transport.
- [ ] No host Docker socket or arbitrary host path in the Maistro Compose bundle.
- [ ] Broker and sandbox conformance passes.
- [ ] Auth and non-default secrets configured.

### Linux/Proxmox

- [ ] Ubuntu Server 24.04 LTS x86-64.
- [ ] `/dev/kvm` and nested virtualization available.
- [ ] Docker Sandboxes installed/authenticated and conformance passes.
- [ ] No Docker socket mounted into Maistro application services.
- [ ] Auth and non-default secrets configured.

Failure of a required check stops the official install.
