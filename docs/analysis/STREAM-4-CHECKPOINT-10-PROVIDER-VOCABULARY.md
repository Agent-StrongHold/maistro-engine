# Stream 4 Checkpoint 10: Provider Vocabulary and Activation Semantics

Date: 2026-08-14
Source audited: `develop`

This checkpoint resolves an important naming collision for Stream 6: current MAIstro uses “provider” for at least two live concepts with different ownership, credential, and activation semantics.

## 1. Hive `/v1/providers` means deployment-wide LLM vendor/model activation

Mounted `routes/providers.py` manages a fixed catalog of external LLM vendors such as:

- Gemini
- Anthropic
- OpenAI
- Groq
- Mistral
- xAI
- OpenRouter

The route owns:

- deployment-wide provider API keys
- age-vault storage
- LiteLLM dynamic model registration
- LiteLLM master-key use
- one-token activation test completion
- provider activation markers
- install/setup UX status

The file explicitly distinguishes these keys from per-user integration credentials.

Classification: `live deployment/model-provider control surface`.

## 2. `CapabilityProvider` means a swappable implementation of a capability slot

Core `maistro.capabilities.protocols.CapabilityProvider` requires:

- provider name
- slot
- trust tier
- requirements
- healthcheck

Concrete providers also implement slot-specific behavior, such as HarnessRunner or infrastructure monitor/action.

This is a different abstraction from an LLM vendor activated through LiteLLM.

Classification: `live capability implementation abstraction`.

## 3. Do not flatten both meanings into one undifferentiated Provider model

The two concepts differ materially.

### Deployment/model provider

- represents external model vendor/endpoints/models
- often activated globally for the deployment
- credentials may be deployment/operator secrets
- LiteLLM performs downstream model routing/registration
- health/availability is partly gateway/vendor state

### Capability provider

- fills a named capability slot
- can be in-process, HTTP-backed, harness-backed, or another implementation style
- has trust tier and slot fallback semantics
- may use deployment credentials, Project credentials, user credentials, or no credential
- selected through CapabilityRegistry today

A canonical Provider concept may encompass both only if it preserves this distinction explicitly through provider kind/type/adapters and scope semantics.

## 4. Credential ownership differs by provider category

Current live code already proves at least three credential ownership modes:

1. **deployment LLM vendor keys** in age vault (`routes/providers.py`)
2. **deployment/operator service secrets** such as host-health token (`capabilities_wiring.py`)
3. **user integration credentials** in core `UserCredentialStore`

Canonical Binding/Invocation must be able to reference the correct credential/resource without collapsing these ownership models.

## 5. Activation semantics also differ

### LLM provider activation

`POST /v1/providers/{name}/activate`:

- requires stored vendor key
- dynamically registers models with LiteLLM
- performs a billed/test model call
- records provider activated

### Capability provider activation

CapabilityRegistry:

- providers register inactive
- operator selects active provider for a slot
- enable/disable acts as a kill switch
- resolve health-checks and applies slot fallback policy

These are related operational ideas but not the same state transition.

## 6. Stream 6 migration constraint

Canonical vocabulary should make clear whether “Provider” refers to:

- external service/vendor/model endpoint
- implementation of a Capability
- transport/harness implementation

A practical convergence model can still use one Provider supertype, but consumers must not lose:

- provider kind
- scope
- credential ownership
- activation semantics
- health/fallback behavior
- model/endpoints where applicable

## 7. Existing provider registry behavior should remain a consumer/source, not be blindly replaced

CapabilityRegistry already provides useful slot/provider selection, health, and fallback behavior.

LiteLLM already provides useful model-provider routing/registration behavior.

Canonical Binding/Invocation should orchestrate these existing mechanics rather than recreating both inside a monolithic provider selector.

## 8. Documentation drift around harness policy remains relevant

The `HarnessRunner` protocol docstring says orchestration should route through a safety wrapper so inbound messages are Warden-scanned and reported actions are policy-checked.

Checkpoint 9 traced the mounted Hive HarnessSessionManager path and found that Warden is supplied but SequencePolicyEngine is not, so the optional PolicyActionGate is not active there.

This is another example of why canonical naming/contract language must distinguish supported capability from actually wired production enforcement.

## Handoff

### Stream 6

Preserve both provider families and normalize them deliberately. Do not infer that identical noun usage means identical ownership or lifecycle.

### Stream 3

Deployment-wide provider activation under `config.write` is not Project resource authorization. Project-scoped Bindings should constrain which configured providers/resources a principal may invoke without redefining global provider installation.

### Stream 7

Provider setup/activation routes are live install/operator UX and should remain product/control-plane projections over canonical provider/binding infrastructure.
