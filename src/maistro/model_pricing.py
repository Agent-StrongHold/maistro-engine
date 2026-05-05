"""
Cloud LLM pricing comparison, benchmark scores, and cost-efficiency metrics.

All prices are USD per million tokens (MTok) as of May 2026.
Prices verified against provider pages; check PRICING_UPDATE_SOURCES for live data.

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

  One-shot chat reply           ~2K-5K tokens
  Code review (single file)     ~5K-10K tokens
  SWE-bench issue resolution    ~15K-25K tokens   (avg from leaderboard traces)
  Full repo summarisation       ~50K-200K tokens
  Long document Q&A             ~100K-500K tokens

cost_per_typical_task_usd uses 8K input + 2K output as a simple normalised unit.
swe_bench_per_dollar = SWE-bench % / typical_task_cost, so higher is better value.

## Tokenizer note (why Opus 4.7 costs more than the price suggests)

Claude Opus 4.7 ships with a new tokenizer:
  1M tokens ~ 555K words   (Opus 4.7)
  1M tokens ~ 750K words   (Sonnet 4.6 and earlier)

The same prose document consumes ~35% more tokens on Opus 4.7, so the effective
per-word cost is higher than the nominal per-token price implies.

## Inference providers vs model creators

Providers marked with is_inference_platform=True in PROVIDERS are inference platforms
that run other companies' open-weight models (e.g. Groq, Fireworks, Cloudflare).
Their pricing reflects hosting costs, not model licensing. The same model often costs
different amounts across platforms.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass


@dataclass
class ModelPricing:
    provider: str
    model_id: str  # canonical API identifier used in requests
    input_mtok: float  # USD per 1M input tokens (cache miss / standard)
    output_mtok: float  # USD per 1M output tokens
    context_window: int  # max input tokens

    max_output: int | None = None  # max output tokens (None = unspecified/default)

    # Prompt caching (where offered)
    cache_write_mtok: float | None = None  # cost to populate cache
    cache_read_mtok: float | None = None  # cost to read from cache

    # Inference speed (tokens/sec); mainly relevant for inference platforms
    inference_speed_tps: float | None = None

    # Free tier — None means no free tier; string describes what is available
    free_tier: str | None = None

    # Tokenizer quirks that affect real-world cost vs nominal price
    tokenizer_note: str | None = None

    # Benchmark scores
    swe_bench_verified: float | None = None  # % of SWE-bench Verified resolved
    swe_bench_note: str | None = None
    mmlu: float | None = None  # % — broad knowledge (57 subjects)
    gpqa_diamond: float | None = None  # % — PhD-level science Q&A
    humanity_last_exam: float | None = None  # % — HLE: hardest multi-discipline exam
    terminal_bench: float | None = None  # % — terminal/shell task completion (agentic)
    humaneval: float | None = None  # % pass@1 — classic code generation
    live_code_bench: float | None = None  # % — coding on post-cutoff problems (harder)
    arena_elo: int | None = None  # Chatbot Arena Elo (human preference; lmarena.ai)

    # Berkeley Function Calling Leaderboard — % overall accuracy on tool-call tasks
    # Critical for agentic systems; source: gorilla.cs.berkeley.edu/leaderboard.html
    bfcl: float | None = None

    # AIME 2024 — % correct on American Invitational Math Examination (0-100 scale)
    # Primary benchmark for separating reasoning/thinking models on hard math
    aime_2024: float | None = None

    # Composite intelligence index (Artificial Analysis v4, higher = smarter)
    intelligence_index: float | None = None

    # Capabilities
    supports_thinking: bool = False  # extended / reasoning mode available
    supports_vision: bool = True
    supports_tool_use: bool = True

    knowledge_cutoff: str | None = None  # "YYYY-MM"
    pricing_url: str = ""
    notes: str | None = None

    # Rate limits — None = unknown/dynamic; verify at provider console
    # These are the LOWEST published limits for that tier; actual limits vary by model.
    free_tier_rpm: int | None = None  # free tier: requests per minute
    free_tier_tpm: int | None = None  # free tier: tokens per minute
    free_tier_tpd: int | None = None  # free tier: tokens per day (used where TPM not stated)
    paid_tier_rpm: int | None = None  # paid/dev tier: requests per minute
    paid_tier_tpm: int | None = None  # paid/dev tier: tokens per minute

    # ── Derived metrics ───────────────────────────────────────────────────

    @property
    def blended_mtok(self) -> float:
        """Blended cost assuming 3:1 input:output token ratio (typical chat)."""
        return (self.input_mtok * 3 + self.output_mtok) / 4

    @property
    def cost_per_typical_task_usd(self) -> float:
        """
        Cost for a normalised agentic task: 8K input + 2K output tokens.
        Use this to compare models on a unit-of-work basis.
        """
        return (self.input_mtok * 8_000 + self.output_mtok * 2_000) / 1_000_000

    @property
    def swe_bench_per_dollar(self) -> float | None:
        """
        SWE-bench % points per dollar of typical-task cost.
        Higher = more coding problem-solving power per dollar.
        """
        if self.swe_bench_verified is None or self.cost_per_typical_task_usd == 0:
            return None
        return self.swe_bench_verified / self.cost_per_typical_task_usd


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, dict] = {
    # ── Frontier model labs ──
    "anthropic": {
        "name": "Anthropic",
        "pricing_url": "https://platform.claude.com/docs/en/docs/about-claude/models/overview",
        "api_docs_url": "https://docs.anthropic.com/en/api/getting-started",
        "is_inference_platform": False,
    },
    "openai": {
        "name": "OpenAI",
        "pricing_url": "https://openai.com/api/pricing/",
        "api_docs_url": "https://platform.openai.com/docs/models",
        "is_inference_platform": False,
    },
    "google": {
        "name": "Google DeepMind (Gemini)",
        "pricing_url": "https://ai.google.dev/gemini-api/docs/pricing",
        "api_docs_url": "https://ai.google.dev/gemini-api/docs",
        "is_inference_platform": False,
    },
    "deepseek": {
        "name": "DeepSeek",
        "pricing_url": "https://api-docs.deepseek.com/quick_start/pricing/",
        "api_docs_url": "https://api-docs.deepseek.com/",
        "is_inference_platform": False,
    },
    "xai": {
        "name": "xAI",
        "pricing_url": "https://docs.x.ai/docs/models",
        "api_docs_url": "https://docs.x.ai/docs",
        "is_inference_platform": False,
    },
    "mistral": {
        "name": "Mistral AI",
        "pricing_url": "https://mistral.ai/pricing",
        "api_docs_url": "https://docs.mistral.ai/",
        "is_inference_platform": False,
    },
    "cohere": {
        "name": "Cohere",
        "pricing_url": "https://cohere.com/pricing",
        "api_docs_url": "https://docs.cohere.com/",
        "is_inference_platform": False,
    },
    "perplexity": {
        "name": "Perplexity AI",
        "pricing_url": "https://docs.perplexity.ai/guides/pricing",
        "api_docs_url": "https://docs.perplexity.ai/",
        "is_inference_platform": False,
    },
    "amazon": {
        "name": "Amazon (AWS Bedrock / Nova)",
        "pricing_url": "https://aws.amazon.com/bedrock/pricing/",
        "api_docs_url": "https://docs.aws.amazon.com/bedrock/",
        "is_inference_platform": False,
    },
    "microsoft": {
        "name": "Microsoft (Azure AI / Phi)",
        "pricing_url": "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        "api_docs_url": "https://learn.microsoft.com/en-us/azure/ai-studio/",
        "is_inference_platform": False,
    },
    "moonshot": {
        "name": "Moonshot AI (Kimi)",
        "pricing_url": "https://openrouter.ai/moonshotai",
        "api_docs_url": "https://platform.moonshot.ai/docs",
        "is_inference_platform": False,
    },
    "minimax": {
        "name": "MiniMax",
        "pricing_url": "https://openrouter.ai/minimax",
        "api_docs_url": "https://www.minimax.io/docs",
        "is_inference_platform": False,
    },
    "writer": {
        "name": "Writer (Palmyra)",
        "pricing_url": "https://openrouter.ai/writer",
        "api_docs_url": "https://dev.writer.com/",
        "is_inference_platform": False,
    },
    # ── Open-weight model labs (prices are inference-provider market rates) ──
    "meta": {
        "name": "Meta (open weights; prices via inference providers)",
        "pricing_url": "https://openrouter.ai/meta-llama",
        "api_docs_url": "https://llama.meta.com/",
        "is_inference_platform": False,
    },
    "google-gemma": {
        "name": "Google (Gemma open weights; prices via inference providers)",
        "pricing_url": "https://openrouter.ai/google",
        "api_docs_url": "https://ai.google.dev/gemma",
        "is_inference_platform": False,
    },
    "qwen": {
        "name": "Alibaba / Qwen (open weights; prices via inference providers)",
        "pricing_url": "https://openrouter.ai/qwen",
        "api_docs_url": "https://help.aliyun.com/zh/dashscope/",
        "is_inference_platform": False,
    },
    "nous-research": {
        "name": "Nous Research (open weights; prices via inference providers)",
        "pricing_url": "https://openrouter.ai/nousresearch",
        "api_docs_url": "https://huggingface.co/NousResearch",
        "is_inference_platform": False,
    },
    "tng-tech": {
        "name": "TNG Tech (open weights; prices via inference providers)",
        "pricing_url": "https://openrouter.ai/tngtech",
        "api_docs_url": "https://github.com/tng-tech",
        "is_inference_platform": False,
    },
    # ── Inference platforms ──
    "groq": {
        "name": "Groq (inference platform; ultra-fast LPU inference)",
        "pricing_url": "https://groq.com/pricing/",
        "api_docs_url": "https://console.groq.com/docs/models",
        "is_inference_platform": True,
    },
    "fireworks": {
        "name": "Fireworks AI (inference platform)",
        "pricing_url": "https://fireworks.ai/pricing",
        "api_docs_url": "https://docs.fireworks.ai/",
        "is_inference_platform": True,
    },
    "cloudflare": {
        "name": "Cloudflare Workers AI (inference platform)",
        "pricing_url": "https://developers.cloudflare.com/workers-ai/platform/pricing/",
        "api_docs_url": "https://developers.cloudflare.com/workers-ai/",
        "is_inference_platform": True,
    },
    "together": {
        "name": "Together AI (inference platform)",
        "pricing_url": "https://www.together.ai/pricing",
        "api_docs_url": "https://docs.together.ai/",
        "is_inference_platform": True,
    },
    "novita": {
        "name": "Novita AI (inference platform)",
        "pricing_url": "https://novita.ai/model-api/pricing",
        "api_docs_url": "https://novita.ai/docs",
        "is_inference_platform": True,
    },
    "cerebras": {
        "name": "Cerebras (inference platform; ultra-fast wafer-scale inference)",
        "pricing_url": "https://cloud.cerebras.ai/platform/pricing",
        "api_docs_url": "https://inference-docs.cerebras.ai/",
        "is_inference_platform": True,
    },
    # Azure OpenAI mirrors OpenAI model pricing but draws from Azure startup credits.
    # NOTE: "Founders Hub" was RETIRED on July 2, 2025. Two tracks now exist:
    #   Self-service: $1K immediate + up to $4K after business verification = $5K/entity
    #     Credits valid 90 days ($1K tranche) / 180 days ($4K tranche)
    #     No investor required — just a registered legal business with a software product.
    #   Investor Offer: $100K+ via VC/accelerator referral (invite-only)
    # Stronghold: $1K approved (self-service track). BookCreator: applying.
    # Near-term combined (both at $5K): ~$10K. Reserve headroom for infra.
    # GitHub Copilot can be funded via Azure credits if Azure sub linked to GitHub.
    # Sources: learn.microsoft.com/en-us/startups/changes-microsoft-for-startups
    "azure_openai": {
        "name": "Azure OpenAI (Microsoft; draws from Azure startup credits)",
        "pricing_url": "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        "api_docs_url": "https://learn.microsoft.com/en-us/azure/ai-services/openai/",
        "is_inference_platform": False,
        "notes": (
            "Self-service startup track: $1K immediate + $4K after business verification = $5K/entity. "
            "Stronghold: $1K approved. BookCreator: applying. "
            "Near-term combined (both reach $5K): ~$10K. "
            "Investor Offer (VC-backed): $100K+. "
            "GitHub Copilot can draw from Azure credits if Azure sub linked to GitHub."
        ),
    },
    # Zhipu AI — Chinese frontier models; GLM series; coding plans
    "zhipu": {
        "name": "Zhipu AI (GLM series — Chinese frontier models)",
        "pricing_url": "https://open.bigmodel.cn/pricing",
        "api_docs_url": "https://open.bigmodel.cn/dev/api",
        "is_inference_platform": False,
        "notes": (
            "GLM Coding Plan: heavily discounted GLM-4-AirX for dev use; "
            "free trial credits on signup at open.bigmodel.cn; strong multilingual/Chinese. "
            "OpenAI-compatible API. GLM-Z1 is the reasoning model series."
        ),
    },
    # Hugging Face — Serverless Inference API for open-weight models
    "huggingface": {
        "name": "Hugging Face (Serverless Inference API — 200K+ models)",
        "pricing_url": "https://huggingface.co/pricing",
        "api_docs_url": "https://huggingface.co/docs/api-inference",
        "is_inference_platform": True,
        "notes": (
            "Free tier: serverless inference on popular models (rate-limited). "
            "PRO plan ($9/mo): higher limits, priority inference. "
            "Inference Endpoints: pay-per-hour GPU hosting ($0.60-$3.20/hr on A10G)."
        ),
    },
    # DeepInfra — ultra-cheap open-weight inference
    "deepinfra": {
        "name": "DeepInfra (inference platform — cheapest open-weight hosting)",
        "pricing_url": "https://deepinfra.com/pricing",
        "api_docs_url": "https://deepinfra.com/docs",
        "is_inference_platform": True,
        "notes": "Often cheapest per-token for Llama, Qwen, Mistral variants. Free trial credits.",
    },
    # Inference platform; ultra-fast CoE architecture
    "sambanova": {
        "name": "SambaNova Systems (inference platform; ultra-fast CoE architecture)",
        "pricing_url": "https://cloud.sambanova.ai/apis",
        "api_docs_url": "https://community.sambanova.ai/",
        "is_inference_platform": True,
    },
    # NVIDIA NIM — inference microservices; GPU-optimised open models
    # Free tier: NIM API at build.nvidia.com — free prototyping (rate-limited, DGX Cloud backend)
    # NVIDIA Inception program: free to join, < 10 years old startup; no VC required;
    #   apply at programs.nvidia.com/phoenix/application; contact inceptionprogram@nvidia.com
    "nvidia": {
        "name": "NVIDIA NIM (inference microservices; GPU-optimised open models)",
        "pricing_url": "https://build.nvidia.com/",
        "api_docs_url": "https://docs.api.nvidia.com/",
        "is_inference_platform": True,
        "notes": (
            "Free prototyping NIM API at build.nvidia.com (rate-limited, no credit card). "
            "NVIDIA Inception program: free membership, no VC required, SDKs/DLI courses/co-marketing. "
            "Apply: programs.nvidia.com/phoenix/application"
        ),
    },
    # AI21 Labs — Jamba hybrid SSM-Transformer models; enterprise-focused
    "ai21": {
        "name": "AI21 Labs (Jamba hybrid SSM-Transformer models)",
        "pricing_url": "https://www.ai21.com/pricing",
        "api_docs_url": "https://docs.ai21.com/",
        "is_inference_platform": False,
        "notes": "Free tier: $10 in API credits on signup. Jamba uses SSM+Transformer hybrid for long-context efficiency.",
    },
    # OpenRouter is an inference aggregator — one API key, 200+ models.
    # Markup is minimal (typically 5-10% over provider cost).
    # Has a small free allowance for new accounts; also hosts genuinely free $0 models.
    "openrouter": {
        "name": "OpenRouter (aggregator — routes to 200+ providers via one API)",
        "pricing_url": "https://openrouter.ai/models",
        "api_docs_url": "https://openrouter.ai/docs",
        "is_inference_platform": True,
        "notes": (
            "Single API key for Anthropic, OpenAI, Google, DeepSeek, Mistral, xAI, etc. "
            "Useful for fallback routing and provider comparison. "
            "Free models available at openrouter.ai/models?q=free. "
            "Rate-limit endpoint: GET https://openrouter.ai/api/v1/auth/key"
        ),
    },
}


# ---------------------------------------------------------------------------
# Model catalogue  (sorted loosely by provider category, then input price)
# ---------------------------------------------------------------------------

MODELS: list[ModelPricing] = [
    # ══════════════════════════════════════════════════════════════════════
    # ANTHROPIC CLAUDE
    # Prompt caching: write = input x 1.25 ; read = input x 0.10
    # Source: https://platform.claude.com/docs/en/docs/about-claude/models/overview
    # Free tier: none — requires credit card / contract
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="anthropic",
        model_id="claude-opus-4-7",
        input_mtok=5.00,
        output_mtok=25.00,
        context_window=1_000_000,
        max_output=128_000,
        cache_write_mtok=6.25,
        cache_read_mtok=0.50,
        free_tier=None,
        tokenizer_note=(
            "New tokenizer: 1M tokens ~ 555K words (vs 750K on older models). "
            "Same prose costs ~35% MORE tokens — raises effective per-word cost."
        ),
        swe_bench_verified=79.4,
        swe_bench_note="High-compute scaffold; standard: 72.5%",
        mmlu=87.4,
        gpqa_diamond=74.9,
        terminal_bench=43.2,  # source: anthropic.com/news/claude-4
        arena_elo=1491,  # lmarena.ai leaderboard May 2026
        intelligence_index=57,
        supports_thinking=False,  # adaptive thinking auto-engages; not user-toggled
        knowledge_cutoff="2026-01",
        pricing_url="https://platform.claude.com/docs/en/docs/about-claude/models/overview",
        notes="Most capable Claude. Step-change agentic coding vs Opus 4.6. New tokenizer raises real-world cost.",
    ),
    ModelPricing(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        input_mtok=3.00,
        output_mtok=15.00,
        context_window=1_000_000,
        max_output=64_000,
        cache_write_mtok=3.75,
        cache_read_mtok=0.30,
        free_tier=None,
        tokenizer_note="Old tokenizer: 1M tokens ~ 750K words.",
        swe_bench_verified=80.2,
        swe_bench_note="High-compute; standard (Sonnet 4 baseline): 72.7%",
        mmlu=85.4,
        gpqa_diamond=70.0,
        arena_elo=1439,  # lmarena.ai leaderboard May 2026
        supports_thinking=True,
        knowledge_cutoff="2025-08",
        pricing_url="https://platform.claude.com/docs/en/docs/about-claude/models/overview",
        notes="Best Claude speed/intelligence balance. Extended thinking up to 64K tokens. 1M context.",
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
        free_tier=None,
        supports_thinking=True,
        knowledge_cutoff="2025-02",
        pricing_url="https://platform.claude.com/docs/en/docs/about-claude/models/overview",
        notes="Fastest Claude. Near-frontier intelligence. Ideal for routing, classification, simple agentic steps.",
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
        free_tier=None,
        supports_thinking=True,
        knowledge_cutoff="2025-05",
        pricing_url="https://platform.claude.com/docs/en/docs/about-claude/models/overview",
        notes="Legacy flagship. Same price as Opus 4.7 but older tokenizer. Still capable for extended thinking.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # OPENAI
    # Source: https://openrouter.ai/openai ; platform.openai.com/docs/models
    # Free tier: none — requires credit card
    #
    # API USAGE TIERS (auto-advance when spend + age both met):
    #   Tier 1:  $5  cumulative           — codex-mini-latest, gpt-4o available
    #   Tier 2:  $50 cumulative, 7 days   — higher rate limits
    #   Tier 3:  $100 cumulative, 7 days  — o4-mini unlocked
    #   Tier 4:  $250 cumulative, 14 days — o3 unlocked
    #   Tier 5:  $1K  cumulative, 30 days — all models, max limits
    #
    # ChatGPT subscription tiers (GPT-5.x generation as of Feb 2026):
    #   Plus $20/mo  — base model + Codex 10-60 cloud tasks/5hr window
    #   Pro  $100/mo — 5x limits, o3-pro, 256K context; promo 10x until May 31 2026
    #   Pro  $200/mo — 20x limits, 1M context, ~250 Deep Research/month
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="openai",
        model_id="gpt-4.1",
        input_mtok=2.00,
        output_mtok=8.00,
        context_window=1_047_576,
        free_tier=None,
        swe_bench_verified=54.6,
        mmlu=90.2,
        gpqa_diamond=66.3,
        arena_elo=1381,
        knowledge_cutoff="2024-06",
        pricing_url="https://openrouter.ai/openai/gpt-4.1",
        notes="OpenAI long-context flagship. ~1M context. Strong advanced coding and reasoning.",
    ),
    ModelPricing(
        provider="openai",
        model_id="gpt-4o-mini",
        input_mtok=0.15,
        output_mtok=0.60,
        context_window=128_000,
        cache_read_mtok=0.075,
        free_tier=None,
        knowledge_cutoff="2023-10",
        pricing_url="https://openrouter.ai/openai/gpt-4o-mini",
        notes=(
            "Most popular OpenAI model by volume. Cached reads at $0.075/MTok. "
            "Great for classification, extraction, and structured output at scale."
        ),
    ),
    ModelPricing(
        provider="openai",
        model_id="codex-mini-latest",
        input_mtok=1.50,
        output_mtok=6.00,
        cache_read_mtok=0.375,
        context_window=200_000,
        max_output=100_000,
        free_tier=None,
        supports_thinking=True,
        knowledge_cutoff="2024-06",
        pricing_url="https://developers.openai.com/codex/pricing",
        notes=(
            "OpenAI Codex agent model — autonomous SWE tasks in cloud sandboxes. "
            "ChatGPT Plus: 10-60 cloud tasks/5hr. Pro $100: 50-300. Pro $200: 200-1200. "
            "API: available from Tier 1+ ($5 cumulative spend). No model gating. "
            "Cached input $0.375/MTok. Supports function calling, structured output, streaming."
        ),
    ),
    ModelPricing(
        provider="openai",
        model_id="gpt-4o",
        input_mtok=2.50,
        output_mtok=10.00,
        context_window=128_000,
        free_tier=None,
        knowledge_cutoff="2023-10",
        pricing_url="https://openrouter.ai/openai/gpt-4o",
        notes="Multimodal flagship (text + vision + audio). Solid general-purpose. Smaller context than newer peers.",
    ),
    ModelPricing(
        provider="openai",
        model_id="o3",
        input_mtok=2.00,
        output_mtok=8.00,
        context_window=200_000,
        free_tier=None,
        swe_bench_verified=69.1,
        mmlu=91.6,
        gpqa_diamond=87.7,
        humanity_last_exam=20.3,
        arena_elo=1424,
        supports_thinking=True,
        knowledge_cutoff="2024-06",
        pricing_url="https://openrouter.ai/openai/o3",
        notes="Reasoning model. Excels at math, science, coding, visual reasoning. 200K context.",
    ),
    ModelPricing(
        provider="openai",
        model_id="o4-mini",
        input_mtok=1.10,
        output_mtok=4.40,
        context_window=200_000,
        free_tier=None,
        swe_bench_verified=68.1,
        gpqa_diamond=81.4,
        live_code_bench=74.9,
        arena_elo=1362,
        supports_thinking=True,
        knowledge_cutoff="2024-06",
        pricing_url="https://openrouter.ai/openai/o4-mini",
        notes="Compact reasoning model. Cost-efficient for scenarios where latency and price matter.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # GOOGLE GEMINI
    # Source: https://ai.google.dev/gemini-api/docs/pricing
    # Free tier: yes — AI Studio free tier with rate limits on all models
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="google",
        model_id="gemini-3.1-pro-preview",
        input_mtok=2.00,  # ≤200K prompt
        output_mtok=12.00,
        context_window=1_000_000,
        free_tier="AI Studio free tier (rate-limited; not for production)",
        swe_bench_verified=80.6,
        swe_bench_note="With tools; non-tool: ~72%",
        mmlu=92.6,
        gpqa_diamond=94.3,
        humanity_last_exam=51.4,
        arena_elo=1493,  # lmarena.ai leaderboard May 2026
        intelligence_index=57,
        knowledge_cutoff="2025-11",
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        notes="Tiered: >200K prompt costs $4/$18 input/output. Preview only — not yet GA.",
    ),
    ModelPricing(
        provider="google",
        model_id="gemini-2.5-pro",
        input_mtok=1.25,  # ≤200K
        output_mtok=10.00,
        context_window=1_000_000,
        free_tier="AI Studio free tier (rate-limited)",
        swe_bench_verified=63.8,
        swe_bench_note="Custom agent setup",
        mmlu=90.0,
        gpqa_diamond=84.0,
        live_code_bench=70.4,
        humanity_last_exam=18.8,
        arena_elo=1460,  # lmarena.ai mid-2025 peak; settled lower as newer models launched
        knowledge_cutoff="2025-01",
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        notes="Tiered: >200K costs $2.50/$15. Strong coding; available on Vertex AI + AI Studio.",
    ),
    ModelPricing(
        provider="google",
        model_id="gemini-2.0-flash",
        input_mtok=0.10,
        output_mtok=0.40,
        context_window=1_000_000,
        free_tier="Free on AI Studio (generous rate limits; audio/image input included)",
        free_tier_rpm=15,
        free_tier_tpm=1_000_000,
        knowledge_cutoff="2024-08",
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        notes=(
            "Latest generation Flash. Very fast; multimodal (image, audio, video). "
            "Experimental thinking mode in gemini-2.0-flash-thinking-exp variant."
        ),
    ),
    ModelPricing(
        provider="google",
        model_id="gemini-2.5-flash",
        input_mtok=0.30,
        output_mtok=2.50,
        context_window=1_000_000,
        free_tier="AI Studio free tier (rate-limited); also free on Google AI Studio",
        swe_bench_verified=60.4,
        mmlu=86.6,
        gpqa_diamond=82.8,
        arena_elo=1412,
        knowledge_cutoff="2025-02",
        supports_thinking=True,
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        notes="Best Gemini value. 1M context. Thinking mode supported. Generous free quota.",
    ),
    ModelPricing(
        provider="google",
        model_id="gemini-2.5-flash-lite",
        input_mtok=0.10,
        output_mtok=0.40,
        context_window=1_000_000,
        free_tier="Free of charge on AI Studio (rate-limited)",
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        notes="Cheapest production Gemini. Free tier available. Great for extraction at massive scale.",
    ),
    ModelPricing(
        provider="google",
        model_id="gemini-3.1-flash-lite-preview",
        input_mtok=0.25,
        output_mtok=1.50,
        context_window=1_000_000,
        free_tier="Free of charge on AI Studio (preview; rate-limited)",
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        notes="Preview. Batch API available at 50% discount on paid tier.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # DEEPSEEK
    # Source: https://api-docs.deepseek.com/quick_start/pricing/
    # Cache hit price cut to 1/10 of launch price on 2026-04-26.
    # Free tier: trial credits on signup
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="deepseek",
        model_id="deepseek-v4-flash",
        input_mtok=0.14,
        output_mtok=0.28,
        context_window=1_000_000,
        max_output=384_000,
        cache_read_mtok=0.0028,  # cache hit = input/50
        free_tier="Trial credits on signup",
        swe_bench_verified=79.0,
        swe_bench_note="Max reasoning mode; non-think: 73.7%",
        mmlu=88.7,
        gpqa_diamond=88.1,
        live_code_bench=91.6,
        humanity_last_exam=34.8,
        supports_thinking=True,
        pricing_url="https://api-docs.deepseek.com/quick_start/pricing/",
        notes=(
            "Exceptional value. Cache hits at $0.0028/MTok (50x cheaper than miss). "
            "384K max output. Thinking toggle available (off by default)."
        ),
    ),
    ModelPricing(
        provider="deepseek",
        model_id="deepseek-v4-pro",
        input_mtok=0.435,  # 75% launch discount until 2026-05-31
        output_mtok=0.87,  # standard post-discount: ~$1.74/$3.48
        context_window=1_000_000,
        max_output=384_000,
        cache_read_mtok=0.003625,
        free_tier="Trial credits on signup",
        swe_bench_verified=80.6,
        swe_bench_note="Max reasoning mode; non-think: 73.6%",
        mmlu=90.1,
        gpqa_diamond=90.1,
        live_code_bench=93.5,
        humanity_last_exam=37.7,
        supports_thinking=True,
        arena_elo=1432,  # lmarena.ai leaderboard May 2026
        knowledge_cutoff="2024-11",
        pricing_url="https://api-docs.deepseek.com/quick_start/pricing/",
        notes=(
            "75% launch discount until 2026-05-31. "
            "Post-discount standard: ~$1.74/$3.48/$0.0145 cache. "
            "Thinking mode on by default. Replaces deepseek-reasoner."
        ),
    ),
    ModelPricing(
        provider="deepseek",
        model_id="deepseek-r1-0528",
        input_mtok=0.50,
        output_mtok=2.15,
        context_window=163_840,
        free_tier="Trial credits on signup",
        swe_bench_verified=57.6,
        mmlu=93.4,
        gpqa_diamond=81.0,
        live_code_bench=73.3,
        humanity_last_exam=17.7,
        aime_2024=87.5,  # AIME 2025 score (no 2024 score available; model released 2025)
        arena_elo=1426,
        supports_thinking=True,
        knowledge_cutoff="2024-07",
        pricing_url="https://openrouter.ai/deepseek/deepseek-r1-0528",
        notes="Open-source reasoning model. Reasoning tokens visible. Performance on par with o1.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # xAI GROK
    # Source: https://openrouter.ai/x-ai/grok-4
    # Free tier: some free credits for new accounts
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="xai",
        model_id="grok-4",
        input_mtok=3.00,
        output_mtok=15.00,
        context_window=256_000,
        free_tier="Limited free credits for new accounts",
        swe_bench_verified=73.0,
        swe_bench_note="Grok-4 Code variant; range 72-75% across evals",
        mmlu=92.1,
        gpqa_diamond=87.5,
        humaneval=97.0,
        live_code_bench=79.0,
        humanity_last_exam=25.4,
        terminal_bench=60.0,
        supports_thinking=True,  # reasoning always on; cannot disable
        arena_elo=1442,  # lmarena.ai leaderboard May 2026
        knowledge_cutoff="2025-07",
        pricing_url="https://docs.x.ai/docs/models",
        notes=(
            "Reasoning always active — cannot be disabled. "
            "Pricing escalates for requests >128K total tokens. "
            "Batch API: 20-50% discount. Supports vision + parallel tool calling."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # MISTRAL AI
    # Source: https://mistral.ai/pricing and openrouter.ai/mistralai
    #
    # FREE TIER — La Plateforme has a genuinely generous developer free tier:
    #   - Mistral Small, Mistral NeMo, open-weight models: free with rate limits
    #   - Codestral: FREE for individual/IDE use at codestral.mistral.ai
    #     (separate endpoint + key from main API; for VS Code, Continue, etc.)
    #   - Typical free limits: ~1 req/s, ~500K tokens/month on eligible models
    #   - No credit card required to start
    #   - 7 people/entities each get their own free key with full quota
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="mistral",
        model_id="codestral-latest",
        input_mtok=0.30,
        output_mtok=0.90,
        context_window=256_000,
        free_tier=(
            "FREE for individual developers at codestral.mistral.ai "
            "(separate API key; no credit card; for IDE integrations)"
        ),
        free_tier_rpm=30,
        supports_tool_use=True,
        supports_vision=False,
        knowledge_cutoff="2024-12",
        pricing_url="https://mistral.ai/pricing",
        notes=(
            "Dedicated code completion + instruction model. "
            "Free at codestral.mistral.ai for individuals/IDEs (VS Code, Continue, Cursor). "
            "Paid API available at api.mistral.ai for production."
        ),
    ),
    ModelPricing(
        provider="mistral",
        model_id="mistral-small-latest",
        input_mtok=0.10,
        output_mtok=0.30,
        context_window=128_000,
        free_tier="La Plateforme free tier — eligible model (~1 req/s, ~500K tok/month)",
        free_tier_rpm=6,
        free_tier_tpm=500_000,  # approximate monthly cap converted, verify at console
        knowledge_cutoff="2024-10",
        pricing_url="https://mistral.ai/pricing",
        notes="Fastest Mistral. Strong for classification, extraction. On free dev tier.",
    ),
    ModelPricing(
        provider="mistral",
        model_id="mistral-medium-latest",
        input_mtok=0.40,
        output_mtok=2.00,
        context_window=128_000,
        free_tier="La Plateforme free tier — check console for current eligibility",
        knowledge_cutoff="2024-12",
        pricing_url="https://mistral.ai/pricing",
        notes="Mid-tier Mistral. Good balance of cost and quality.",
    ),
    ModelPricing(
        provider="mistral",
        model_id="mistral-large-latest",
        input_mtok=2.00,
        output_mtok=6.00,
        context_window=131_072,
        free_tier="La Plateforme free tier — check console for eligibility",
        knowledge_cutoff="2024-12",
        pricing_url="https://mistral.ai/pricing",
        notes="Mistral's flagship general-purpose model. Strong reasoning, multilingual, tool use.",
    ),
    ModelPricing(
        provider="mistral",
        model_id="mistral-nemo",
        input_mtok=0.15,
        output_mtok=0.15,
        context_window=128_000,
        free_tier="La Plateforme free tier — eligible; very low cost",
        free_tier_rpm=6,
        knowledge_cutoff="2024-07",
        pricing_url="https://mistral.ai/pricing",
        notes="12B param. Apache 2.0 licence. Flat $0.15/$0.15. Multilingual. On free dev tier.",
    ),
    ModelPricing(
        provider="mistral",
        model_id="devstral-medium",
        input_mtok=0.40,
        output_mtok=2.00,
        context_window=131_072,
        free_tier="La Plateforme free tier — check console; coding model may have separate quota",
        swe_bench_verified=61.6,
        swe_bench_note="SWE-Bench Verified; claimed to beat Gemini 2.5 Pro and GPT-4.1",
        knowledge_cutoff="2025-06",
        pricing_url="https://openrouter.ai/mistralai/devstral-medium-2507",
        notes="Coding specialist (Mistral + All Hands AI). Best SWE-bench at this price tier.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # COHERE
    # Source: https://cohere.com/pricing
    # Free tier: trial API key (non-commercial use, rate-limited)
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="cohere",
        model_id="command-r-plus-08-2024",
        input_mtok=2.50,
        output_mtok=10.00,
        context_window=128_000,
        free_tier="Trial API key (non-commercial; rate-limited)",
        knowledge_cutoff="2024-08",
        pricing_url="https://cohere.com/pricing",
        notes="~50% higher throughput vs Apr-2024 version. Strong at RAG and enterprise workflows.",
    ),
    ModelPricing(
        provider="cohere",
        model_id="command-r-03-2024",
        input_mtok=0.50,
        output_mtok=1.50,
        context_window=128_000,
        free_tier="Trial API key (non-commercial; rate-limited)",
        knowledge_cutoff="2024-03",
        pricing_url="https://cohere.com/pricing",
        notes="Budget Command model. Good for RAG retrieval, structured extraction, grounding.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # PERPLEXITY AI (Sonar — search-grounded models)
    # Source: https://docs.perplexity.ai/guides/pricing
    # NOTE: Sonar models include live web search in their responses.
    #       Pricing also has a per-request fee ($0.005/search call) on top of tokens.
    # Free tier: pplx.ai chat interface free; API requires payment
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="perplexity",
        model_id="sonar",
        input_mtok=1.00,
        output_mtok=1.00,
        context_window=200_000,
        free_tier=None,
        free_tier_rpm=50,  # Tier 0: 50 RPM on standard Sonar models
        paid_tier_rpm=4000,  # Tier 4+
        supports_vision=False,
        pricing_url="https://docs.perplexity.ai/guides/pricing",
        notes=(
            "Web-search grounded. Flat $1/$1 pricing. "
            "+$0.005/search call on top of tokens. Tier 0 free: 50 RPM."
        ),
    ),
    ModelPricing(
        provider="perplexity",
        model_id="sonar-pro",
        input_mtok=3.00,
        output_mtok=15.00,
        context_window=200_000,
        free_tier=None,
        supports_vision=False,
        pricing_url="https://docs.perplexity.ai/guides/pricing",
        notes="Multi-step search; complex research queries. +$0.005/search call.",
    ),
    ModelPricing(
        provider="perplexity",
        model_id="sonar-reasoning-pro",
        input_mtok=2.00,
        output_mtok=8.00,
        context_window=200_000,
        free_tier=None,
        supports_thinking=True,
        supports_vision=False,
        pricing_url="https://docs.perplexity.ai/guides/pricing",
        notes="Search + reasoning. CoT on top of live web data. +$0.005/search call.",
    ),
    ModelPricing(
        provider="perplexity",
        model_id="sonar-deep-research",
        input_mtok=2.00,
        output_mtok=8.00,
        context_window=200_000,
        free_tier=None,
        free_tier_rpm=5,  # Tier 0: only 5 RPM — very limited
        supports_vision=False,
        pricing_url="https://docs.perplexity.ai/guides/pricing",
        notes=(
            "Autonomous multi-step research (many web searches per query). "
            "+$2/1K citation tokens. Tier 0 free: only 5 RPM."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # AMAZON (AWS Bedrock — Nova family)
    # Source: https://openrouter.ai/amazon ; aws.amazon.com/bedrock/pricing
    # Free tier: AWS Free Tier (~limited Nova Micro/Lite calls in first 12 months)
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="amazon",
        model_id="amazon.nova-pro-v1",
        input_mtok=0.80,
        output_mtok=3.20,
        context_window=300_000,
        free_tier="AWS Free Tier: limited monthly calls in first 12 months",
        supports_vision=True,
        knowledge_cutoff="2024-03",
        pricing_url="https://openrouter.ai/amazon/nova-pro-v1",
        notes="Multimodal (image + video text input). Bedrock-native. 300K context.",
    ),
    ModelPricing(
        provider="amazon",
        model_id="amazon.nova-lite-v1",
        input_mtok=0.06,
        output_mtok=0.24,
        context_window=300_000,
        free_tier="AWS Free Tier: limited monthly calls in first 12 months",
        supports_vision=True,
        knowledge_cutoff="2024-03",
        pricing_url="https://openrouter.ai/amazon/nova-lite-v1",
        notes="Very low-cost multimodal. 300K context. Image + video + text input.",
    ),
    ModelPricing(
        provider="amazon",
        model_id="amazon.nova-micro-v1",
        input_mtok=0.035,
        output_mtok=0.14,
        context_window=128_000,
        free_tier="AWS Free Tier: limited monthly calls in first 12 months",
        supports_vision=False,
        knowledge_cutoff="2024-03",
        pricing_url="https://openrouter.ai/amazon/nova-micro-v1",
        notes="Lowest-latency Nova. Text-only. Lowest price in Amazon's lineup.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # MICROSOFT (Phi small models — via Azure AI / OpenRouter)
    # Source: https://openrouter.ai/microsoft
    # Free tier: $200 Azure free credits for new accounts
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="microsoft",
        model_id="phi-4",
        input_mtok=0.065,
        output_mtok=0.14,
        context_window=16_384,
        free_tier="$200 Azure free credits on new account",
        supports_vision=False,
        knowledge_cutoff="2024-06",
        pricing_url="https://openrouter.ai/microsoft/phi-4",
        notes="14B param SLM. Optimised for complex reasoning with constrained resources.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # MOONSHOT AI  (Kimi)
    # Source: https://openrouter.ai/moonshotai/kimi-k2
    # Free tier: trial credits on signup
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="moonshot",
        model_id="kimi-k2",
        input_mtok=0.57,
        output_mtok=2.30,
        context_window=131_072,
        free_tier="Trial credits on signup",
        swe_bench_verified=65.8,
        swe_bench_note="Single attempt agentic; multi-attempt: 71.6%",
        mmlu=89.5,
        gpqa_diamond=75.1,
        live_code_bench=53.7,
        arena_elo=1426,  # lmarena.ai leaderboard May 2026
        knowledge_cutoff="2025-07",
        pricing_url="https://openrouter.ai/moonshotai/kimi-k2",
        notes="1T-param MoE (32B active). Competitive with frontier models at mid-range cost.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # MINIMAX
    # Source: https://openrouter.ai/minimax/minimax-m1
    # Free tier: trial credits on signup
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="minimax",
        model_id="minimax-m1",
        input_mtok=0.40,
        output_mtok=2.20,
        context_window=1_000_000,
        free_tier="Trial credits on signup",
        knowledge_cutoff="2025-06",
        pricing_url="https://openrouter.ai/minimax/minimax-m1",
        notes="456B total / 45.9B active MoE. 1M context. Hybrid architecture.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # WRITER  (Palmyra — enterprise-focused)
    # Source: https://openrouter.ai/writer/palmyra-x5
    # Free tier: none (enterprise-focused)
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="writer",
        model_id="palmyra-x5",
        input_mtok=0.60,
        output_mtok=6.00,
        context_window=1_040_000,
        free_tier=None,
        knowledge_cutoff="2025-12",
        pricing_url="https://openrouter.ai/writer/palmyra-x5",
        notes="Purpose-built for enterprise AI agents. 1M+ context. High output price reflects quality focus.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # META LLAMA  (open weights; prices are inference-provider market rates)
    # Free tier: varies by inference provider
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="meta",
        model_id="llama-4-maverick",
        input_mtok=0.15,
        output_mtok=0.60,
        context_window=1_048_576,
        free_tier="Free on many providers (Groq free tier, Cloudflare Workers AI free tier)",
        mmlu=85.5,
        gpqa_diamond=69.8,
        humaneval=90.0,
        live_code_bench=43.4,
        arena_elo=1292,
        knowledge_cutoff="2024-10",
        pricing_url="https://openrouter.ai/meta-llama/llama-4-maverick",
        notes="Open weights. ~1M context. Prices vary: Groq, Together, Fireworks all host it.",
    ),
    ModelPricing(
        provider="meta",
        model_id="llama-3.3-70b",
        input_mtok=0.59,
        output_mtok=0.79,
        context_window=131_072,
        free_tier="Free tier on Groq (rate-limited)",
        pricing_url="https://groq.com/pricing/",
        notes="Strong open-weight general-purpose model. Via Groq at ~394 t/s.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # GOOGLE GEMMA  (open weights via Google / inference providers)
    # Source: https://openrouter.ai/google/gemma-3-27b-it
    # Free tier: Google AI Studio free tier
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="google-gemma",
        model_id="gemma-3-27b-it",
        input_mtok=0.08,
        output_mtok=0.16,
        context_window=131_072,
        free_tier="Google AI Studio free tier",
        supports_vision=True,
        knowledge_cutoff="2024-08",
        pricing_url="https://openrouter.ai/google/gemma-3-27b-it",
        notes="Open weights. Multimodal. 140+ languages. Very cheap via inference providers.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # ALIBABA / QWEN  (open weights via inference providers)
    # Source: https://openrouter.ai/qwen/qwen3-235b-a22b
    # Free tier: Alibaba Cloud free trial credits
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="qwen",
        model_id="qwen3-235b-a22b",
        input_mtok=0.455,
        output_mtok=1.82,
        context_window=131_072,
        free_tier="Alibaba Cloud free trial credits on signup",
        mmlu=87.8,
        gpqa_diamond=81.1,
        humaneval=77.6,
        live_code_bench=70.7,
        arena_elo=1369,
        aime_2024=81.5,  # AIME 2025 score (model too recent for 2024)
        supports_thinking=True,
        knowledge_cutoff="2025-06",
        pricing_url="https://openrouter.ai/qwen/qwen3-235b-a22b",
        notes="MoE 235B total / 22B active. Thinking mode available. Open weights.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # NOUS RESEARCH  (open weights via inference providers)
    # Source: https://openrouter.ai/nousresearch/hermes-3-llama-3.1-405b
    # Free tier: none direct; depends on inference provider
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="nous-research",
        model_id="hermes-3-llama-3.1-405b",
        input_mtok=1.00,
        output_mtok=1.00,
        context_window=131_072,
        free_tier=None,
        knowledge_cutoff="2023-12",
        pricing_url="https://openrouter.ai/nousresearch/hermes-3-llama-3.1-405b",
        notes="Full-parameter finetune of Llama 3.1 405B. Flat $1/$1 pricing simplifies budgeting.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # TNG TECH  (open weights distillation via inference providers)
    # Source: https://openrouter.ai/tngtech/deepseek-r1t2-chimera
    # Free tier: none direct
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="tng-tech",
        model_id="deepseek-r1t2-chimera",
        input_mtok=0.30,
        output_mtok=1.10,
        context_window=130_000,
        free_tier=None,
        supports_thinking=True,
        knowledge_cutoff="2024-07",
        pricing_url="https://openrouter.ai/tngtech/deepseek-r1t2-chimera",
        notes="671B MoE. Chimera distillation of DeepSeek R1. Tested to ~130K context.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # GROQ  (inference platform — ultra-fast LPU hardware)
    # Source: https://groq.com/pricing/
    # Free tier: yes — free API key at console.groq.com with rate limits
    # Prompt caching: 50% off cached input tokens
    # Batch API: 50% discount for async
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="groq",
        model_id="llama-3.1-8b-instant",
        input_mtok=0.05,
        output_mtok=0.08,
        context_window=128_000,
        inference_speed_tps=840,
        free_tier="Free API key — no credit card; rate-limited (30 RPM / 6K TPM)",
        free_tier_rpm=30,
        free_tier_tpm=6_000,
        pricing_url="https://groq.com/pricing/",
        notes=(
            "Fastest cheap model on Groq. 840 t/s. Cached tokens excluded from rate limit counters."
        ),
    ),
    ModelPricing(
        provider="groq",
        model_id="llama-4-scout-17b-16e",
        input_mtok=0.11,
        output_mtok=0.34,
        context_window=128_000,
        inference_speed_tps=594,
        free_tier="Free API key — 30 RPM / 6K TPM",
        free_tier_rpm=30,
        free_tier_tpm=6_000,
        pricing_url="https://groq.com/pricing/",
        notes="Llama 4 Scout on Groq. 594 t/s. Good quality/speed/cost balance.",
    ),
    ModelPricing(
        provider="groq",
        model_id="llama-3.3-70b-versatile",
        input_mtok=0.59,
        output_mtok=0.79,
        context_window=128_000,
        inference_speed_tps=394,
        free_tier="Free API key — 30 RPM / 12K TPM",
        free_tier_rpm=30,
        free_tier_tpm=12_000,
        pricing_url="https://groq.com/pricing/",
        notes="Full-power 70B on Groq at 394 t/s. GPT-4o quality at ~4x lower cost.",
    ),
    ModelPricing(
        provider="groq",
        model_id="gpt-oss-120b",
        input_mtok=0.15,
        output_mtok=0.60,
        context_window=128_000,
        inference_speed_tps=500,
        free_tier="Free API key — 30 RPM / 6K TPM",
        free_tier_rpm=30,
        free_tier_tpm=6_000,
        pricing_url="https://groq.com/pricing/",
        notes="OpenAI open-source 120B on Groq. 500 t/s. Strong quality at low price.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # FIREWORKS AI  (inference platform)
    # Source: https://fireworks.ai/pricing
    # Free tier: $1 in credits for new users
    # Prompt caching: 50% off cached input; Batch API: 50% off
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="fireworks",
        model_id="accounts/fireworks/models/deepseek-v4-pro",
        input_mtok=1.74,  # Fireworks lists full non-discounted price
        output_mtok=3.48,
        context_window=1_000_000,
        cache_read_mtok=0.87,  # 50% cached input discount
        free_tier="$1 free credit on signup",
        supports_thinking=True,
        pricing_url="https://fireworks.ai/pricing",
        notes=(
            "Fireworks hosts DeepSeek-V4-Pro at full (non-launch-discounted) price. "
            "Cached input at 50% off. Batch API also 50% off."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # CLOUDFLARE WORKERS AI
    # Source: https://developers.cloudflare.com/workers-ai/platform/pricing/
    # Pricing via Neurons: $0.011/1K Neurons (units of compute)
    # Equivalent per-token rates shown below.
    # Free tier: 10K Neurons/day free on ALL plans (Free + Paid)
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="cloudflare",
        model_id="@cf/meta/llama-3.1-70b-instruct",
        input_mtok=0.293,
        output_mtok=2.253,
        context_window=131_072,
        free_tier="10K Neurons/day free (all plans; resets daily at 00:00 UTC)",
        pricing_url="https://developers.cloudflare.com/workers-ai/platform/pricing/",
        notes="Runs at Cloudflare edge. Free daily allowance covers ~34K input tokens at zero cost.",
    ),
    ModelPricing(
        provider="cloudflare",
        model_id="@cf/meta/llama-3.2-1b-instruct",
        input_mtok=0.027,
        output_mtok=0.201,
        context_window=131_072,
        inference_speed_tps=None,
        free_tier="10K Neurons/day free",
        pricing_url="https://developers.cloudflare.com/workers-ai/platform/pricing/",
        notes="Smallest/cheapest Cloudflare model. Good for edge classification and triage.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # TOGETHER AI  (inference platform)
    # Source: https://docs.together.ai/docs/serverless-models
    # Free tier: $1 free credit on signup
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="together",
        model_id="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        input_mtok=0.88,
        output_mtok=0.88,
        context_window=131_072,
        free_tier="$1 free credit on signup",
        pricing_url="https://docs.together.ai/docs/serverless-models",
        notes="Flat $0.88/$0.88 pricing simplifies cost estimation. Strong general-purpose model.",
    ),
    ModelPricing(
        provider="together",
        model_id="Qwen/Qwen3.5-397B-A17B-Instruct-FP8",
        input_mtok=0.60,
        output_mtok=3.60,
        context_window=262_144,
        free_tier="$1 free credit on signup",
        supports_thinking=True,
        pricing_url="https://docs.together.ai/docs/serverless-models",
        notes="397B MoE (17B active) on Together. 256K context. Prompt caching available.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # NOVITA AI  (inference platform)
    # Source: https://novita.ai/model-api/pricing
    # Free tier: some models permanently free; batch at 50% off
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="novita",
        model_id="meta-llama/llama-3.1-8b-instruct",
        input_mtok=0.02,
        output_mtok=0.05,
        context_window=16_384,
        free_tier="Batch inference at 50% discount; some models permanently free",
        pricing_url="https://novita.ai/model-api/pricing",
        notes="Cheapest 8B inference option listed. Very high volume / low cost use cases.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # CEREBRAS  (inference platform — wafer-scale ultra-fast)
    # Source: https://cloud.cerebras.ai
    # Free tier: yes — free trial tier at cloud.cerebras.ai (no credit card)
    # Specific per-token pricing not published; refer to pricing page for rates.
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="cerebras",
        model_id="llama-4-scout-17b",
        input_mtok=0.10,  # approximate; verify at cloud.cerebras.ai/platform/pricing
        output_mtok=0.10,
        context_window=131_072,
        inference_speed_tps=2000,
        free_tier="Free trial tier at cloud.cerebras.ai (no credit card required)",
        pricing_url="https://cloud.cerebras.ai/platform/pricing",
        notes=(
            "2,000+ t/s — one of the fastest available inference platforms. "
            "Wafer-scale CS-3 hardware. Pricing approximate; check page for current rates."
        ),
    ),
    ModelPricing(
        provider="cerebras",
        model_id="gpt-oss-120b",
        input_mtok=0.60,  # approximate; verify at cloud.cerebras.ai/platform/pricing
        output_mtok=0.60,
        context_window=131_072,
        inference_speed_tps=3000,
        free_tier="Free trial tier at cloud.cerebras.ai (no credit card required)",
        pricing_url="https://cloud.cerebras.ai/platform/pricing",
        notes="3,000 t/s — fastest 120B inference available. Pricing approximate.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # ZHIPU AI  (GLM series — Chinese frontier; strong coding + multilingual)
    # Source: https://open.bigmodel.cn/pricing
    # Free tier: trial credits on signup at open.bigmodel.cn
    # GLM Coding Plan: GLM-4-AirX at ~60% discount for developer/coding workloads
    # API is OpenAI-compatible — litellm prefix: "zhipuai/"
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="zhipu",
        model_id="glm-4-plus",
        input_mtok=0.70,
        output_mtok=0.70,
        context_window=128_000,
        free_tier="Trial credits on signup at open.bigmodel.cn",
        knowledge_cutoff="2024-12",
        pricing_url="https://open.bigmodel.cn/pricing",
        notes=(
            "Zhipu AI flagship. Strong Chinese + English. OpenAI-compatible API. "
            "Flat $0.70/$0.70 pricing. Multimodal (vision)."
        ),
    ),
    ModelPricing(
        provider="zhipu",
        model_id="glm-4-air",
        input_mtok=0.14,
        output_mtok=0.14,
        context_window=128_000,
        free_tier="Trial credits on signup; GLM Coding Plan reduces to ~$0.06/MTok",
        knowledge_cutoff="2024-12",
        pricing_url="https://open.bigmodel.cn/pricing",
        notes=(
            "GLM Coding Plan: ~60% discount for dev/coding use = effectively $0.05-$0.06/MTok. "
            "Very fast, very cheap. Strong at structured tasks and code generation."
        ),
    ),
    ModelPricing(
        provider="zhipu",
        model_id="glm-z1-plus",
        input_mtok=0.70,
        output_mtok=0.70,
        context_window=128_000,
        free_tier="Trial credits on signup",
        supports_thinking=True,
        knowledge_cutoff="2024-12",
        pricing_url="https://open.bigmodel.cn/pricing",
        notes="GLM-Z1 reasoning series. CoT thinking mode. Strong at math, science, coding.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # DEEPINFRA  (inference platform — ultra-cheap open-weight hosting)
    # Source: https://deepinfra.com/pricing
    # Free tier: trial API credits on signup
    # Often the cheapest per-token for Llama, Qwen, Mistral open-weight models
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="deepinfra",
        model_id="meta-llama/Meta-Llama-3.1-8B-Instruct",
        input_mtok=0.055,
        output_mtok=0.055,
        context_window=131_072,
        free_tier="Trial API credits on signup",
        pricing_url="https://deepinfra.com/meta-llama/Meta-Llama-3.1-8B-Instruct",
        notes="Often cheapest 8B serving. Flat rate. Great for high-volume lightweight tasks.",
    ),
    ModelPricing(
        provider="deepinfra",
        model_id="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        input_mtok=0.23,
        output_mtok=0.40,
        context_window=131_072,
        free_tier="Trial API credits on signup",
        pricing_url="https://deepinfra.com/meta-llama/Llama-3.3-70B-Instruct",
        notes="One of the cheapest 70B hosting options. Good for high-quality open-weight at scale.",
    ),
    ModelPricing(
        provider="deepinfra",
        model_id="deepseek-ai/DeepSeek-V3",
        input_mtok=0.14,
        output_mtok=0.28,
        context_window=163_840,
        free_tier="Trial API credits on signup",
        pricing_url="https://deepinfra.com/deepseek-ai/DeepSeek-V3",
        notes="DeepSeek-V3 on DeepInfra. Very cheap. Good general-purpose performance.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # AI21 LABS  (Jamba — hybrid SSM-Transformer architecture)
    # Source: https://www.ai21.com/pricing
    # Free tier: $10 in credits on signup; trial access to Jamba models
    # SSM (State Space Model) hybrid: faster, cheaper at long context vs pure Transformer
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="ai21",
        model_id="jamba-1.6-ultra",
        input_mtok=0.50,
        output_mtok=0.70,
        context_window=256_000,
        free_tier="$10 in API credits on signup",
        knowledge_cutoff="2024-06",
        pricing_url="https://www.ai21.com/pricing",
        notes=(
            "256K context SSM+Transformer hybrid. Excellent cost at long context due to SSM. "
            "Strong at RAG, summarisation, structured extraction. Enterprise-focused."
        ),
    ),
    ModelPricing(
        provider="ai21",
        model_id="jamba-1.6-mini",
        input_mtok=0.20,
        output_mtok=0.40,
        context_window=256_000,
        free_tier="$10 in API credits on signup",
        knowledge_cutoff="2024-06",
        pricing_url="https://www.ai21.com/pricing",
        notes=(
            "Smaller Jamba variant. Best value for long-context tasks. "
            "256K context with efficient SSM hybrid architecture."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # SAMBANOVA  (inference platform — Composition of Experts ultra-fast)
    # Source: https://cloud.sambanova.ai/apis
    # Free tier: free tier with rate limits at cloud.sambanova.ai
    # Note: SambaNova runs open-weight models on custom RDU wafer-scale chips
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="sambanova",
        model_id="Meta-Llama-3.3-70B-Instruct",
        input_mtok=0.60,
        output_mtok=0.60,
        context_window=131_072,
        inference_speed_tps=2200,
        free_tier="Free tier at cloud.sambanova.ai (rate-limited; no credit card required)",
        pricing_url="https://cloud.sambanova.ai/apis",
        notes=(
            "2,200 t/s — among the fastest 70B inference available. "
            "SambaNova RDU wafer-scale hardware. Flat $0.60/$0.60 pricing."
        ),
    ),
    ModelPricing(
        provider="sambanova",
        model_id="Qwen3-235B-A22B",
        input_mtok=1.30,
        output_mtok=1.30,
        context_window=131_072,
        inference_speed_tps=600,
        free_tier="Free tier at cloud.sambanova.ai (rate-limited)",
        supports_thinking=True,
        pricing_url="https://cloud.sambanova.ai/apis",
        notes=(
            "235B MoE on SambaNova RDU at ~600 t/s. "
            "Thinking mode supported. Flat input/output pricing."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # NVIDIA NIM  (inference microservices — GPU-optimised open models)
    # Source: https://build.nvidia.com/
    # Free tier: 1000 free API credits on signup; available at build.nvidia.com
    # OpenAI-compatible API; runs on A100/H100 fleets
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="nvidia",
        model_id="meta/llama-3.3-70b-instruct",
        input_mtok=0.23,
        output_mtok=0.42,
        context_window=131_072,
        free_tier="1000 API credits free on signup at build.nvidia.com",
        knowledge_cutoff="2023-12",
        pricing_url="https://build.nvidia.com/meta/llama-3_3-70b-instruct",
        notes=(
            "NVIDIA-optimised Llama 3.3 70B via NIM microservice. "
            "OpenAI-compatible API. Strong throughput on H100 clusters."
        ),
    ),
    ModelPricing(
        provider="nvidia",
        model_id="nvidia/llama-3.1-nemotron-ultra-253b-v1",
        input_mtok=0.55,
        output_mtok=0.55,
        context_window=131_072,
        free_tier="1000 API credits free on signup at build.nvidia.com",
        supports_thinking=True,
        pricing_url="https://build.nvidia.com/nvidia/llama-3_1-nemotron-ultra-253b-v1",
        notes=(
            "NVIDIA-tuned 253B Llama derivative. Thinking mode available. "
            "Strong coding and reasoning. Optimised for NVIDIA hardware."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # AZURE OPENAI
    # Pricing mirrors OpenAI direct. Value = drawing from Azure for Startups credits
    # instead of paying cash. Stronghold: ~$2.5K approved. BookCreator: applying.
    # litellm model prefix: "azure/<deployment-name>"
    # Important: reserve credit headroom for compute/storage infra, not just inference.
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="azure_openai",
        model_id="azure/gpt-4.1",
        input_mtok=2.00,
        output_mtok=8.00,
        context_window=1_047_576,
        free_tier="Covered by Azure for Startups credits (Tier 1: $1K; Tier 2: +$5K per entity)",
        knowledge_cutoff="2024-06",
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        notes=(
            "Same model as OpenAI gpt-4.1. Costs draw from Azure credits not cash. "
            "Deploy via Azure AI Studio. litellm: model='azure/YOUR_DEPLOYMENT_NAME'."
        ),
    ),
    ModelPricing(
        provider="azure_openai",
        model_id="azure/gpt-4o",
        input_mtok=2.50,
        output_mtok=10.00,
        context_window=128_000,
        free_tier="Covered by Azure for Startups credits",
        knowledge_cutoff="2023-10",
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        notes="Azure-hosted GPT-4o. Good for multimodal tasks on startup credits.",
    ),
    ModelPricing(
        provider="azure_openai",
        model_id="azure/o4-mini",
        input_mtok=1.10,
        output_mtok=4.40,
        context_window=200_000,
        free_tier="Covered by Azure for Startups credits",
        supports_thinking=True,
        knowledge_cutoff="2024-06",
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        notes="Best cost-effective reasoning model on Azure credits. 200K context.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # OPENROUTER  (aggregator — single key for 200+ models)
    # Source: https://openrouter.ai/docs
    # Free tier: small credit on signup + genuinely free $0/tok models
    # Useful for: fallback routing, model comparison, accessing free-tier models
    # litellm provider prefix: "openrouter/<provider>/<model>"
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="openrouter",
        model_id="openrouter/auto",
        input_mtok=0.00,  # routing meta-model; actual cost = underlying model price
        output_mtok=0.00,
        context_window=200_000,
        free_tier=(
            "Small free credit on signup + free $0 models (filter at openrouter.ai/models?q=free)"
        ),
        pricing_url="https://openrouter.ai/models",
        notes=(
            "Routes automatically to best available model. "
            "Input/output price = underlying model. Add ~5-10% OpenRouter markup. "
            "Free models include: Llama-3.1-8B, Gemma, Qwen, Mistral-7B variants. "
            "GET /api/v1/auth/key for rate-limit status. "
            "litellm: model='openrouter/anthropic/claude-opus-4-7' etc."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Programmatic price-refresh sources
# ---------------------------------------------------------------------------

PRICING_UPDATE_SOURCES: dict[str, str] = {
    # LiteLLM keeps a JSON file of every model's price + context window.
    # Updated with each litellm release — single best source for batch refresh.
    "litellm_model_db": (
        "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
    ),
    # OpenRouter public API — live pricing for every routed model.
    # GET /api/v1/models -> list[{id, pricing:{prompt, completion}, context_length}]
    "openrouter_api": "https://openrouter.ai/api/v1/models",
    # Provider-specific canonical pages
    "anthropic": "https://platform.claude.com/docs/en/docs/about-claude/models/overview",
    "openai": "https://openai.com/api/pricing/",
    "google": "https://ai.google.dev/gemini-api/docs/pricing",
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing/",
    "xai": "https://docs.x.ai/docs/models",
    "mistral": "https://mistral.ai/pricing",
    "cohere": "https://cohere.com/pricing",
    "perplexity": "https://docs.perplexity.ai/guides/pricing",
    "amazon": "https://aws.amazon.com/bedrock/pricing/",
    "microsoft": "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    "groq": "https://groq.com/pricing/",
    "fireworks": "https://fireworks.ai/pricing",
    "cloudflare": "https://developers.cloudflare.com/workers-ai/platform/pricing/",
    "together": "https://docs.together.ai/docs/serverless-models",
    "novita": "https://novita.ai/model-api/pricing",
    "cerebras": "https://cloud.cerebras.ai/platform/pricing",
    "azure_openai": "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "ai21": "https://www.ai21.com/pricing",
    "sambanova": "https://cloud.sambanova.ai/apis",
    "nvidia": "https://build.nvidia.com/",
    "moonshot": "https://platform.moonshot.ai/docs/pricing/chat",
    "minimax": "https://www.minimax.io/pricing",
    "zhipu": "https://open.bigmodel.cn/pricing",
    "huggingface": "https://huggingface.co/pricing",
    "deepinfra": "https://deepinfra.com/pricing",
}


# ---------------------------------------------------------------------------
# Startup / cloud credit programs
# ---------------------------------------------------------------------------
#
# Data as of May 2026.  Sources: learn.microsoft.com/en-us/startups, cloud.google.com/startup,
# aws.amazon.com/startups, cloudvisor.co/aws-activate-program, nvidia.com/en-us/startups.
#
# KEY for "funding_required":
#   False  = bootstrapped / no investor needed
#   "seed" = seed or later funding required (or accelerator)
#   "vc"   = VC-backed or invite-only referral
#
# NOTE: "Microsoft Founders Hub" was retired July 2, 2025. Two new tracks exist.

STARTUP_PROGRAMS: dict[str, dict] = {
    # ── Microsoft ─────────────────────────────────────────────────────────
    "microsoft_self_service": {
        "name": "Microsoft Azure Startup Credit (Self-Service)",
        "provider": "Microsoft / Azure",
        "credits_usd": 5_000,
        "credit_detail": "$1K immediately (valid 90 days) + up to $4K after business verification (valid 180 days)",
        "duration_note": "90 days / 180 days after each tranche",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Azure OpenAI Service (all models) + Azure AI Foundry covered",
        "other_perks": "GitHub Copilot can draw from Azure credits if Azure sub linked to GitHub",
        "url": "https://azure.microsoft.com/en-us/free/startups/",
        "docs_url": "https://learn.microsoft.com/en-us/startups/changes-microsoft-for-startups",
        "notes": (
            "Must be a new Azure customer with no prior Azure account. "
            "Signed in via personal MSA. Registered legal business, owns software product. "
            "Cannot be consultancy / agency / gov / edu / crypto. "
            "Stronghold: $1K approved (self-service track). BookCreator: applying. "
            "Both reaching full $5K = $10K combined near-term."
        ),
    },
    "microsoft_investor_offer": {
        "name": "Microsoft for Startups Investor Offer",
        "provider": "Microsoft / Azure",
        "credits_usd": 100_000,  # starting value; can go higher
        "credit_detail": "Starts at $100K; up to $150K+ depending on investor/cohort",
        "duration_note": "Varies by cohort and investor agreement",
        "funding_required": "vc",
        "multiple_entities_ok": False,
        "ai_inference_covered": True,
        "ai_detail": "Azure OpenAI + Azure AI Foundry + GPU VM access for AI workloads",
        "other_perks": (
            "GitHub Enterprise (20 users), M365 Business Premium (50 seats), "
            "Visual Studio Enterprise (5 users), Dynamics 365, Power Platform, "
            "Azure Standard Support, go-to-market co-selling"
        ),
        "url": "https://www.microsoft.com/en-us/startups",
        "docs_url": "https://learn.microsoft.com/en-us/microsoft-for-startups/benefits",
        "notes": "Requires referral code from VC/accelerator in Microsoft's Investor Network. Pre-Series C only.",
    },
    # ── Google ────────────────────────────────────────────────────────────
    "google_cloud_start": {
        "name": "Google for Startups Cloud Program — Start",
        "provider": "Google Cloud",
        "credits_usd": 2_000,
        "credit_detail": "$2,000 in Google Cloud credits",
        "duration_note": "1 year",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Vertex AI (Gemini), Google AI Studio",
        "other_perks": "$200 Google Cloud Skill Boost training credits",
        "url": "https://cloud.google.com/startup",
        "notes": "No institutional funding needed. Founded within last 5 years. No prior Google Cloud credits (beyond free trial).",
    },
    "google_cloud_scale_ai": {
        "name": "Google for Startups Cloud Program — Scale AI",
        "provider": "Google Cloud",
        "credits_usd": 350_000,
        "credit_detail": "Up to $250K Year 1 (100%) + up to $100K Year 2 (20% discount) = $350K over 2 years",
        "duration_note": "2 years",
        "funding_required": "seed",
        "multiple_entities_ok": False,
        "ai_inference_covered": True,
        "ai_detail": "Vertex AI + Gemini + Anthropic Claude (up to $10K partner credit) + Fireworks AI",
        "other_perks": "Dedicated Startup Success Manager, frontier model access, enablement resources",
        "url": "https://cloud.google.com/startup",
        "notes": "AI-first startup required. Seed to Series A (Series A must be within last 12 months). Founded within 10 years. Cap: not yet received $5K+ in Google Cloud credits.",
    },
    # ── AWS ───────────────────────────────────────────────────────────────
    "aws_activate_founders": {
        "name": "AWS Activate — Founders",
        "provider": "Amazon Web Services",
        "credits_usd": 1_000,
        "credit_detail": "$1,000 AWS credits + $350 Developer Support credits",
        "duration_note": "12 months",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Amazon Bedrock (Nova models, Claude, Llama, Mistral, Cohere via Bedrock)",
        "other_perks": "$350 AWS Developer Support",
        "url": "https://aws.amazon.com/activate/founders/",
        "notes": (
            "Self-funded / bootstrapped. No Activate Provider affiliation needed. "
            "New to Activate Credits (never received before). "
            "Each separate legal entity can apply independently."
        ),
    },
    "aws_activate_portfolio": {
        "name": "AWS Activate — Portfolio",
        "provider": "Amazon Web Services",
        "credits_usd": 100_000,
        "credit_detail": "Up to $100K credits; varies by Activate Provider (YC = $25K, others vary)",
        "duration_note": "12-24 months depending on provider",
        "funding_required": "seed",
        "multiple_entities_ok": False,
        "ai_inference_covered": True,
        "ai_detail": "Amazon Bedrock (same coverage as Founders, but higher limit)",
        "other_perks": "Up to $10,000 Business Support (24/7 cloud engineers)",
        "url": "https://aws.amazon.com/activate/",
        "notes": (
            "Must have Seed or Series A funding + valid Org ID from an Activate Provider. "
            "Apply within 12 months of most recent funding. Pre-Series B only. "
            "Cannot double-dip for same entity (can only upgrade, not re-apply for same amount)."
        ),
    },
    # ── NVIDIA ────────────────────────────────────────────────────────────
    "nvidia_inception": {
        "name": "NVIDIA Inception",
        "provider": "NVIDIA",
        "credits_usd": None,  # not publicly stated; disclosed after acceptance
        "credit_detail": "Free NIM API access for prototyping (rate-limited); partner discounts; credit amounts vary",
        "duration_note": "Ongoing membership (no fixed term)",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "NVIDIA NIM prototyping API (build.nvidia.com), DGX Cloud access (amount varies)",
        "other_perks": (
            "NVIDIA DLI free courses + discounted workshops, "
            "SDKs (CUDA, TensorRT, NeMo, Triton), co-marketing, "
            "Inception Capital Connect (VC introductions), global events"
        ),
        "url": "https://www.nvidia.com/en-us/startups/",
        "apply_url": "https://programs.nvidia.com/phoenix/application",
        "notes": (
            "Free to join. < 10 years old, at least one developer, incorporated, active website. "
            "Disqualifiers: consulting, crypto, cloud reseller, publicly traded. "
            "Two separate incorporated startups can each apply independently. "
            "Contact: inceptionprogram@nvidia.com for credit specifics."
        ),
    },
    # ── Cloudflare ────────────────────────────────────────────────────────
    "cloudflare_for_startups": {
        "name": "Cloudflare for Startups — Bootstrap",
        "provider": "Cloudflare",
        "credits_usd": 5_000,
        "credit_detail": "$5K Bootstrap (no investor); $25K Early Stage (<$1M raised); $100K Seed ($1-5M); $250K High Growth (Tier 1 VC)",
        "duration_note": "~12 months",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Workers AI (10K Neurons/day free for all; startup program expands quota), R2, Pages",
        "other_perks": "CDN, DDoS, DNS, Pages, Workers, R2 storage, Zero Trust, Cache Reserve (capped at $10K)",
        "url": "https://www.cloudflare.com/forstartups/",
        "notes": (
            "Bootstrap tier: no investor needed — bootstrapped/stealth, founded < 5 years, building software. "
            "Workers AI 10K Neurons/day is already free on all plans; program expands this. "
            "Multiple separate legal entities can each apply independently."
        ),
    },
    # ── OpenAI ────────────────────────────────────────────────────────────
    "openai_for_startups": {
        "name": "OpenAI for Startups — Direct Apply",
        "provider": "OpenAI",
        "credits_usd": 2_500,
        "credit_detail": "$2,500 API credits (direct); $100K+ with OpenAI partner VC referral",
        "duration_note": "Not publicly specified",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Full OpenAI API access (GPT-4.1, o3, o4-mini, Codex, etc.)",
        "other_perks": "Partner network introductions, early model access",
        "url": "https://openai.com/startups/",
        "notes": (
            "Direct apply (no investor): $2,500. < 5 years old from incorporation; "
            "functional product/prototype; formally incorporated (no sole proprietors); API meaningfully integrated. "
            "Partner VC referral path: $100K. OpenAI Grove cohort: $50K + 5-week mentorship (cohort-based, check for availability)."
        ),
    },
    # ── Anthropic ─────────────────────────────────────────────────────────
    "anthropic_for_startups": {
        "name": "Anthropic for Startups (Claude)",
        "provider": "Anthropic",
        "credits_usd": None,  # not publicly disclosed
        "credit_detail": "Undisclosed; priority rate limits + API credits + founder events",
        "duration_note": "Not publicly specified",
        "funding_required": "vc",  # requires Anthropic partner VC backing
        "multiple_entities_ok": False,
        "ai_inference_covered": True,
        "ai_detail": "Claude API (all models)",
        "other_perks": "Priority rate limits (highest published tier), Anthropic team office hours, exclusive events",
        "url": "https://claude.com/programs/startups",
        "notes": (
            "REQUIRES VC partner backing — no direct open-apply path. "
            "Must be backed by an Anthropic partner VC to receive a program link. "
            "Bootstrapped founders: standard API + pay-as-you-go; no startup credit program without VC partner."
        ),
    },
    # ── Mistral ───────────────────────────────────────────────────────────
    "mistralship": {
        "name": "Mistralship (Mistral AI startup program)",
        "provider": "Mistral AI",
        "credits_usd": 33_000,  # ~EUR 30K
        "credit_detail": "EUR 30,000 (~$33K USD) on La Plateforme",
        "duration_note": "~6 months (cohort-based)",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "La Plateforme API (all Mistral models — codestral, mistral-large, devstral, etc.)",
        "other_perks": "1-on-1 support from Mistral Solutions & Science team; early access to new models",
        "url": "https://mistral.ai/",
        "notes": (
            "Pre-Series B required (can be bootstrapped). Founded < 7 years. Business email + website. "
            "COHORT-BASED — check mistral.ai for current cohort status (Cohort 1 closed Jan 2025; Cohort 2 TBD). "
            "Separate from the already-generous free dev tier (2 RPM, 1B tokens/month)."
        ),
    },
    # ── GitHub ────────────────────────────────────────────────────────────
    "github_for_startups": {
        "name": "GitHub for Startups",
        "provider": "GitHub / Microsoft",
        "credits_usd": 10_000,
        "credit_detail": "$10,000 in GitHub platform credits (12 months)",
        "duration_note": "12 months",
        "funding_required": "seed",
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "GitHub Copilot (Business + premium models + agentic), 50K Actions minutes, Advanced Security",
        "other_perks": "GitHub Enterprise (20 seats), GitHub Actions credits, GitHub Packages, Advanced Security",
        "url": "https://github.com/enterprise/startups",
        "notes": (
            "Requires funding (Series B or earlier) OR GitHub for Startups partner affiliation. "
            "Covers GitHub Copilot Business licenses + premium models (Claude, GPT-4, etc.). "
            "Azure credits can also fund Copilot if Azure sub linked to GitHub. "
            "Apply via partner or email startups@github.com"
        ),
    },
    # ── Fireworks AI ──────────────────────────────────────────────────────
    "fireworks_for_startups": {
        "name": "Fireworks AI for Startups",
        "provider": "Fireworks AI",
        "credits_usd": 5_000,
        "credit_detail": "Up to $5,000 in Fireworks inference credits",
        "duration_note": "Not publicly specified",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Fireworks serverless inference (DeepSeek, Llama, Qwen, Mixtral, etc.)",
        "other_perks": "Higher rate limits, startup community access, product roadmap sessions, meetups/hackathons",
        "url": "https://fireworks.ai/startup-program",
        "notes": (
            "Review-based, no stated funding requirement. "
            "Positioned for AI builders needing fast reliable inference. "
            "Fireworks is particularly strong for DeepSeek-V4-Pro and open-weight models at scale."
        ),
    },
}


def startup_programs_table() -> str:
    """
    Markdown table of startup credit programs, sorted by credits (highest first).
    Includes only programs where funding_required=False (no investor needed).
    """
    no_funding = {k: v for k, v in STARTUP_PROGRAMS.items() if not v["funding_required"]}
    sorted_programs = sorted(
        no_funding.items(),
        key=lambda kv: kv[1]["credits_usd"] or 0,
        reverse=True,
    )

    rows = []
    for _, prog in sorted_programs:
        cred = f"${prog['credits_usd']:,}" if prog["credits_usd"] else "varies"
        ai = "yes" if prog["ai_inference_covered"] else "no"
        multi = "yes" if prog["multiple_entities_ok"] else "no"
        rows.append(
            f"| {prog['name'][:45]:<45} | {cred:>8} | {ai:^4} | {multi:^5} | {prog['url']} |"
        )

    header = (
        "### No-Funding-Required AI Cloud Startup Programs\n\n"
        "| Program                                       |  Credits | AI  | Multi | URL |\n"
        "|-----------------------------------------------|----------|-----|-------|-----|\n"
    )
    footer = (
        "\nAI = AI/LLM inference covered by credits\n"
        "Multi = multiple separate legal entities can each apply independently\n"
        "Data as of May 2026 — always verify at program URL before applying\n"
    )
    return header + "\n".join(rows) + "\n" + footer


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def get_model(model_id: str) -> ModelPricing | None:
    return next((m for m in MODELS if m.model_id == model_id), None)


def models_by_provider(provider: str) -> list[ModelPricing]:
    return [m for m in MODELS if m.provider == provider]


def cost_for_tokens(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    use_cache_read: bool = False,
) -> float | None:
    """Return total USD cost for a specific token usage on a given model."""
    m = get_model(model_id)
    if m is None:
        return None
    if use_cache_read and m.cache_read_mtok is not None:
        input_cost = m.cache_read_mtok * input_tokens / 1_000_000
    else:
        input_cost = m.input_mtok * input_tokens / 1_000_000
    return input_cost + m.output_mtok * output_tokens / 1_000_000


def fetch_openrouter_prices(timeout: int = 15) -> dict[str, dict]:
    """
    Fetch live model prices from the OpenRouter public API.

    Returns a dict keyed by model id (e.g. "anthropic/claude-sonnet-4-6").
    Each value contains at minimum "prompt" and "completion" prices as USD/token strings.

    No authentication required.  Source: https://openrouter.ai/api/v1/models

    Example:
        prices = fetch_openrouter_prices()
        claude = prices.get("anthropic/claude-sonnet-4-6")
        if claude:
            input_per_mtok = float(claude["prompt"]) * 1_000_000
    """
    url = PRICING_UPDATE_SOURCES["openrouter_api"]
    req = urllib.request.Request(url, headers={"User-Agent": "maistro-model-pricing/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return {m["id"]: m.get("pricing", {}) for m in data.get("data", [])}


def fetch_litellm_prices(timeout: int = 20) -> dict[str, dict]:
    """
    Fetch model prices from the LiteLLM model database (GitHub raw JSON).

    Returns the full dict keyed by model name.  Each entry includes:
      input_cost_per_token, output_cost_per_token, max_input_tokens,
      max_output_tokens, litellm_provider, and more.

    Updated with each LiteLLM release.
    Source: https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json

    Example:
        prices = fetch_litellm_prices()
        entry = prices.get("claude-sonnet-4-6")
        if entry:
            input_per_mtok = entry["input_cost_per_token"] * 1_000_000
    """
    url = PRICING_UPDATE_SOURCES["litellm_model_db"]
    req = urllib.request.Request(url, headers={"User-Agent": "maistro-model-pricing/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def price_diff_report(timeout: int = 15) -> str:
    """
    Compare MODELS list prices against live OpenRouter prices.
    Returns a Markdown report highlighting models where our stored price differs.
    """
    try:
        live = fetch_openrouter_prices(timeout=timeout)
    except Exception as exc:
        return f"Could not fetch OpenRouter prices: {exc}"

    lines = [
        "## Price freshness vs OpenRouter live API\n",
        "| Model | Stored In $/MTok | Live In $/MTok | Drift |\n",
        "|-------|-----------------|----------------|-------|\n",
    ]
    found_any = False
    for m in MODELS:
        # OpenRouter uses "provider/model" format; try a few key models
        or_key = f"{m.provider}/{m.model_id}".lower()
        entry = live.get(or_key)
        if entry is None:
            continue
        try:
            live_in = float(entry.get("prompt", 0)) * 1_000_000
        except (ValueError, TypeError):
            continue
        drift = ((live_in - m.input_mtok) / m.input_mtok * 100) if m.input_mtok else 0
        flag = " **STALE**" if abs(drift) > 10 else ""
        lines.append(
            f"| {m.model_id} | ${m.input_mtok:.4f} | ${live_in:.4f} | {drift:+.1f}%{flag} |\n"
        )
        found_any = True
    if not found_any:
        lines.append(
            "| (no matching models found — model IDs may differ from OpenRouter format) |\n"
        )
    return "".join(lines)


def benchmark_table() -> str:
    """
    Two Markdown tables of benchmark scores sorted by SWE-bench % (best first).
    Table 1: coding/agentic benchmarks. Table 2: general intelligence benchmarks.
    Only includes models with at least one benchmark score populated.
    """
    scored = [
        m
        for m in MODELS
        if any(
            [
                m.swe_bench_verified,
                m.terminal_bench,
                m.humaneval,
                m.live_code_bench,
                m.mmlu,
                m.gpqa_diamond,
                m.humanity_last_exam,
                m.arena_elo,
                m.bfcl,
                m.aime_2024,
            ]
        )
    ]
    scored.sort(key=lambda m: m.swe_bench_verified or 0, reverse=True)

    def f(v: float | None) -> str:
        return f"{v:.1f}%" if v is not None else "-"

    def fi(v: int | None) -> str:
        return str(v) if v is not None else "-"

    coding_rows = [
        f"| {m.provider:<14} | {m.model_id:<30} "
        f"| {f(m.swe_bench_verified):>11} "
        f"| {f(m.terminal_bench):>12} "
        f"| {f(m.humaneval):>10} "
        f"| {f(m.live_code_bench):>12} "
        f"| {f(m.bfcl):>9} |"
        for m in scored
    ]
    coding_header = (
        "### Coding & Agentic Benchmarks\n\n"
        "| Provider       | Model                          "
        "| SWE-bench % | Terminal-Bench | HumanEval% | LiveCodeBench |  BFCL % |\n"
        "|----------------|--------------------------------"
        "|-------------|----------------|------------|---------------|---------|\n"
    )

    intel_rows = [
        f"| {m.provider:<14} | {m.model_id:<30} "
        f"| {f(m.mmlu):>7} "
        f"| {f(m.gpqa_diamond):>12} "
        f"| {f(m.humanity_last_exam):>9} "
        f"| {f(m.aime_2024):>11} "
        f"| {fi(m.arena_elo):>9} "
        f"| {fi(m.intelligence_index):>8} |"
        for m in scored
    ]
    intel_header = (
        "\n### General Intelligence Benchmarks\n\n"
        "| Provider       | Model                          "
        "|    MMLU | GPQA Diamond |   HLE % |  AIME 2024 | Arena Elo | AI-Idx |\n"
        "|----------------|--------------------------------"
        "|---------|--------------|---------|------------|-----------|--------|\n"
    )

    footer = (
        "\nSWE-bench Verified: % of SWE-bench Verified issues resolved (swebench.com)\n"
        "Terminal-bench: terminal/shell task completion rate (agentic coding)\n"
        "HumanEval: classic pass@1 code generation benchmark\n"
        "LiveCodeBench: post-training-cutoff competitive coding problems\n"
        "BFCL: Berkeley Function Calling Leaderboard (gorilla.cs.berkeley.edu)\n"
        "MMLU: Massive Multitask Language Understanding (57 subjects)\n"
        "GPQA Diamond: PhD-level science Q&A (graduate-level)\n"
        "HLE: Humanity's Last Exam (hardest multi-discipline PhD-level exam)\n"
        "AIME 2024: American Invitational Math Exam 2024 (0-100 scale)\n"
        "Arena Elo: Chatbot Arena human preference ranking (lmarena.ai)\n"
        "AI-Idx: Artificial Analysis Intelligence Index v4 (artificialanalysis.ai)\n"
        "'-' = score not yet populated; contributions welcome\n"
    )
    return (
        coding_header
        + "\n".join(coding_rows)
        + intel_header
        + "\n".join(intel_rows)
        + "\n"
        + footer
    )


def limits_table() -> str:
    """
    Markdown table of rate limits sorted by provider.
    Shows free tier RPM/TPM and notes. Only models with free tier data shown.
    """
    has_data = [m for m in MODELS if m.free_tier is not None or m.free_tier_rpm is not None]
    has_data.sort(key=lambda m: (m.provider, m.model_id))

    def fi(v: int | None) -> str:
        return str(v) if v is not None else "?"

    rows = [
        f"| {m.provider:<14} | {m.model_id[:30]:<30} "
        f"| {fi(m.free_tier_rpm):>8} "
        f"| {fi(m.free_tier_tpm):>10} "
        f"| {(m.free_tier or '')[:60]:<60} |"
        for m in has_data
    ]
    header = (
        "| Provider       | Model                          "
        "| Free RPM | Free TPM  | Free Tier Description                                       |\n"
        "|----------------|--------------------------------"
        "|----------|-----------|-------------------------------------------------------------|\n"
    )
    footer = (
        "\n? = available but limit not confirmed; check provider console\n"
        "Rate limits change frequently — always verify at source before production use\n"
        "Groq limits source: https://console.groq.com/docs/rate-limits\n"
        "Perplexity limits source: https://docs.perplexity.ai/guides/rate-limits\n"
        "Google limits: personalized per project at aistudio.google.com/rate-limit\n"
        "Mistral limits: https://console.mistral.ai (account dashboard)\n"
    )
    return header + "\n".join(rows) + "\n" + footer


def comparison_table() -> str:
    """
    Markdown table sorted by input price (cheapest first).

    Columns:
      Provider | Model | In $/MTok | Out $/MTok | Context | Free Tier |
      SWE-bench % | Task cost* | Value†
    """
    rows = []
    for m in sorted(MODELS, key=lambda x: x.input_mtok):
        ctx = "1M" if m.context_window >= 1_000_000 else f"{m.context_window // 1_000}K"
        swe = f"{m.swe_bench_verified:.1f}%" if m.swe_bench_verified is not None else "-"
        task = f"${m.cost_per_typical_task_usd:.4f}"
        val = f"{m.swe_bench_per_dollar:.0f}" if m.swe_bench_per_dollar is not None else "-"
        free = "yes" if m.free_tier else "no"
        # Truncate long model IDs for table readability
        mid = m.model_id if len(m.model_id) <= 32 else m.model_id[:29] + "..."
        rows.append(
            f"| {m.provider:<14} | {mid:<32} | ${m.input_mtok:>7.4f} "
            f"| ${m.output_mtok:>8.4f} | {ctx:>7} | {free:^9} "
            f"| {swe:>11} | {task:>10} | {val:>7} |"
        )

    header = (
        "| Provider       | Model                            |  In $/MTok | Out $/MTok "
        "| Context | Free Tier | SWE-bench % |  Task cost* |  Value† |\n"
        "|----------------|----------------------------------|------------|------------"
        "|---------|-----------|-------------|-------------|--------|\n"
    )
    footer = (
        "\n*Typical task cost = 8K input + 2K output tokens\n"
        "†Value = SWE-bench % / typical task cost (higher = more coding power per $)\n"
        "SWE-bench: https://swebench.com (Verified subset unless noted)\n"
        "Intelligence Index: https://artificialanalysis.ai\n"
        f"Models listed: {len(MODELS)} across {len(PROVIDERS)} providers\n"
    )
    return header + "\n".join(rows) + "\n" + footer
