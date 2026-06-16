---
id: SPEC-207
title: Secure default Linux installer and Proxmox VM provisioner
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-06-12
substrate:
  - maistro-engine#ADR-097
implements:
  - maistro-engine#ADR-097
related:
  - maistro-engine#SPEC-180
  - maistro-engine#SPEC-190
  - maistro-engine#ADR-098
  - maistro-engine#SPEC-208
contracts:
  - boundary
  - behavioral
tests: []
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-207: Secure Default Linux Installer

## Goal

Ship one simple installer path whose runtime and security boundary are identical across supported
Linux hypervisors: a complete Maistro installation inside an Ubuntu Server VM, with untrusted work
executed by Docker Sandboxes inside that VM.

Windows and macOS use the separate containerized desktop plus host broker path in ADR-098 and
SPEC-208.

## Components

### Common Ubuntu guest installer

The common installer runs inside Ubuntu Server 24.04 LTS x86-64 and:

1. verifies Ubuntu version, architecture, `/dev/kvm`, and nested virtualization;
2. installs or verifies the pinned Docker and Docker Sandboxes dependencies;
3. verifies required Docker authentication without copying credentials into builder sandboxes;
4. installs the complete Maistro control plane, UI when selected, persistence, and sandbox worker;
5. starts a disposable conformance sandbox before reporting success;
6. fails closed without offering an automatic lower-isolation fallback.

### Proxmox helper

The Proxmox helper is a convenience provisioner, not a separate deployment architecture. It:

1. creates an Ubuntu Server 24.04 LTS x86-64 VM from a pinned image/template;
2. configures CPU virtualization passthrough/nested KVM, memory, disk, and network;
3. injects only the minimum bootstrap material needed to invoke the common guest installer;
4. waits for guest preflight and conformance results;
5. prints recovery and connection information.

The helper does **not** install Maistro on the Proxmox host, create LXC workers, create per-campaign
sibling VMs, or leave a privileged Maistro service on the host.

### Other Linux hypervisors

For the first supported release, documentation tells operators how to provision the required Ubuntu
VM and run the common guest installer. Hypervisor-specific automation beyond the Proxmox helper is
backlogged.

## Backlog, Not Default Installer Branches

- Proxmox sibling builder VMs
- Incus/libvirt VM lifecycle adapters
- gVisor, Kata, and Firecracker sandbox providers
- Kubernetes and cloud-native deployment automation
- Managed sandbox services
- Bare-metal and non-Ubuntu direct installation
- Shared-kernel container mode for explicitly trusted workloads

## Required Tests

- Clean Proxmox VM provisioning and repeatable rerun.
- Clean generic Ubuntu VM guest installation.
- Missing nested virtualization and missing `/dev/kvm` fail before Maistro enables execution.
- Docker Sandboxes conformance covers sanitized staging-repo clone isolation, disabled push URLs,
  absence of inherited credentials, socket isolation, network policy, limits, persistence/resume,
  artifact export, and teardown.
- The helper cannot mutate unrelated Proxmox resources and does not leave guest credentials on the
  Proxmox host.
