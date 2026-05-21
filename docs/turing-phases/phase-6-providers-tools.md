# Phase 6: Providers & Tools

**Goal:** LLM providers (Provider protocol, FakeProvider, LiteLLM) and tool registry
with 9 tools. The `code_modification.py` (StrongholdClient) is dropped.

**Depends on:** Phase 1 (Reactor). Providers are consumed by cognition (Phase 4) and
runtime (Phase 7) but are defined here as independent infrastructure.

---

## 1. Source Inventory

| Source file | Lines | Description |
|------------|-------|-------------|
| `turing/runtime/providers/base.py` | 80 | Provider protocol, FreeTierWindow, error types |
| `turing/runtime/providers/fake.py` | 104 | Deterministic FakeProvider for testing |
| `turing/runtime/providers/litellm.py` | 269 | LiteLLM production provider with quota |
| `turing/runtime/providers/messaging.py` | 178 | SignalWire SMS provider |
| `turing/runtime/tools/base.py` | 67 | Tool protocol + registry |
| `turing/runtime/tools/code_reader.py` | 89 | Sandboxed file reading |
| `turing/runtime/tools/obsidian.py` | 98 | Obsidian vault writer |
| `turing/runtime/tools/rss.py` | 227 | RSS reader |
| `turing/rss_seen_repo.py` | 86 | RSS dedup tracker |
| `turing/runtime/tools/search.py` | 67 | Web search |
| `turing/runtime/tools/wiki.py` | 115 | Wiki writer |
| `turing/runtime/tools/wordpress.py` | 70 | WordPress REST API |
| `turing/runtime/tools/newsletter.py` | 118 | Newsletter composition |
| **Total** | **~1,568** | |

**Dropped:**
- `turing/runtime/tools/code_modification.py` (88 lines) — StrongholdClient, replaced by maistro-core

| Source test file | Lines | Key ACs covered |
|-----------------|-------|----------------|
| `tests/test_fake_provider.py` | 178 | AC-34.* |
| `tests/test_litellm_provider.py` | 274 | AC-35.* |
| `tests/test_messaging.py` | 217 | AC-38.* |
| `tests/test_tool_registry.py` | 51 | AC-36.* |
| `tests/test_http_tools.py` | 262 | AC-37.* (search, wiki, wordpress) |
| `tests/test_rss_reader.py` | 98 | AC-37.* (RSS) |
| `tests/test_rss_seen_repo.py` | 95 | RSS dedup |
| `tests/test_obsidian_writer.py` | 61 | AC-37.* (obsidian) |
| `tests/test_newsletter.py` | 120 | AC-37.* (newsletter) |
| **Total** | **~1,356** | |

## 2. Target File Mapping

| Source | Target |
|--------|--------|
| `runtime/providers/base.py` | `maistro_turing/providers/base.py` |
| `runtime/providers/fake.py` | `maistro_turing/providers/fake.py` |
| `runtime/providers/litellm.py` | `maistro_turing/providers/litellm.py` |
| `runtime/providers/messaging.py` | `maistro_turing/providers/messaging.py` |
| `runtime/tools/base.py` | `maistro_turing/tools/base.py` |
| `runtime/tools/code_reader.py` | `maistro_turing/tools/code_reader.py` |
| `runtime/tools/obsidian.py` | `maistro_turing/tools/obsidian.py` |
| `runtime/tools/rss.py` | `maistro_turing/tools/rss.py` |
| `rss_seen_repo.py` | `maistro_turing/tools/rss_seen_repo.py` |
| `runtime/tools/search.py` | `maistro_turing/tools/search.py` |
| `runtime/tools/wiki.py` | `maistro_turing/tools/wiki.py` |
| `runtime/tools/wordpress.py` | `maistro_turing/tools/wordpress.py` |
| `runtime/tools/newsletter.py` | `maistro_turing/tools/newsletter.py` |

## 3. Acceptance Criteria

