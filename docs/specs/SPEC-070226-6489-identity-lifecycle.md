---
id: SPEC-070226-6489
title: "Identity lifecycle: DID method, agent authority tokens, recovery, offboarding"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-07-02
substrate:
  - maistro-engine#ADR-021
  - maistro-engine#ADR-024
  - maistro-engine#ADR-084
  - maistro-engine#SPEC-003
implements:
  - maistro-engine#ADR-084
related:
  - maistro-engine#ADR-026
  - maistro-engine#ADR-059
supersedes: []
blocks: []
blocked-by: []
contracts:
  - behavioral
tests: []
layer: Identity
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-070226-6489: Identity lifecycle — DID method, agent authority tokens, recovery, offboarding

## Context

ADR-084 specifies identity lifecycle: onboarding (agent identity creation), authority token issuance
(CapabilityToken per ADR-024), recovery (if key is lost), and offboarding (revoke all tokens).

DID method is did:key (per ADR-021 baseline); agent authority tokens are JWT-like credentials
signed by the agent's DID. This SPEC wires the full lifecycle.

## Goals

- Agent identity creation via did:key on bootstrap.
- CapabilityToken issuance for agent→agent delegation (ADR-024).
- Key recovery if agent loses its private key (recovery ladder: seed phrase → new key → re-issue tokens).
- Offboarding: revoke all tokens, archive identity.

## Non-goals

- Multi-key rotation (Phase 2).
- Cross-tenant identity federation (Stronghold).

## Decision

### Agent identity creation

```python
async def create_agent_identity(agent_id: str) -> AgentIdentity:
    """Bootstrap a new agent with did:key identity."""
    # Generate Ed25519 keypair (random seed)
    seed = os.urandom(32)
    keypair = Ed25519PrivateKey.from_seed(seed)
    
    # Create did:key
    did = f"did:key:{encode_key(keypair.public_key)}"
    
    # Store identity (encrypted key in vault, public DID in registry)
    identity = AgentIdentity(
        agent_id=agent_id,
        did=did,
        created_at=now(),
        recovery_seed_encrypted=vault.encrypt(seed),  # recovery path
    )
    await identity_store.save(identity)
    return identity
```

### CapabilityToken issuance

```python
@dataclass
class CapabilityToken:
    """JWT-like token signed by agent DID; grants authority to delegate to sub-agents."""
    iss: str  # issuer DID (the agent)
    sub: str  # subject (delegated agent or service)
    cap: Literal["delegate", "read", "write"]
    exp: int  # expiry timestamp
    signature: bytes  # Ed25519 signature over {iss}.{sub}.{cap}.{exp}

async def issue_capability_token(
    agent_id: str,
    target_agent_id: str,
    capability: str,
    ttl_seconds: int = 3600
) -> CapabilityToken:
    identity = await identity_store.get(agent_id)
    token = CapabilityToken(
        iss=identity.did,
        sub=target_agent_id,
        cap=capability,
        exp=int(time.time()) + ttl_seconds
    )
    token.signature = sign_token(identity.private_key, token)
    return token
```

### Key recovery (recovery ladder)

```python
# Recovery ladder: seed phrase (user knows) → new keypair → re-issue tokens

async def recover_agent_identity(
    agent_id: str,
    recovery_seed_phrases: list[str]  # BIP39 phrases
) -> AgentIdentity:
    """Recover lost agent key from recovery seed."""
    # Verify seed matches stored seed (checksum)
    stored_seed = await vault.decrypt(
        await identity_store.get(agent_id).recovery_seed_encrypted
    )
    if mnemonic_to_seed(recovery_seed_phrases) != stored_seed:
        raise InvalidRecoverySeedError()
    
    # Re-generate keypair from seed (deterministic)
    keypair = Ed25519PrivateKey.from_seed(stored_seed)
    
    # DID doesn't change (derived from public key)
    # Re-issue all capability tokens (old ones are now invalid)
    old_tokens = await token_store.get_by_issuer(agent_id)
    for token in old_tokens:
        new_token = await issue_capability_token(
            agent_id,
            token.sub,
            token.cap,
            ttl_seconds=86400  # 1 day grace
        )
    
    return identity
```

### Offboarding (revocation)

```python
async def offboard_agent(agent_id: str):
    """Revoke all tokens, archive identity."""
    identity = await identity_store.get(agent_id)
    
    # Revoke all capability tokens
    tokens = await token_store.get_by_issuer(agent_id)
    for token in tokens:
        await token_store.revoke(token)
    
    # Archive identity (soft-delete)
    identity.offboarded_at = now()
    await identity_store.save(identity)
    
    emit("identity.offboarded", agent_id=agent_id)
```

## Acceptance criteria

- [ ] New agent gets a did:key identity with Ed25519 public key.
- [ ] CapabilityToken issued by agent A to agent B can be verified (signature check).
- [ ] Recovery with correct seed phrase regenerates the same DID (deterministic).
- [ ] Recovery with wrong seed phrase raises InvalidRecoverySeedError (property: no guessing).
- [ ] Offboarding revokes all issued tokens; agents can't use old tokens.
- [ ] Token expiry is checked on every use (expired tokens rejected).

## Testing

- Unit: identity creation (DID derivation), token signing/verification.
- Unit: recovery (seed → key regeneration determinism).
- Integration: agent issues token to sub-agent, sub-agent uses token, token accepted/rejected
  correctly.
- Offboarding: mark agent as offboarded, confirm old tokens are invalid.
- Property: "recovery from seed always produces the same DID and tokens" (use Hypothesis to
  generate seeds).

## References

- [ADR-084: Identity Lifecycle](../adr/ADR-084-identity-lifecycle.md)
- [ADR-024: Agent Identity & Verifiable Credentials](../adr/ADR-024-agent-identity-did-vc.md)
