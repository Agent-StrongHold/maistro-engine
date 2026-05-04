"""
Cloud LLM pricing comparison, benchmark scores, and cost-efficiency metrics.

All prices are USD per million tokens (MTok) as of May 2026.

## Programmatic price refresh

Two machine-readable sources cover most providers:

  LiteLLM model DB (JSON, updated with each litellm release):
    https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json

  OpenRouter model API (live, returns context + pricing for every listed model):
    https://openrouter.ai/api/v1/models

Provider-specific canonical pricing pages are stored in PRICING_UPDATE_SOURCES below
and on each ModelPricing instance.

## "x tokens ≈ what unit of work?"

Rough real-world task token budgets (input + output):

  One-shot chat reply           ~2K–5K tokens
  Code review (single file)     ~5K–10K tokens
  SWE-bench issue resolution    ~15K–25K tokens   (avg from leaderboard traces)
  Full repo summarisation       ~50K–200K tokens
  Long document Q&A             ~100K–500K tokens

cost_per_typical_task_usd uses 8K input + 2K output as a simple normalised unit.
swe_bench_per_dollar = SWE-bench % ÷ typical_task_cost, so higher is better value.

## Tokenizer note (why Opus 4.7 costs more than the price suggests)

Claude Opus 4.7 ships with a new tokenizer:
  1M tokens ≈ 555K words   (Opus 4.7)
  1M tokens ≈ 750K words   (Sonnet 4.6 and earlier)

The same prose document consumes ~35% more tokens on Opus 4.7, so the effective
per-word cost is higher than the nominal per-token price implies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelPricing:
    provider: str
    model_id: str          # canonical API identifier
    input_mtok: float      # USD per 1M input tokens (cache miss / standard)
    output_mtok: float     # USD per 1M output tokens
    context_window: int    # max input tokens
    max_output: Optional[int] = None  # max output tokens

    # Prompt caching (where offered)
    cache_write_mtok: Optional[float] = None   # cost to populate cache
    cache_read_mtok: Optional[float] = None    # cost to read from cache (huge saving)

    # Tokenizer quirks that affect real-world cost
    tokenizer_note: Optional[str] = None

    # Benchmark scores
    swe_bench_verified: Optional[float] = None   # % of SWE-bench Verified resolved
    swe_bench_note: Optional[str] = None
    mmlu: Optional[float] = None                 # %
    gpqa_diamond: Optional[float] = None         # %

    # Composite intelligence index (Artificial Analysis v4, higher = smarter)
    intelligence_index: Optional[float] = None

    # Capabilities
    supports_thinking: bool = False   # extended / reasoning mode available
    supports_vision: bool = True
    supports_tool_use: bool = True

    knowledge_cutoff: Optional[str] = None   # "YYYY-MM"
    pricing_url: str = ""
    notes: Optional[str] = None

    # ── Derived metrics ───────────────────────────────────────────────────

    @property
    def blended_mtok(self) -> float:
        """Blended cost assuming 3:1 input:output token ratio (typical chat)."""
        return (self.input_mtok * 3 + self.output_mtok) / 4

    @property
    def cost_per_typical_task_usd(self) -> float:
        """
        Cost for a normalised 'typical agentic task': 8K input + 2K output tokens.
        Use this to compare models on a unit-of-work basis.
        """
        return (self.input_mtok * 8_000 + self.output_mtok * 2_000) / 1_000_000

    @property
    def swe_bench_per_dollar(self) -> Optional[float]:
        """
        SWE-bench % points per dollar of typical-task cost.
        Captures 'how much problem-solving power per dollar'.
        Higher is better.
        """
        if self.swe_bench_verified is None or self.cost_per_typical_task_usd == 0:
            return None
        return self.swe_bench_verified / self.cost_per_typical_task_usd


# ---------------------------------------------------------------------------
# Provider registry — used to know where to refresh prices
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "name": "Anthropic",
        "pricing_url": "https://platform.claude.com/docs/en/docs/about-claude/models/overview",
        "api_docs_url": "https://docs.anthropic.com/en/api/getting-started",
    },
    "openai": {
        "name": "OpenAI",
        "pricing_url": "https://openai.com/api/pricing/",
        "api_docs_url": "https://platform.openai.com/docs/models",
    },
    "google": {
        "name": "Google DeepMind",
        "pricing_url": "https://ai.google.dev/gemini-api/docs/pricing",
        "api_docs_url": "https://ai.google.dev/gemini-api/docs",
    },
    "deepseek": {
        "name": "DeepSeek",
        "pricing_url": "https://api-docs.deepseek.com/quick_start/pricing/",
        "api_docs_url": "https://api-docs.deepseek.com/",
    },
    "xai": {
        "name": "xAI",
        "pricing_url": "https://docs.x.ai/docs/models",
        "api_docs_url": "https://docs.x.ai/docs",
    },
    "mistral": {
        "name": "Mistral AI",
        "pricing_url": "https://mistral.ai/pricing",
        "api_docs_url": "https://docs.mistral.ai/",
    },
    "meta": {
        "name": "Meta (open weights; prices via inference provider)",
        "pricing_url": "https://openrouter.ai/meta-llama",
        "api_docs_url": "https://llama.meta.com/",
    },
}


# ---------------------------------------------------------------------------
# Model catalogue
# ---------------------------------------------------------------------------

MODELS: list[ModelPricing] = [

    # ── Anthropic Claude ────────────────────────────────────────────────────
    # Prompt caching: write = input_price × 1.25 ; read = input_price × 0.10
    # Sources: https://platform.claude.com/docs/en/docs/about-claude/models/overview

    ModelPricing(
        provider="anthropic",
        model_id="claude-opus-4-7",
        input_mtok=5.00,
        output_mtok=25.00,
        context_window=1_000_000,
        max_output=128_000,
        cache_write_mtok=6.25,   # 1.25 × $5
        cache_read_mtok=0.50,    # 0.10 × $5
        tokenizer_note=(
            "New tokenizer: 1M tokens ≈ 555K words (vs 750K words on older models). "
            "The same English prose costs ~35% MORE tokens, raising effective per-word cost "
            "relative to the nominal per-token price."
        ),
        swe_bench_verified=79.4,
        swe_bench_note="High-compute scaffold; standard (no scaffold): 72.5%",
        mmlu=87.4,
        gpqa_diamond=74.9,
        intelligence_index=57,   # Artificial Analysis Intelligence Index v4
        supports_thinking=False,  # Adaptive thinking (auto-engage), not user-toggled
        knowledge_cutoff="2026-01",
        pricing_url="https://platform.claude.com/docs/en/docs/about-claude/models/overview",
        notes=(
            "Most capable Claude. Step-change improvement in agentic coding over Opus 4.6. "
            "Adaptive thinking engages automatically on hard problems. "
            "New tokenizer means higher effective cost for long prose vs nominal price."
        ),
    ),

    ModelPricing(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        input_mtok=3.00,
        output_mtok=15.00,
        context_window=1_000_000,
        max_output=64_000,
        cache_write_mtok=3.75,   # 1.25 × $3
        cache_read_mtok=0.30,    # 0.10 × $3
        tokenizer_note="Old tokenizer: 1M tokens ≈ 750K words.",
        swe_bench_verified=80.2,
        swe_bench_note="High-compute; standard (Claude Sonnet 4 baseline): 72.7%",
        intelligence_index=None,
        supports_thinking=True,
        knowledge_cutoff="2025-08",
        pricing_url="https://platform.claude.com/docs/en/docs/about-claude/models/overview",
        notes=(
            "Best speed/intelligence balance in the Claude lineup. "
            "Supports extended thinking (up to 64K thinking tokens). "
            "1M context at a lower price than Opus 4.7."
        ),
    ),

    ModelPricing(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
        input_mtok=1.00,
        output_mtok=5.00,
        context_window=200_000,
        max_output=64_000,
        cache_write_mtok=1.25,
        cache_read_mtok=0.10,
        supports_thinking=True,
        knowledge_cutoff="2025-02",
        pricing_url="https://platform.claude.com/docs/en/docs/about-claude/models/overview",
        notes=(
            "Fastest Claude. Near-frontier intelligence at lowest per-token cost. "
            "Ideal for high-volume routing, classification, and simple agentic steps."
        ),
    ),

    ModelPricing(
        provider="anthropic",
        model_id="claude-opus-4-6",
        input_mtok=5.00,
        output_mtok=25.00,
        context_window=1_000_000,
        max_output=128_000,
        cache_write_mtok=6.25,
        cache_read_mtok=0.50,
        supports_thinking=True,
        knowledge_cutoff="2025-05",
        pricing_url="https://platform.claude.com/docs/en/docs/about-claude/models/overview",
        notes=(
            "Legacy flagship. Same price as Opus 4.7 but older tokenizer/architecture. "
            "Still solid for extended thinking workloads."
        ),
    ),

    # ── OpenAI ──────────────────────────────────────────────────────────────
    # Sources: https://openrouter.ai/openai/* (OpenAI's own pricing page returns 403)

    ModelPricing(
        provider="openai",
        model_id="gpt-4.1",
        input_mtok=2.00,
        output_mtok=8.00,
        context_window=1_047_576,
        knowledge_cutoff="2024-06",
        pricing_url="https://openrouter.ai/openai/gpt-4.1",
        notes=(
            "OpenAI's long-context flagship. ~1M token context matches Claude/Gemini. "
            "Strong at advanced coding and long-context reasoning."
        ),
    ),

    ModelPricing(
        provider="openai",
        model_id="gpt-4o",
        input_mtok=2.50,
        output_mtok=10.00,
        context_window=128_000,
        knowledge_cutoff="2023-10",
        pricing_url="https://openrouter.ai/openai/gpt-4o",
        notes=(
            "Multimodal (text + vision + audio). Solid general-purpose performance. "
            "Smaller context window than flagship competitors."
        ),
    ),

    # ── Google Gemini ────────────────────────────────────────────────────────
    # Sources: https://ai.google.dev/gemini-api/docs/pricing

    ModelPricing(
        provider="google",
        model_id="gemini-3.1-pro-preview",
        input_mtok=2.00,     # ≤200K prompt
        output_mtok=12.00,   # ≤200K prompt
        context_window=1_000_000,
        intelligence_index=57,
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        notes=(
            "Tiered pricing: prompts >200K cost $4 input / $18 output per MTok. "
            "Preview model; production availability not guaranteed."
        ),
    ),

    ModelPricing(
        provider="google",
        model_id="gemini-2.5-pro",
        input_mtok=1.25,     # ≤200K
        output_mtok=10.00,   # ≤200K
        context_window=1_000_000,
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        notes=(
            "Tiered: >200K costs $2.50 input / $15 output. "
            "Competitive coding performance; available via Vertex AI and AI Studio."
        ),
    ),

    ModelPricing(
        provider="google",
        model_id="gemini-2.5-flash",
        input_mtok=0.30,
        output_mtok=2.50,
        context_window=1_000_000,
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        notes=(
            "Best Gemini value tier. Free usage available (AI Studio). "
            "Supports thinking mode and 1M context."
        ),
    ),

    ModelPricing(
        provider="google",
        model_id="gemini-2.5-flash-lite",
        input_mtok=0.10,
        output_mtok=0.40,
        context_window=1_000_000,
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        notes=(
            "Cheapest production Gemini. Free tier available. "
            "Good for structured extraction and classification at massive scale."
        ),
    ),

    ModelPricing(
        provider="google",
        model_id="gemini-3.1-flash-lite-preview",
        input_mtok=0.25,
        output_mtok=1.50,
        context_window=1_000_000,
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        notes="Preview. Batch API available at 50% discount.",
    ),

    # ── DeepSeek ─────────────────────────────────────────────────────────────
    # Sources: https://api-docs.deepseek.com/quick_start/pricing/
    # Cache hit price was cut to 1/10 of launch price on 2026-04-26.

    ModelPricing(
        provider="deepseek",
        model_id="deepseek-v4-flash",
        input_mtok=0.14,          # cache miss (standard)
        output_mtok=0.28,
        context_window=1_000_000,
        max_output=384_000,
        cache_read_mtok=0.0028,   # cache hit = input/50 — extreme KV cache savings
        supports_thinking=True,   # thinking mode toggle available (non-thinking by default)
        pricing_url="https://api-docs.deepseek.com/quick_start/pricing/",
        notes=(
            "Extraordinary value. Cache hits at $0.0028/MTok (50× cheaper than miss). "
            "Largest max_output (384K) of any model listed. "
            "Non-thinking mode default; thinking mode optionally enabled."
        ),
    ),

    ModelPricing(
        provider="deepseek",
        model_id="deepseek-v4-pro",
        input_mtok=0.435,         # 75% launch discount active until 2026-05-31
        output_mtok=0.87,         # post-discount standard: ~$1.74 / $3.48
        context_window=1_000_000,
        max_output=384_000,
        cache_read_mtok=0.003625, # discounted; standard: ~$0.0145
        supports_thinking=True,   # reasoning/thinking mode on by default
        pricing_url="https://api-docs.deepseek.com/quick_start/pricing/",
        notes=(
            "75% launch discount runs through 2026-05-31. "
            "Post-discount standard prices: ~$1.74 input / $3.48 output / $0.0145 cache read. "
            "Reasoning (thinking) mode is default. Replaces deepseek-reasoner."
        ),
    ),

    # ── xAI Grok ─────────────────────────────────────────────────────────────
    # Sources: https://openrouter.ai/x-ai/grok-4

    ModelPricing(
        provider="xai",
        model_id="grok-4",
        input_mtok=3.00,
        output_mtok=15.00,
        context_window=256_000,
        knowledge_cutoff="2025-07",
        pricing_url="https://docs.x.ai/docs/models",
        notes=(
            "Reasoning always active; cannot be disabled or adjusted. "
            "Pricing escalates when a single request exceeds 128K total tokens. "
            "Batch API offers 20–50% discount. Supports vision and parallel tool calling."
        ),
    ),

    # ── Mistral AI ────────────────────────────────────────────────────────────
    # Sources: https://openrouter.ai/mistralai/devstral-medium-2507

    ModelPricing(
        provider="mistral",
        model_id="devstral-medium",
        input_mtok=0.40,
        output_mtok=2.00,
        context_window=131_072,
        swe_bench_verified=61.6,
        swe_bench_note=(
            "SWE-Bench Verified; release notes claim it exceeds Gemini 2.5 Pro and GPT-4.1"
        ),
        knowledge_cutoff="2025-06",
        pricing_url="https://openrouter.ai/mistralai/devstral-medium-2507",
        notes=(
            "Coding-specialist model (joint Mistral + All Hands AI). "
            "Best known SWE-bench score at this price point."
        ),
    ),

    # ── Meta Llama (open weights; prices via inference provider) ─────────────
    # Prices reflect OpenRouter / Groq market rates; may vary by provider.

    ModelPricing(
        provider="meta",
        model_id="llama-4-maverick",
        input_mtok=0.15,
        output_mtok=0.60,
        context_window=1_048_576,
        pricing_url="https://openrouter.ai/meta-llama/llama-4-maverick",
        notes=(
            "Open weights. ~1M context. "
            "Prices are inference-provider market rates and vary (Groq, Together, Fireworks, etc.)."
        ),
    ),

    ModelPricing(
        provider="meta",
        model_id="llama-3.3-70b",
        input_mtok=0.59,
        output_mtok=0.79,
        context_window=131_072,
        pricing_url="https://console.groq.com/docs/models",
        notes=(
            "Via Groq at ~280 tokens/sec. Strong open-weight general-purpose baseline. "
            "Available across Groq, Together, Fireworks at varying prices."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Programmatic price-refresh sources
# ---------------------------------------------------------------------------

PRICING_UPDATE_SOURCES: dict[str, str] = {
    # LiteLLM keeps a JSON file of every model's price + context window.
    # It's updated with each litellm release and is the easiest single source.
    "litellm_model_db": (
        "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
    ),
    # OpenRouter's public API returns live pricing for every model it routes.
    # GET https://openrouter.ai/api/v1/models  →  list[{id, pricing: {prompt, completion}, context_length}]
    "openrouter_api": "https://openrouter.ai/api/v1/models",
    # Provider-specific canonical pages (for verification / scraping)
    "anthropic": "https://platform.claude.com/docs/en/docs/about-claude/models/overview",
    "openai": "https://openai.com/api/pricing/",
    "google": "https://ai.google.dev/gemini-api/docs/pricing",
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing/",
    "xai": "https://docs.x.ai/docs/models",
    "mistral": "https://mistral.ai/pricing",
    "meta_via_openrouter": "https://openrouter.ai/api/v1/models",
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def get_model(model_id: str) -> Optional[ModelPricing]:
    return next((m for m in MODELS if m.model_id == model_id), None)


def cost_for_tokens(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    use_cache_read: bool = False,
) -> Optional[float]:
    """Return total USD cost for a specific token usage on a given model."""
    m = get_model(model_id)
    if m is None:
        return None
    if use_cache_read and m.cache_read_mtok is not None:
        input_cost = m.cache_read_mtok * input_tokens / 1_000_000
    else:
        input_cost = m.input_mtok * input_tokens / 1_000_000
    return input_cost + m.output_mtok * output_tokens / 1_000_000


def comparison_table() -> str:
    """
    Markdown table of all models sorted by input price (cheapest first).

    Columns:
      Provider | Model | In $/MTok | Out $/MTok | Context | Max Out |
      SWE-bench % | Task cost* | Value†
    """
    rows = []
    for m in sorted(MODELS, key=lambda x: x.input_mtok):
        ctx = "1M" if m.context_window >= 1_000_000 else f"{m.context_window // 1_000}K"
        max_out = (
            f"{m.max_output // 1_000}K" if m.max_output else "—"
        )
        swe = f"{m.swe_bench_verified:.1f}%" if m.swe_bench_verified is not None else "—"
        task = f"${m.cost_per_typical_task_usd:.4f}"
        val = (
            f"{m.swe_bench_per_dollar:.0f}"
            if m.swe_bench_per_dollar is not None
            else "—"
        )
        rows.append(
            f"| {m.provider:<12} | {m.model_id:<30} | ${m.input_mtok:>7.4f} "
            f"| ${m.output_mtok:>8.4f} | {ctx:>7} | {max_out:>7} "
            f"| {swe:>11} | {task:>10} | {val:>7} |"
        )

    header = (
        "| Provider     | Model                          |  In $/MTok | Out $/MTok "
        "| Context | Max Out | SWE-bench % |  Task cost* |  Value† |\n"
        "|--------------|--------------------------------|------------|------------"
        "|---------|---------|-------------|-------------|--------|\n"
    )
    footer = (
        "\n*Typical task cost = 8K input + 2K output tokens\n"
        "†Value = SWE-bench % ÷ typical task cost (higher = more problem-solving power per $)\n"
        "SWE-bench scores from https://swebench.com (Verified subset unless noted)\n"
        "Intelligence Index from https://artificialanalysis.ai\n"
    )
    return header + "\n".join(rows) + "\n" + footer