### AC-34: Provider protocol + FakeProvider (boundary + behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-34.1 | boundary | `Provider` protocol is `@runtime_checkable` | `isinstance(FakeProvider(), Provider)` is True | Runtime checkable |
| AC-34.2 | behavioral | `FakeProvider.complete(prompt)` | Returns deterministic string based on prompt | Deterministic output |
| AC-34.3 | behavioral | `FakeProvider.complete(prompt, max_tokens=10)` | Response respects max_tokens hint | Token limit |
| AC-34.4 | behavioral | `FakeProvider.quota_window()` | Returns `FreeTierWindow` or `None` | Quota window |
| AC-34.5 | boundary | `ProviderError` hierarchy | `RateLimited` and `ProviderUnavailable` are subclasses | Error types |
| AC-34.6 | boundary | `FreeTierWindow.headroom` | `max(0, tokens_allowed - tokens_used)` | Headroom never negative |
| AC-34.7 | boundary | `EmbeddingProvider` protocol | `embed()` returns `list[float]` | Embedding protocol |
| AC-34.8 | boundary | `ImageGenProvider` protocol | `generate_image()` returns base64 string | Image protocol |

### AC-35: LiteLLM provider (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-35.1 | behavioral | `LiteLLMProvider.complete(prompt)` with valid API key | Returns completion string | Completion works |
| AC-35.2 | behavioral | `LiteLLMProvider.complete()` when rate-limited | Raises `RateLimited` | Rate limit handling |
| AC-35.3 | behavioral | `LiteLLMProvider.complete()` when 5xx | Raises `ProviderUnavailable` | Server error handling |
| AC-35.4 | behavioral | `LiteLLMProvider.quota_window()` | Returns current window or `None` | Quota tracking |
| AC-35.5 | behavioral | `LiteLLMProvider.complete()` on retry | Retries up to configured max | Retry logic |

### AC-36: Tool registry + base protocol (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-36.1 | boundary | `Tool` protocol with `name: str` and `run(**kwargs) -> str` | Runtime checkable | Tool protocol |
| AC-36.2 | behavioral | `ToolRegistry.register(tool)` | `ToolRegistry.get(tool.name)` returns tool | Register/get round-trip |
| AC-36.3 | behavioral | `ToolRegistry.get("nonexistent")` | Returns `None` | Missing tool returns None |
| AC-36.4 | behavioral | `ToolRegistry.list_tools()` | Returns all registered tool names | List is complete |

### AC-37: Individual tools (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-37.1 | behavioral | `CodeReader.run(path=valid_file)` | Returns file contents | File reading works |
| AC-37.2 | boundary | `CodeReader.run(path=nonexistent)` | Returns error string, no crash | Missing file is safe |
| AC-37.3 | behavioral | `ObsidianWriter.run(title, content, vault_path)` | File created in vault | Obsidian write works |
| AC-37.4 | behavioral | `RSSReader.run(feed_url=valid_rss)` | Returns parsed entries | RSS parsing works |
| AC-37.5 | behavioral | `RSSSeenRepo.is_seen(self_id, url, item_id)` | Returns bool | Dedup check |
| AC-37.6 | behavioral | `RSSSeenRepo.mark_seen(self_id, url, item_id)` | `is_seen` returns True after marking | Dedup marking |
| AC-37.7 | behavioral | `WebSearch.run(query="test")` | Returns search results | Search works |
| AC-37.8 | behavioral | `WikiWriter.run(title, content)` | Wiki page created | Wiki write works |
| AC-37.9 | behavioral | `WordPress.run(title, content)` | Post created via REST API | WordPress works |
| AC-37.10 | behavioral | `Newsletter.run(title, sections)` | Newsletter composed | Newsletter works |

### AC-38: Messaging — SignalWire (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-38.1 | behavioral | `SignalWire.send(to, body)` with valid credentials | Message sent, returns message ID | Send works |
| AC-38.2 | behavioral | `SignalWire.send()` with invalid credentials | Raises `ProviderError` | Auth failure |
| AC-38.3 | boundary | `SignalWire` requires `SIGNALWIRE_SID` + `SIGNALWIRE_TOKEN` env vars | `ValueError` if missing | Env var required |

## 4. Unit Test Plan

