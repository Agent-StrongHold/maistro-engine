---
id: S-141
title: "Secrets vault — age-encrypted file unlocked by admin keypair"
domain: security
status: draft
priority: P1
effort: ""
created: 2026-04-25
updated: 2026-05-13
completed: ""
owner: conductor
commits: []
supersedes: ""
---

# S-141: Secrets Vault

## Acceptance Criteria

- [ ] `secrets.use(name, callback)` is the ONLY public API; `secrets.get` does not exist anywhere in the codebase
- [ ] CI grep for `secrets.get` outside test fixtures fails the build
- [ ] Vault file `secrets.age` is encrypted to the admin's `m/0'` public key from S-149
- [ ] Admin private key is held in OS keychain on desktop, passphrase-encrypted file on headless Linux; never on disk in cleartext
- [ ] At startup, vault is decrypted into mlock'd process memory; private key zeroed after decryption; in-memory state zeroed on process death
- [ ] Vault unavailability at startup: if the admin private key cannot be retrieved from the OS keychain AND the passphrase-encrypted fallback file is absent or fails to decrypt, conductor refuses to start with a `VAULT_UNAVAILABLE` error and clear recovery instructions (`maistro vault recover`); conductor never starts with an empty or partial vault — fail-closed is the only acceptable behavior
- [ ] Bouncer rejects agent output containing any vault-credential prefix (final-line defense); the match pattern is the first 8 bytes (64 bits) of the SHA-256 hash of each credential value; prefix length is fixed and documented in the Bouncer implementation
- [ ] Bouncer pattern set is regenerated within 100ms of any vault mutation (add, rotate, remove, rebuild)
- [ ] Restoring the seed on a new machine reconstitutes the vault encryption key; importing a backup file restores credential values
- [ ] All vault mutations are admin-signed and recorded as VCs in the audit log
- [ ] No credential value is ever in a Langfuse trace, log line, or panic stack
- [ ] `maistro vault export --encrypted` produces an age-encrypted file importable on a fresh install with the same seed
- [ ] Setup wizard asks about vault backup; operator must explicitly acknowledge "no backup" to skip

See `blakematthews-dev/project_maistro` specs/security/S-141-vault.md for full spec.
