---
id: ADR-026
title: "Internal Trust Root — Local CA from Conductor Seed"
repo: maistro-engine
kind: adr
status: Proposed
created: 2026-05-07
substrate:
  - maistro-engine#ADR-021
  - maistro-engine#ADR-024
implements: []
related:
  - maistro-engine#ADR-020
  - maistro-engine#ADR-029
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
tests: []
layer: Governance
owners:
  - '@BlakeMatthews-dev'
---

# ADR-026: Internal Trust Root — Local CA from Conductor Seed

**Status:** Proposed
**Date:** 2026-05-07
**Depends on:** ADR-021 (Conductor Seed), ADR-024 (DID/VC Identity)

---

## Context

The conductor needs valid HTTPS for internal hostnames that don't have public-CA chains — mesh hostnames, LAN mDNS names, localhost. Self-signed certs show warnings forever. The only working path is: be your own CA, and get devices to trust your CA root.

This is **not a stopgap.** It's a permanent capability for operators who explicitly don't want public PKI in their trust chain — the same audience that runs their own Bitcoin node and holds their own seed phrase.

**Source:** `Project_mAIstro/specs/security/S-155-internal-trust-root.md` (265 lines)

## Decision

The conductor mints an X.509 Certificate Authority deterministically derived from the Conductor Seed (ADR-021), constrained to the conductor's own hostnames, with a trust install ceremony for household devices.

### Key derivation

```
ca_secret = HKDF(
    ikm  = bip39_seed_bytes,        # from ADR-021
    salt = "maistro-tls-ca-v1",
    info = instance_name,
    L    = 32                        # P-256 key size
)
```

Properties:
- **Deterministic** — restore seed → same CA → already-installed trust roots remain valid
- **Independent of BIP32 paths** — lives in HKDF-space, no collision with wallet derivations
- **P-256** — universally supported in X.509 / TLS / OS trust stores

### CA cert properties

- **Subject CN:** `<instance-name> Conductor CA`
- **Validity:** 10 years, auto-regenerated
- **Key usage:** Certificate Sign, CRL Sign
- **Name Constraints (critical):** restricted to conductor's hostnames only
- **Basic Constraints:** `CA:TRUE, pathlen:0`

**Name Constraints is the load-bearing safety property.** The CA can ONLY issue valid certs for the conductor's own hostnames. It cannot impersonate google.com or any other site.

### Leaf certs

Short-lived (90-day), auto-rotated, covering all conductor-served hostnames (dashboard, DID document, message board, Lightning endpoint, Electrum port).

### TLS modes (operator choice)

| Mode | Behavior |
|---|---|
| `public-ca` | Use substrate-provided LE certs. Local CA exists but unused. |
| `local-ca` | Sovereignty mode. Conductor serves own CA leaves exclusively. Zero public-PKI outbound. |
| `both` | Parallel chains. Useful during migration. |

Mode is reversible, switchable at any time. The local CA does **not** retire when public-CA paths become available.

### Trust install ceremony

QR-code-based one-time install URL at `/trust/<token>`:
1. Fetches CA cert in DER + PEM
2. Detects platform, presents right install path
3. Per-platform matrix (macOS, Windows, Linux, iOS, Android)
4. Install ceremony recorded as a Verifiable Credential (ADR-024)
5. Device compromise → VC revoked from dashboard → CA rotated

### DID anchoring

DID document (ADR-024) includes service entry advertising the CA:

```json
{
  "id": "#tls-trust-anchor",
  "type": "X509TrustAnchor",
  "serviceEndpoint": {
    "caCertSha256": "<hash>",
    "nameConstraints": ["*.brigid.local"],
    "validFrom": "2026-04-25",
    "validUntil": "2036-04-25"
  }
}
```

## Interface (spec)

```python
@dataclass
class LocalCA:
    def get_ca_cert_pem(self) -> str: ...
    def issue_leaf(self, hostnames: list[str]) -> str: ...  # returns leaf PEM
    def get_ca_fingerprint(self) -> str: ...
    def rotate(self) -> None: ...  # advances HKDF salt

class TrustInstaller:
    def generate_install_url(self, ttl_hours: int = 24) -> str: ...
    def verify_install(self, device_fp: str) -> bool: ...
    def revoke_device(self, device_fp: str) -> None: ...
```

## Acceptance criteria

- [ ] CA derived deterministically from seed; same seed → same CA across reinstalls
- [ ] CA cert includes Name Constraints restricting issuance to conductor's hostnames
- [ ] Leaf certs auto-rotated at 90-day intervals
- [ ] QR install ceremony works on macOS/Windows/Linux/iOS/Android browsers
- [ ] iOS install walks user through two-step trust-enable flow
- [ ] DID document publishes CA fingerprint + name constraints as X509TrustAnchor service
- [ ] Trust install recorded as VC; revocable from dashboard
- [ ] Name Constraints enforcement: malicious cert for `google.com` rejected by browsers
- [ ] TLS mode operator-controlled and reversible
- [ ] `local-ca` mode: zero LE/ACME/OCSP/CT outbound traffic verifiable via tcpdump

## Out of scope

- Public CA functionality (name constraints prevent this)
- Mobile app cert pinning (future native app concern)
- Substrate-mediated CA distribution (speculative, v3)
- Forcing one TLS mode over another

## Source references

- `/root/github/Project_mAIstro/specs/security/S-155-internal-trust-root.md` — full 265-line spec

## Links

- Source spec: S-155
- Related ADRs: ADR-020 (Setup Wizard), ADR-021 (Conductor Seed), ADR-024 (DID/VC), ADR-029 (Networking Substrate)