| Test file | ACs covered | Marks |
|-----------|-------------|-------|
| `tests/test_fake_provider.py` | AC-34.1..34.8 | `contract("boundary")` `scope("unit")` |
| `tests/test_litellm_provider.py` | AC-35.1..35.5 | `contract("behavioral")` `scope("unit")` |
| `tests/test_messaging.py` | AC-38.1..38.3 | `contract("behavioral")` `scope("unit")` |
| `tests/test_tool_registry.py` | AC-36.1..36.4 | `contract("behavioral")` `scope("unit")` |
| `tests/test_http_tools.py` | AC-37.7..37.10 | `contract("behavioral")` `scope("unit")` |
| `tests/test_rss_reader.py` | AC-37.4 | `contract("behavioral")` `scope("unit")` |
| `tests/test_rss_seen_repo.py` | AC-37.5..37.6 | `contract("behavioral")` `scope("unit")` |
| `tests/test_obsidian_writer.py` | AC-37.3 | `contract("behavioral")` `scope("unit")` |
| `tests/test_newsletter.py` | AC-37.10 | `contract("behavioral")` `scope("unit")` |

## 5. Property Tests (Hypothesis)

### P-34.1: FreeTierWindow headroom is never negative

```python
from maistro_turing.providers.base import FreeTierWindow

@given(
    allowed=st.integers(min_value=0, max_value=1_000_000),
    used=st.integers(min_value=0, max_value=2_000_000),
)
@settings(max_examples=200)
def test_headroom_never_negative(allowed, used):
    from datetime import datetime, timedelta
    w = FreeTierWindow(
        provider="test", window_kind="daily",
        window_started_at=datetime.now(), window_duration=timedelta(days=1),
        tokens_allowed=allowed, tokens_used=used,
    )
    assert w.headroom >= 0
```

### P-34.2: FakeProvider is deterministic

```python
from maistro_turing.providers.fake import FakeProvider

@given(prompt=st.text(min_size=0, max_size=500))
@settings(max_examples=100)
def test_fake_provider_deterministic(prompt):
    p = FakeProvider()
    result1 = p.complete(prompt)
    result2 = p.complete(prompt)
    assert result1 == result2
```

## 6. Integration Test Plan

| Test | What it wires | AC | Marks |
|-------|--------------|-----|-------|
| `test_provider_bridge_with_fake` | TuringProviderBridge → FakeProvider.complete() | AC-34 + bridge | `contract("cross-service")` `scope("integration")` |
| `test_tool_dispatch_via_actor` | ToolRegistry → CodeReader → result returned | AC-36 + AC-37 | `contract("cross-service")` `scope("integration")` |
| `test_rss_reader_with_dedup` | RSSReader → RSSSeenRepo → only new items processed | AC-37.4 + 37.6 | `contract("cross-service")` `scope("integration")` |

## 7. Bridge Adapter Specs

No new bridges. The existing `TuringProviderBridge` already wraps the `Provider` protocol.
Phase 6 adds concrete implementations that the bridge can use:

- `FakeProvider` → used by bridge in dev/test mode
- `LiteLLMProvider` → used by bridge in production
- `TuringEmbeddingBridge` → wraps `EmbeddingProvider` (new, needed for Phase 7 embedding index)

```python
class TuringEmbeddingBridge:
    """Wraps EmbeddingProvider for semantic retrieval."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    def embed(self, text: str) -> list[float]:
        return self._provider.embed(text)

    def search(self, query: str, vectors: list[tuple[str, list[float]]],
               top_k: int = 5) -> list[tuple[str, float]]:
        """Cosine similarity search against stored vectors."""
        ...
```

## 8. Phase Gate

- [ ] All AC-34..38 tests pass
- [ ] `ruff check packages/maistro-turing/` clean
- [ ] `mypy packages/maistro-turing/ --strict` clean
- [ ] Test count >= 50
- [ ] No `stronghold` imports
- [ ] `code_modification.py` is NOT ported (confirmed dropped)
- [ ] `python -c "from maistro_turing.providers.fake import FakeProvider; print('OK')"` succeeds
- [ ] `python -c "from maistro_turing.tools.base import ToolRegistry; print('OK')"` succeeds
