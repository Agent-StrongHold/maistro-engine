---
id: S-144
title: "LiteLLM free-tier auto-configuration — OAuth-first onboarding for the LLM hook"
domain: infra
status: draft
priority: P1
effort: ""
created: 2026-04-25
completed: ""
owner: conductor
commits: []
supersedes: ""
---

# S-144: LiteLLM Free-Tier Auto-Configuration

## Acceptance Criteria

- [ ] Setup wizard offers 4 default free-tier providers; OAuth where supported, paste-API fallback elsewhere
- [ ] OAuth flows for Groq and OpenRouter complete in-browser without leaving the Console
- [ ] Cloudflare deep-link opens the CF dashboard scoped to Workers AI token creation; user pastes the resulting token; vault stores it
- [ ] Cerebras paste-API-key flow works without OAuth (until provider supports it); Console flags this as "OAuth pending provider support"
- [ ] All API keys stored in the vault (S-141); never written to disk in cleartext, never appear in litellm.yaml as a plaintext value
- [ ] LiteLLM routing prefers free-tier providers, falls back across them on rate-limit / outage, degrades gracefully when all are exhausted
- [ ] Daily quota widget on Console first run shows real numbers
- [ ] Sovereignty mode: configuration with zero external providers and one local OpenAI-compatible endpoint is fully supported and tested
- [ ] BYO Anthropic / OpenAI / others is supported via paste-API-key; appears in the wizard as an explicit non-default choice
- [ ] Bouncer screens LiteLLM responses; malicious tool-call sequences from any provider are caught
- [ ] Adding a new free-tier provider later is a Medley plugin install, not a conductor source change
- [ ] OAuth token expiry: when an OAuth-issued API key expires or is revoked by a provider, conductor surfaces a `PROVIDER_AUTH_EXPIRED` alert on the dashboard naming the provider and offering a one-click re-authentication link; LiteLLM routing automatically excludes the expired provider and falls back to remaining configured providers immediately — expired credentials are not silently retried until they begin generating 401 errors
- [ ] Privacy disclosure: the setup wizard explicitly surfaces a "free providers may train on your prompts" warning before storing any external API keys; the warning includes a link to each selected provider's privacy policy; sovereignty mode (local-only) is presented as a clear alternative in the same screen

See `blakematthews-dev/project_maistro` specs/infra/S-144-litellm-freetier.md for full spec.
