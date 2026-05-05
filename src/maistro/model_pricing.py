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

    # MATH-500 — % correct on 500 competition math problems (hendrycks/MATH subset)
    # Covers algebra, geometry, number theory, calculus. Lower ceiling than AIME.
    math_500: float | None = None

    # BigCodeBench — % pass@1 on 1140 real-world coding tasks using scientific/web libs
    # Harder than HumanEval; includes pandas, PIL, requests, scikit-learn, etc.
    bigcodebench: float | None = None

    # MMLU Pro — 10-choice version of MMLU; harder, better ceiling for frontier models
    # Source: tiger-lab.github.io/MMLU-Pro/  |  % correct across 12K questions
    mmlu_pro: float | None = None

    # IFEval — Instruction Following Eval; 541 verifiable instructions (strict prompt-level %)
    # Tests precise rule-following (word count, format, avoid X). Source: github.com/google-research/google-research/tree/master/instruction_following_eval
    ifeval: float | None = None

    # TAU-bench — Tool-Agent-User bench; agentic tool-use on realistic retail/airline APIs
    # % tasks fully completed end-to-end. Source: github.com/sierra-research/tau-bench
    tau_bench: float | None = None

    # MMMU — Massive Multitask Multimodal Understanding; vision+text across 11.5K questions
    # % correct; requires reasoning over images, charts, diagrams. Source: mmmu-benchmark.github.io
    mmmu: float | None = None

    # MathVista — visual math problems (charts, figures, geometry diagrams); % correct
    # Source: mathvista.github.io
    mathvista: float | None = None

    # SimpleQA — factual accuracy benchmark; 4326 short-answer questions; no abstaining allowed
    # Models that refuse or say "I don't know" score 0 on that question. Source: openai.com/index/introducing-simpleqa
    simple_qa: float | None = None

    # FRAMES — Factual Retrieval Across Multi-document Evaluation; long-context retrieval + synthesis
    # % correct; avg doc length 100K+ tokens. Source: research.google/blog/frames-benchmark
    frames: float | None = None

    # FrontierMath — Expert-level original math problems (post-cutoff, not on internet)
    # Only top frontier models score >2%. Source: epoch.ai/frontiermath
    frontier_math: float | None = None

    # OSWorld — Computer-use agent on real OS tasks (Windows/macOS/Ubuntu GUI automation)
    # % of tasks completed successfully. Source: os-world.github.io
    osworld: float | None = None

    # MGSM — Multilingual Grade School Math; mean % correct across 10 languages
    # Evaluates multilingual reasoning beyond English. Source: github.com/google-research/url-nlp/tree/main/mgsm
    mgsm: float | None = None

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
    # Upstage — Korean AI lab; Solar models benchmark extremely well per-dollar
    # Solar Pro is a 22B model competitive with much larger models on MMLU/MATH
    "upstage": {
        "name": "Upstage (Solar models — high benchmark efficiency per dollar)",
        "pricing_url": "https://console.upstage.ai/pricing",
        "api_docs_url": "https://developers.upstage.ai/docs/getting-started",
        "is_inference_platform": False,
        "notes": (
            "OpenAI-compatible API. Free $10 credit on signup. "
            "Solar Pro: strong math/reasoning performance vs 70B-class models. "
            "Document OCR/parsing also available (Solar OCR). "
        ),
    },
    # 01.AI — Yi series; Li Kai-Fu's lab; ultra-cheap inference, solid quality
    "01ai": {
        "name": "01.AI (Yi series — ultra-cheap, solid general-purpose)",
        "pricing_url": "https://platform.01.ai/pricing",
        "api_docs_url": "https://platform.01.ai/docs",
        "is_inference_platform": False,
        "notes": (
            "Yi-Lightning: $0.14/MTok flat in/out — one of cheapest mid-quality options. "
            "OpenAI-compatible API. Free trial credits on signup. "
            "Models available on OpenRouter: openrouter.ai/01-ai"
        ),
    },
    # LeptonAI — cheap inference platform; serverless open-weight hosting
    "lepton": {
        "name": "LeptonAI (inference platform — cheap serverless open-weight hosting)",
        "pricing_url": "https://www.lepton.ai/pricing",
        "api_docs_url": "https://www.lepton.ai/docs",
        "is_inference_platform": True,
        "notes": (
            "Serverless and dedicated GPU inference. "
            "Free $10 credit on signup. OpenAI-compatible API. "
            "Focuses on Llama, Mistral, Qwen open-weight models. Low cold-start latency."
        ),
    },
    # Baidu — ERNIE series; dominant Chinese LLM; strong on Chinese language tasks
    "baidu": {
        "name": "Baidu (ERNIE series — dominant Chinese frontier model)",
        "pricing_url": "https://qianfan.cloud.baidu.com/pricing",
        "api_docs_url": "https://cloud.baidu.com/doc/WENXINWORKSHOP/",
        "is_inference_platform": False,
        "notes": (
            "ERNIE 4.0 Turbo: strong Chinese-language, reasoning, and coding. "
            "Available via Baidu Qianfan platform. Free trial credits. "
            "Less accessible outside China; OpenRouter lists some ERNIE variants."
        ),
    },
    # Reka AI — multimodal frontier model lab; native video/image/audio understanding
    "reka": {
        "name": "Reka AI (multimodal frontier models — native video/image/audio)",
        "pricing_url": "https://platform.reka.ai/pricing",
        "api_docs_url": "https://docs.reka.ai/",
        "is_inference_platform": False,
        "notes": (
            "Reka Core, Flash, Edge family. Native multimodal (video, image, audio, text). "
            "Free trial credits on signup. OpenAI-compatible API. "
            "Strong at document understanding and long-video QA."
        ),
    },
    # Tencent — Hunyuan series; dominant Chinese frontier; strong coding + math + multilingual
    "tencent": {
        "name": "Tencent (Hunyuan series — Chinese frontier; strong multilingual + coding)",
        "pricing_url": "https://cloud.tencent.com/product/hunyuan",
        "api_docs_url": "https://cloud.tencent.com/document/product/1729",
        "is_inference_platform": False,
        "notes": (
            "Hunyuan-Large: 389B MoE, strong Chinese/multilingual. "
            "OpenAI-compatible API. Free trial credits on signup. "
            "Also available via OpenRouter: openrouter.ai/tencent"
        ),
    },
    # ByteDance — Doubao (Skylark) series; China's most-used LLM; strong on Chinese + coding
    "bytedance": {
        "name": "ByteDance (Doubao/Skylark — China's largest LLM deployment)",
        "pricing_url": "https://console.volcengine.com/ark/region:ark+cn-beijing/model",
        "api_docs_url": "https://www.volcengine.com/docs/82379/1182403",
        "is_inference_platform": False,
        "notes": (
            "Doubao is ByteDance's LLM brand (Volcano Engine platform). "
            "Ultra-cheap: among the lowest per-token prices of any frontier-quality model. "
            "Strong Chinese, coding, and instruction-following. "
            "OpenAI-compatible API. Free trial credits on signup."
        ),
    },
    # Hyperbolic — inference platform; cheap H100 GPU-backed inference for frontier + open models
    "hyperbolic": {
        "name": "Hyperbolic (inference platform — H100-backed; frontier + open-weight)",
        "pricing_url": "https://app.hyperbolic.xyz/models",
        "api_docs_url": "https://docs.hyperbolic.xyz/",
        "is_inference_platform": True,
        "notes": (
            "H100 GPU cluster. Hosts Meta Llama, DeepSeek, Qwen, Mistral, NovaSky. "
            "OpenAI-compatible API. Free $1 credit on signup. "
            "Batch API: 50% off standard rate."
        ),
    },
    # SiliconFlow — Chinese inference platform; ultra-cheap; 100+ models; OpenAI-compat
    "siliconflow": {
        "name": "SiliconFlow (inference platform — ultra-cheap; 100+ models; China-based)",
        "pricing_url": "https://siliconflow.cn/pricing",
        "api_docs_url": "https://docs.siliconflow.cn/",
        "is_inference_platform": True,
        "notes": (
            "Largest Chinese third-party inference platform. "
            "Hosts Qwen, DeepSeek, InternLM, Llama, Mistral variants at very low prices. "
            "Free tier: some models free with rate limits. OpenAI-compatible API. "
            "Also available on OpenRouter as proxy."
        ),
    },
    # InternLM / Shanghai AI Lab — strong STEM/coding; internationally competitive
    "internlm": {
        "name": "Shanghai AI Lab (InternLM series — strong STEM, coding, multilingual)",
        "pricing_url": "https://internlm.intern-ai.org.cn/",
        "api_docs_url": "https://internlm.intern-ai.org.cn/api/document",
        "is_inference_platform": False,
        "notes": (
            "InternLM 3 series: 8B and 70B instruction-tuned models. "
            "Strong on STEM, coding, and long-context Chinese tasks. "
            "Open-weight; also served cheaply via SiliconFlow. "
            "InternLM 2.5-VL: multimodal variant."
        ),
    },
    # Aleph Alpha — European AI lab; GDPR/data-sovereignty focus; on-prem option
    "aleph_alpha": {
        "name": "Aleph Alpha (European AI — GDPR/data-sovereignty; Pharia models)",
        "pricing_url": "https://www.aleph-alpha.com/pricing",
        "api_docs_url": "https://docs.aleph-alpha.com/",
        "is_inference_platform": False,
        "notes": (
            "Pharia-1 series (successor to Luminous). German-based; GDPR-compliant by design. "
            "On-premise deployment option for regulated industries. "
            "EU AI Act compliant. API + Python SDK available. "
            "Best choice when European data sovereignty is a hard requirement."
        ),
    },
    # nScale — UK GPU cloud; H100 clusters; serverless inference + bare-metal compute
    "nscale": {
        "name": "nScale (UK GPU cloud — H100 serverless inference + bare-metal)",
        "pricing_url": "https://nscale.com/pricing",
        "api_docs_url": "https://docs.nscale.com/",
        "is_inference_platform": True,
        "notes": (
            "UK-based H100 GPU cloud. Serverless LLM inference + dedicated GPU instances. "
            "OpenAI-compatible API. No egress fees. "
            "Good for European-region latency with GDPR data residency guarantees. "
            "Hosts Llama, Mistral, Qwen variants."
        ),
    },
    # Microsoft Phi — small models with outsized reasoning; phi-4 beats much larger models
    "phi": {
        "name": "Microsoft Phi (small reasoning models — phi-4 beats 70B+ on many tasks)",
        "pricing_url": "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        "api_docs_url": "https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models",
        "is_inference_platform": False,
        "notes": (
            "Phi-4 (14B): matches Llama-3 70B on many benchmarks at 5x lower cost. "
            "Phi-4-mini (3.8B): extraordinary for size — best-in-class small model reasoning. "
            "Available via Azure AI Foundry (startup-credit-eligible) or Ollama/local. "
            "OpenAI-compatible endpoint on Azure. Great for edge or cost-sensitive steps."
        ),
    },
    # TII UAE / Falcon — Falcon 3 series; multilingual; Arabic-first open weights
    "falcon_tii": {
        "name": "TII UAE (Falcon 3 series — multilingual; Arabic-first open weights)",
        "pricing_url": "https://huggingface.co/tiiuae",
        "api_docs_url": "https://huggingface.co/tiiuae",
        "is_inference_platform": False,
        "notes": (
            "Falcon 3 (1B, 3B, 7B, 10B, 40B) — Apache 2.0 license, fully open weights. "
            "Best Arabic-language performance among open models. Strong multilingual coverage. "
            "Served via Hyperbolic, Together AI, Hugging Face Inference Endpoints. "
            "No hosted API from TII directly; use inference platforms."
        ),
    },
    # Replicate — inference + fine-tuning platform; widely used by ML devs
    # Primary use: host custom fine-tuned LoRA models; run open-weight models via API
    "replicate": {
        "name": "Replicate (inference + fine-tuning platform — open-weight models)",
        "pricing_url": "https://replicate.com/pricing",
        "api_docs_url": "https://replicate.com/docs",
        "is_inference_platform": True,
        "notes": (
            "Per-GPU-second billing. ~$0.00115/s on H100. "
            "Fine-tune Flux/SDXL/Llama via API → deploy trained model to endpoint. "
            "Key for BookCreator: train LoRA per child character, host for inference. "
            "Python SDK: pip install replicate. Webhooks for async training completion."
        ),
    },
    # Modal — serverless GPU Python platform; deploy custom inference in pure Python
    "modal": {
        "name": "Modal (serverless GPU Python platform — custom inference deployment)",
        "pricing_url": "https://modal.com/pricing",
        "api_docs_url": "https://modal.com/docs",
        "is_inference_platform": True,
        "notes": (
            "Write Python functions, decorate with @modal.gpu('A100'), deploy instantly. "
            "Per-GPU-second billing: A10G $0.000306/s, A100 $0.00122/s, H100 $0.00195/s. "
            "Free tier: $30/mo included. No cold-start penalty — keep-warm option. "
            "Ideal for deploying custom fine-tuned models (e.g. per-child LoRA inference). "
            "Persistent volumes for weights storage. Cron + queue support built-in."
        ),
    },
    # IBM watsonx.ai — enterprise compliance, Granite series, EU/US data residency options
    "ibm_watsonx": {
        "name": "IBM watsonx.ai (Granite series — enterprise compliance, data residency)",
        "pricing_url": "https://www.ibm.com/products/watsonx-ai/pricing",
        "api_docs_url": "https://dataplatform.cloud.ibm.com/docs/content/wsj/analyze-data/fm-api.html",
        "is_inference_platform": False,
        "notes": (
            "Granite 3.3 Instruct (2B, 8B, 128K context) — Apache 2.0 open weights. "
            "FedRAMP authorized; HIPAA-eligible; SOC 2 Type II. "
            "EU/US data residency options. IBM Lite plan: 50K tokens/mo free. "
            "Strong for regulated industries (healthcare, finance, government)."
        ),
    },
    # Databricks — DBRX; enterprise data + ML platform; Mosaic ML acquisition
    "databricks": {
        "name": "Databricks (DBRX — enterprise data/ML; runs inside Databricks workspace)",
        "pricing_url": "https://www.databricks.com/product/pricing",
        "api_docs_url": "https://docs.databricks.com/en/machine-learning/foundation-models/index.html",
        "is_inference_platform": False,
        "notes": (
            "DBRX (132B MoE) + Meta Llama + Mistral via Foundation Model APIs. "
            "Billed in DBUs (Data Bundle Units) inside workspace — credit-based. "
            "Also serves Llama/Mistral at competitive rates via serving endpoints. "
            "Key advantage: models run inside your Databricks workspace (data never leaves). "
            "OpenAI-compatible endpoint available."
        ),
    },
    # Liquid AI — LFM (Liquid Foundation Models); efficient recurrent architecture
    "liquid_ai": {
        "name": "Liquid AI (LFM series — efficient recurrent architecture; smaller = fast)",
        "pricing_url": "https://www.liquid.ai/liquid-foundation-models",
        "api_docs_url": "https://docs.liquid.ai/",
        "is_inference_platform": False,
        "notes": (
            "Liquid Foundation Models (LFM): novel architecture (liquid time-constant networks). "
            "LFM-40B-MoE outperforms Llama 3.3 70B at 40% fewer active params. "
            "LFM-7B matches Llama 3 8B at higher throughput. "
            "Extremely memory-efficient — strong for edge/on-device. "
            "OpenAI-compatible API. Free tier credits on signup."
        ),
    },
    # Meta Llama API — Meta's official managed Llama inference endpoint (launched 2025)
    "llama_api": {
        "name": "Meta Llama API (official managed Llama inference — llama.developer.meta.com)",
        "pricing_url": "https://llama.developer.meta.com/docs/overview",
        "api_docs_url": "https://llama.developer.meta.com/docs/api",
        "is_inference_platform": False,
        "notes": (
            "Meta's own managed inference for Llama 3.3 70B and 3.1 405B. "
            "OpenAI-compatible API. Free trial tier available. "
            "Advantage: guaranteed to run the exact reference model implementation. "
            "Same Llama you'd self-host — no quantization, no provider variation."
        ),
    },
    # Voyage AI — best-in-class text and code embeddings for RAG pipelines
    "voyage_ai": {
        "name": "Voyage AI (embeddings — voyage-3 / voyage-code-3; best-in-class RAG)",
        "pricing_url": "https://docs.voyageai.com/docs/pricing",
        "api_docs_url": "https://docs.voyageai.com/",
        "is_inference_platform": False,
        "notes": (
            "voyage-3 consistently ranks #1 on MTEB embedding leaderboard. "
            "voyage-code-3: specialised for code retrieval (code search, autocomplete context). "
            "voyage-3-large: highest quality, 2x cost. voyage-3-lite: 10x cheaper for bulk. "
            "Input-only billing (no output tokens — embeddings are vectors). "
            "Reranker also available: voyage-rerank-2 ($0.05/1K queries)."
        ),
    },
    # LG AI Research — EXAONE 3.5; Korean frontier; strong coding and reasoning
    "exaone": {
        "name": "LG AI Research (EXAONE 3.5 — Korean frontier; strong coding + reasoning)",
        "pricing_url": "https://huggingface.co/LGAI-EXAONE",
        "api_docs_url": "https://huggingface.co/LGAI-EXAONE/EXAONE-3.5-32B-Instruct",
        "is_inference_platform": False,
        "notes": (
            "EXAONE 3.5 (2.4B, 7.8B, 32B) — Research license (non-commercial free, commercial via LG). "
            "Best Korean-language open model. Strong coding (HumanEval 80+%) and instruction following. "
            "Served via Together AI, SiliconFlow, and HuggingFace Inference Endpoints. "
            "Weights on HuggingFace. Contact LG AI Research for commercial licensing."
        ),
    },
    # AI71 — G42/MBZUAI Jais Arabic-English frontier models; best Arabic LLM available
    "ai71": {
        "name": "AI71 (Jais — G42/MBZUAI Arabic-English frontier; best Arabic open LLM)",
        "pricing_url": "https://ai71.ai/pricing",
        "api_docs_url": "https://docs.ai71.ai/",
        "is_inference_platform": False,
        "notes": (
            "Jais-30b-chat: best Arabic-English bilingual open LLM. Apache 2.0. "
            "Pre-trained on Arabic + English corpus (178B tokens Arabic). "
            "AI71 is the commercialisation arm of G42/MBZUAI (Abu Dhabi). "
            "OpenAI-compatible API. UAE data residency. "
            "Best choice for Arabic NLP — outperforms GPT-3.5 on Arabic benchmarks."
        ),
    },
    # Baseten — production model serving; truss framework; hot replicas; SLA-backed
    "baseten": {
        "name": "Baseten (model serving platform — truss framework; production SLAs)",
        "pricing_url": "https://www.baseten.co/pricing/",
        "api_docs_url": "https://docs.baseten.co/",
        "is_inference_platform": True,
        "notes": (
            "Deploy any model (HuggingFace, custom) with the Truss framework. "
            "Autoscaling + hot replicas (zero cold starts). Pay per compute-second. "
            "Pre-built deployments for Llama, Mistral, Whisper, Stable Diffusion. "
            "Stronger SLAs than Replicate — better for production API traffic. "
            "GPU options: A10G ($0.90/hr), A100 ($2.45/hr), H100 ($3.30/hr)."
        ),
    },
    # Snowflake Arctic — 480B dense MoE; open weights; SQL/data analytics focus
    "snowflake": {
        "name": "Snowflake (Arctic — 480B MoE; enterprise data/SQL focus; open weights)",
        "pricing_url": "https://www.together.ai/pricing",
        "api_docs_url": "https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions",
        "is_inference_platform": False,
        "notes": (
            "Arctic-Instruct: 480B parameter MoE (128 experts). Apache 2.0. "
            "Optimised for enterprise SQL, data analysis, and instruction-following on structured data. "
            "Hosted via Together AI and Snowflake Cortex (inside Snowflake platform). "
            "Not competitive with frontier models on creative/code — specialised for data workloads."
        ),
    },
    # Nebius AI — European inference cloud; cheapest EU-based open-weight hosting (H100)
    "nebius": {
        "name": "Nebius AI (EU inference cloud — cheapest EU H100 hosting for open weights)",
        "pricing_url": "https://nebius.com/prices",
        "api_docs_url": "https://nebius.com/docs/ai-studio",
        "is_inference_platform": True,
        "notes": (
            "Yandex-spun-off EU AI cloud (Amsterdam HQ, Netherlands data residency). "
            "30+ open-weight models from $0.01/MTok. H100 GPU cluster. "
            "OpenAI-compatible API. GDPR-compliant EU data processing. "
            "Best option for EU-region open-weight inference at lowest cost."
        ),
    },
    # Lambda Labs — GPU cloud; serverless LLM inference API + on-demand GPU instances
    "lambda_ai": {
        "name": "Lambda Labs (GPU cloud — serverless inference API + on-demand H100 instances)",
        "pricing_url": "https://lambdalabs.com/service/gpu-cloud",
        "api_docs_url": "https://docs.lambdalabs.com/inference/",
        "is_inference_platform": True,
        "notes": (
            "Lambda Inference API: 20+ LLMs from $0.015/MTok (Llama, Qwen, Hermes). "
            "Also GPU rental: H100 SXM5 $2.49/hr on-demand, 8x H100 $14.32/hr. "
            "OpenAI-compatible API. Free trial available. "
            "Strong for teams that need both managed inference and raw GPU access."
        ),
    },
    # Ollama — local inference runtime; run 100+ models fully offline on consumer hardware
    "ollama": {
        "name": "Ollama (local inference — run 100+ open models on consumer hardware for free)",
        "pricing_url": "https://ollama.com/library",
        "api_docs_url": "https://github.com/ollama/ollama/blob/main/docs/api.md",
        "is_inference_platform": True,
        "notes": (
            "Run Llama, Qwen, Mistral, Gemma, Phi, DeepSeek etc. locally — $0 inference cost. "
            "OpenAI-compatible REST API on localhost:11434. Single binary, auto-downloads model weights. "
            "GPU-accelerated on NVIDIA/AMD/Apple Silicon. No network latency, full data privacy. "
            "Ideal for dev/test without spending credits. Not suitable for production user-facing APIs."
        ),
    },
    # Alibaba DashScope — direct Qwen API from Alibaba; includes free qwen-flash tier
    "dashscope": {
        "name": "Alibaba DashScope (direct Qwen API — 34+ models; free flash tier)",
        "pricing_url": "https://help.aliyun.com/zh/dashscope/developer-reference/tongyi-qianwen-7b-14b-72b-metering-and-billing",
        "api_docs_url": "https://help.aliyun.com/zh/dashscope/",
        "is_inference_platform": False,
        "notes": (
            "Alibaba's official Qwen inference endpoint. 34+ models including Qwen3, QwQ. "
            "qwen-flash: free up to 1M tokens/day (rate-limited). "
            "OpenAI-compatible API via DashScope SDK or openai with base_url override. "
            "Requires Aliyun account (Alibaba Cloud). Primarily used for Chinese market."
        ),
    },
    # Allen Institute for AI — OLMo series; fully open (weights + data + code)
    "allenai": {
        "name": "Allen Institute for AI (OLMo — fully open models: weights + data + training code)",
        "pricing_url": "https://openrouter.ai/allenai",
        "api_docs_url": "https://huggingface.co/allenai",
        "is_inference_platform": False,
        "notes": (
            "OLMo (Open Language Model): fully transparent — weights, data, training code all Apache 2.0. "
            "OLMo-3.1-32B: competitive with Llama 3.3 70B on reasoning, best-in-class for research. "
            "OLMo 2 Think: reasoning variant with chain-of-thought. "
            "Served via OpenRouter. Ideal when full model provenance is required."
        ),
    },
    # Inflection AI — Pi model; conversational AI; emotional intelligence focus
    "inflection": {
        "name": "Inflection AI (Pi — emotionally intelligent conversational AI)",
        "pricing_url": "https://openrouter.ai/inflection",
        "api_docs_url": "https://developers.inflection.ai/",
        "is_inference_platform": False,
        "notes": (
            "Pi-3 (Productivity + Pi): conversational model tuned for helpfulness and EQ. "
            "Inflection-3-Productivity: business/work tasks. Inflection-3-Pi: personal AI companion. "
            "Available via OpenRouter. Not a coding-focused model — strong at nuanced dialogue. "
            "Higher price ($2.50/$10/MTok) reflects small market footprint."
        ),
    },
    # Arcee AI — distillation/compression specialists; efficient models via speculative decoding
    "arcee_ai": {
        "name": "Arcee AI (distillation specialists — efficient compressed models via speculative decoding)",
        "pricing_url": "https://openrouter.ai/arcee-ai",
        "api_docs_url": "https://docs.arcee.ai/",
        "is_inference_platform": False,
        "notes": (
            "Specialist in model distillation and merging. Trinity-mini: 7B model compressed from Llama-3 family. "
            "Maestro-reasoning: frontier reasoning at lower inference cost than o1-class. "
            "Arcee Spotlight: document understanding specialist. "
            "Models available via OpenRouter. Apache 2.0 weights on HuggingFace."
        ),
    },
    # Poolside AI — enterprise code generation; trained on proprietary code corpus
    "poolside": {
        "name": "Poolside AI (enterprise code generation — proprietary code corpus; free preview)",
        "pricing_url": "https://openrouter.ai/poolside",
        "api_docs_url": "https://www.poolside.ai/",
        "is_inference_platform": False,
        "notes": (
            "Laguna model family: trained on proprietary enterprise code corpus, not public GitHub. "
            "Free preview tier via OpenRouter (no cost during beta). "
            "Laguna-XS.2 and Laguna-M.1 both 131K context. "
            "Strong for enterprise codebases where models trained on public code underfit."
        ),
    },
    # StepFun AI — Chinese frontier; long context (262K); competitive coding + math
    "stepfun": {
        "name": "StepFun AI (Chinese frontier — 262K context; strong coding + math)",
        "pricing_url": "https://openrouter.ai/stepfun-ai",
        "api_docs_url": "https://platform.stepfun.com/docs",
        "is_inference_platform": False,
        "notes": (
            "Step series by StepFun (Kuaishou subsidiary). Step-3.5-Flash: 262K context at $0.10/$0.30. "
            "Strong on Chinese-language tasks, math, and code generation. "
            "Available via OpenRouter. OpenAI-compatible API on platform.stepfun.com. "
            "Free trial credits on signup."
        ),
    },
    # Xiaomi — MiMo math reasoning models; optimised for STEM
    "xiaomi": {
        "name": "Xiaomi (MiMo — math and STEM reasoning specialist; up to 1M context)",
        "pricing_url": "https://openrouter.ai/xiaomi",
        "api_docs_url": "https://github.com/XiaoMi/MiMo",
        "is_inference_platform": False,
        "notes": (
            "MiMo: Xiaomi's math-reasoning-optimised models. "
            "MiMo-v2.5: 1M context window; strong on AIME / competition math. "
            "MiMo-v2-Flash: fast 262K context at $0.09/$0.29. "
            "Available via OpenRouter. Open weights on HuggingFace (Apache 2.0)."
        ),
    },
    # Morph Labs — Fast Apply: code editing specialist; insert/replace diffs
    "morph": {
        "name": "Morph Labs (Fast Apply — code diff/edit specialist; not a general chat model)",
        "pricing_url": "https://openrouter.ai/morph",
        "api_docs_url": "https://morphlabs.ai/",
        "is_inference_platform": False,
        "notes": (
            "Morph Fast Apply: designed to apply code diffs/edits — not a general chat model. "
            "Takes (original file, edit instruction) and outputs the patched file. "
            "Morph-v3-Fast: $0.80/$1.20; Morph-v3-Large: $0.90/$1.90. Up to 262K context. "
            "Best-in-class for agentic coding pipelines that need to apply generated diffs reliably."
        ),
    },
    # Inclusion AI — Ling-2.6: 1 trillion parameter MoE; free public tier
    "inclusionai": {
        "name": "Inclusion AI (Ling-2.6 — 1T parameter MoE; free public tier)",
        "pricing_url": "https://openrouter.ai/inclusion-ai",
        "api_docs_url": "https://inclusionai.github.io/ling/",
        "is_inference_platform": False,
        "notes": (
            "Ling-2.6: 1 trillion parameter MoE model released by Inclusion AI (Chinese lab). "
            "Ling-2.6-1T: free via OpenRouter during public preview. 262K context. "
            "Ling-2.6-Flash: paid at $0.08/$0.24. Strong coding and reasoning. "
            "Open weights planned post-preview."
        ),
    },
    # ByteDance Seed — research lab wing of ByteDance; separate from Doubao/Skylark product
    "bytedance_seed": {
        "name": "ByteDance Seed (research models — separate from Doubao product line)",
        "pricing_url": "https://openrouter.ai/bytedance-research",
        "api_docs_url": "https://github.com/ByteDance-Seed",
        "is_inference_platform": False,
        "notes": (
            "ByteDance Seed is the research arm (not the Doubao product). "
            "Seed-1.6-Flash: ultra-fast 262K context at $0.075/$0.30. "
            "Seed-2.0-Mini: compact 262K context at $0.10/$0.40. "
            "Available via OpenRouter. Research-license weights; commercial use via ByteDance API."
        ),
    },
    # LlamaGate — inference platform; small 7-8B models only; very cheap; context ≤16K
    "llamagate": {
        "name": "LlamaGate (inference platform — 7-8B models only; ultra-cheap; 16K context max)",
        "pricing_url": "https://llamagate.com/pricing",
        "api_docs_url": "https://llamagate.com/docs",
        "is_inference_platform": True,
        "notes": (
            "Budget inference for 7-8B models: Llama 3.1/3.2, Qwen3, DeepSeek-R1 distill, Gemma3. "
            "From $0.03/MTok. Context capped at 16K — not suitable for long-document tasks. "
            "OpenAI-compatible API. Includes embeddings (nomic-embed) and vision (llava-7b, qwen3-vl). "
            "Best for: cheap high-volume batch tasks where 8B model quality is sufficient."
        ),
    },
    # Oracle Cloud Infrastructure (OCI) Generative AI — enterprise cloud; Llama + Cohere + Mistral
    "oci": {
        "name": "Oracle Cloud (OCI Generative AI — Llama, Cohere, Mistral; enterprise SLAs)",
        "pricing_url": "https://www.oracle.com/artificial-intelligence/generative-ai/pricing/",
        "api_docs_url": "https://docs.oracle.com/en-us/iaas/Content/generative-ai/overview.htm",
        "is_inference_platform": True,
        "notes": (
            "OCI Generative AI Service hosts Meta Llama 3.x, Cohere Command, Mistral. "
            "Flat per-token billing. Hosted in Oracle's FedRAMP-authorized regions (US, EU, AP). "
            "Strong for enterprises already in OCI (Oracle ERP/DB customers). "
            "Oracle for Startups program offers up to $300K in OCI credits. "
            "OpenAI-compatible via OCI SDK or direct REST. Requires OCI tenancy."
        ),
    },
    # OVH Cloud — French EU cloud; GDPR; competitive open-weight LLM hosting
    "ovhcloud": {
        "name": "OVH Cloud (EU inference — GDPR; French data residency; competitive open-weight pricing)",
        "pricing_url": "https://endpoints.ai.cloud.ovh.net/",
        "api_docs_url": "https://docs.ovh.com/gb/en/publiccloud/ai/",
        "is_inference_platform": True,
        "notes": (
            "OVH AI Endpoints: Llama, DeepSeek, Mistral hosted in French/EU datacenters. "
            "GDPR-compliant by design; data never leaves EU. "
            "DeepSeek-R1-Distill-Llama-70B: $0.67/MTok flat. Llama-3.1-8B: $0.10/MTok flat. "
            "OVH is Europe's largest independent cloud. OpenAI-compatible API. "
            "Good choice for EU-based applications requiring GDPR + cost efficiency."
        ),
    },
    # GitHub Copilot API — LLM access covered by GitHub Copilot subscription ($0 inference cost)
    "github_copilot": {
        "name": "GitHub Copilot API (GPT-4o/Claude/Gemini access covered by Copilot subscription)",
        "pricing_url": "https://github.com/features/copilot/plans",
        "api_docs_url": "https://docs.github.com/en/copilot/using-github-copilot/using-extensions-to-integrate-external-tools-with-copilot-chat",
        "is_inference_platform": True,
        "notes": (
            "GitHub Copilot Individual $10/mo or Business $19/user/mo. "
            "API access to 30+ models (GPT-4o, Claude, Gemini, o3) — all included in subscription. "
            "Per-token inference cost is $0 — covered by Copilot subscription. "
            "Azure subscription required; can draw from Azure startup credits. "
            "Useful: if team already has Copilot, use it for agentic tasks at no extra marginal cost."
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
    # ══════════════════════════════════════════════════════════════════════
    # OPENAI — additional models
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="openai",
        model_id="gpt-4.1-mini",
        input_mtok=0.40,
        output_mtok=1.60,
        cache_read_mtok=0.10,
        context_window=1_047_576,
        free_tier=None,
        swe_bench_verified=23.0,
        mmlu=85.0,
        knowledge_cutoff="2024-06",
        pricing_url="https://openai.com/api/pricing/",
        notes=(
            "Smarter and cheaper than gpt-4o-mini. ~1M context. "
            "Cached reads at $0.10/MTok. Best OpenAI value for general production use."
        ),
    ),
    ModelPricing(
        provider="openai",
        model_id="o1",
        input_mtok=15.00,
        output_mtok=60.00,
        cache_read_mtok=7.50,
        context_window=200_000,
        max_output=100_000,
        free_tier=None,
        swe_bench_verified=48.9,
        gpqa_diamond=78.0,
        aime_2024=83.3,
        math_500=96.4,
        supports_thinking=True,
        knowledge_cutoff="2023-10",
        pricing_url="https://openai.com/api/pricing/",
        notes=(
            "Full o1 reasoning model. Much more expensive than o4-mini but higher quality. "
            "Thinking tokens are billed. Cached reads at $7.50/MTok. "
            "Requires Tier 5 ($1K cumulative spend) for full access."
        ),
    ),
    ModelPricing(
        provider="openai",
        model_id="o1-mini",
        input_mtok=3.00,
        output_mtok=12.00,
        context_window=128_000,
        free_tier=None,
        aime_2024=56.7,
        supports_thinking=True,
        knowledge_cutoff="2023-10",
        pricing_url="https://openai.com/api/pricing/",
        notes="Smaller reasoning model. Good for math/coding reasoning without full o1 cost.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # xAI GROK — additional models
    # Source: https://docs.x.ai/docs/models
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="xai",
        model_id="grok-3",
        input_mtok=3.00,
        output_mtok=15.00,
        context_window=131_072,
        free_tier="Limited free credits for new accounts",
        mmlu=87.5,
        gpqa_diamond=84.4,
        humaneval=88.9,
        knowledge_cutoff="2025-03",
        pricing_url="https://docs.x.ai/docs/models",
        notes=(
            "Full Grok-3 without reasoning mode. "
            "Available via api.x.ai (OpenAI-compat) or OpenRouter. "
            "Strong coding and instruction following."
        ),
    ),
    ModelPricing(
        provider="xai",
        model_id="grok-3-mini",
        input_mtok=0.30,
        output_mtok=0.50,
        context_window=131_072,
        free_tier="Limited free credits for new accounts",
        gpqa_diamond=79.0,
        aime_2024=81.0,
        supports_thinking=True,
        knowledge_cutoff="2025-03",
        pricing_url="https://docs.x.ai/docs/models",
        notes=(
            "Compact reasoning model. Exceptional AIME/GPQA for price. "
            "Thinking mode on by default. Cheapest xAI option with CoT."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # COHERE — additional models
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="cohere",
        model_id="command-a",
        input_mtok=2.50,
        output_mtok=10.00,
        context_window=256_000,
        free_tier="Trial API key (non-commercial; rate-limited)",
        swe_bench_verified=60.1,
        knowledge_cutoff="2025-01",
        pricing_url="https://cohere.com/pricing",
        notes=(
            "Cohere's latest flagship command model. 256K context. "
            "Strong at enterprise RAG, tool use, structured outputs. "
            "Optimised for agentic pipelines."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # QWEN — additional models
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="qwen",
        model_id="qwen3-32b",
        input_mtok=0.30,
        output_mtok=1.20,
        context_window=131_072,
        free_tier="Alibaba Cloud free trial credits on signup",
        mmlu=86.0,
        gpqa_diamond=79.0,
        aime_2024=72.9,
        math_500=90.8,
        supports_thinking=True,
        knowledge_cutoff="2025-06",
        pricing_url="https://openrouter.ai/qwen/qwen3-32b",
        notes=(
            "32B dense model with thinking mode. Cheaper and faster than Qwen3-235B. "
            "Strong coding and math. Apache 2.0 open weights."
        ),
    ),
    ModelPricing(
        provider="qwen",
        model_id="qwen2.5-coder-32b-instruct",
        input_mtok=0.07,
        output_mtok=0.07,
        context_window=131_072,
        free_tier="Alibaba Cloud free trial credits on signup",
        humaneval=92.7,
        bigcodebench=55.7,
        live_code_bench=46.1,
        knowledge_cutoff="2024-10",
        pricing_url="https://openrouter.ai/qwen/qwen2.5-coder-32b-instruct",
        notes=(
            "Dedicated coding model. Exceptional HumanEval (92.7%). "
            "Very cheap at $0.07/$0.07 flat. Open weights (Apache 2.0). "
            "Good drop-in code completion model for agentic SWE pipelines."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # UPSTAGE  (Solar — high benchmark efficiency per dollar)
    # Source: https://console.upstage.ai/pricing
    # Free tier: $10 credit on signup; OpenAI-compatible API
    # Solar Pro: 22B model with benchmark scores rivalling 70B-class models
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="upstage",
        model_id="solar-pro",
        input_mtok=1.50,
        output_mtok=1.50,
        context_window=32_768,
        free_tier="$10 credit on signup at console.upstage.ai",
        mmlu=79.9,
        math_500=74.0,
        humaneval=86.8,
        knowledge_cutoff="2024-06",
        pricing_url="https://console.upstage.ai/pricing",
        notes=(
            "22B model with outsized benchmark performance for its size. "
            "Strong math/reasoning vs cost. OpenAI-compatible API. "
            "Shorter context (32K) — best for focused single-doc tasks."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # 01.AI  (Yi series — ultra-cheap, solid quality)
    # Source: https://platform.01.ai/pricing
    # Free tier: trial credits on signup; OpenAI-compatible API
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="01ai",
        model_id="yi-lightning",
        input_mtok=0.14,
        output_mtok=0.14,
        context_window=16_384,
        free_tier="Trial credits on signup at platform.01.ai",
        mmlu=77.0,
        knowledge_cutoff="2024-06",
        pricing_url="https://platform.01.ai/pricing",
        notes=(
            "Flat $0.14/$0.14 — one of cheapest capable mid-tier models. "
            "Good for classification, extraction, simple RAG. "
            "OpenAI-compatible. Also on OpenRouter: 01-ai/yi-lightning."
        ),
    ),
    ModelPricing(
        provider="01ai",
        model_id="yi-large",
        input_mtok=3.00,
        output_mtok=3.00,
        context_window=32_768,
        free_tier="Trial credits on signup at platform.01.ai",
        mmlu=82.0,
        knowledge_cutoff="2024-06",
        pricing_url="https://platform.01.ai/pricing",
        notes=(
            "Yi-Large flagship. Flat $3/$3. 200B-class quality. "
            "Strong multilingual (Chinese + English). 32K context."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # REKA AI  (multimodal frontier — native video/image/audio)
    # Source: https://platform.reka.ai
    # Free tier: trial credits on signup; OpenAI-compatible API
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="reka",
        model_id="reka-core",
        input_mtok=3.00,
        output_mtok=15.00,
        context_window=128_000,
        free_tier="Trial credits on signup at platform.reka.ai",
        mmlu=83.0,
        gpqa_diamond=53.0,
        knowledge_cutoff="2024-06",
        pricing_url="https://platform.reka.ai/pricing",
        notes=(
            "Reka's frontier model. Native multimodal: text, image, video, audio. "
            "128K context. Strong at long-video QA and document understanding. "
            "OpenAI-compatible API."
        ),
    ),
    ModelPricing(
        provider="reka",
        model_id="reka-flash",
        input_mtok=0.80,
        output_mtok=2.00,
        context_window=128_000,
        free_tier="Trial credits on signup at platform.reka.ai",
        knowledge_cutoff="2024-06",
        pricing_url="https://platform.reka.ai/pricing",
        notes="Mid-tier Reka. Cheaper multimodal inference. Good image/doc Q&A at lower cost.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # LEPTON AI  (inference platform — cheap serverless open-weight hosting)
    # Source: https://www.lepton.ai/pricing
    # Free tier: $10 credit on signup; OpenAI-compatible API
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="lepton",
        model_id="llama3-1-8b",
        input_mtok=0.07,
        output_mtok=0.07,
        context_window=128_000,
        free_tier="$10 credit on signup at lepton.ai",
        pricing_url="https://www.lepton.ai/pricing",
        notes="Cheap 8B inference on Lepton. Flat $0.07/$0.07. OpenAI-compatible.",
    ),
    ModelPricing(
        provider="lepton",
        model_id="llama3-1-70b",
        input_mtok=0.55,
        output_mtok=0.55,
        context_window=128_000,
        free_tier="$10 credit on signup at lepton.ai",
        pricing_url="https://www.lepton.ai/pricing",
        notes="70B on Lepton. Flat rate. Good for high-quality open-weight at mid-range cost.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # BAIDU  (ERNIE series — dominant Chinese LLM)
    # Source: https://qianfan.cloud.baidu.com/pricing
    # Free tier: trial credits on signup (Qianfan platform)
    # Note: less accessible outside China; some ERNIE variants on OpenRouter
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="baidu",
        model_id="ernie-4.0-turbo-128k",
        input_mtok=0.37,
        output_mtok=1.10,
        context_window=128_000,
        free_tier="Trial credits on signup at qianfan.cloud.baidu.com",
        mmlu=84.0,
        knowledge_cutoff="2024-06",
        pricing_url="https://qianfan.cloud.baidu.com/pricing",
        notes=(
            "ERNIE 4.0 Turbo — Baidu's fast flagship. Strong Chinese language + coding. "
            "128K context. Qianfan platform API. Restricted outside mainland China without VPN/proxy."
        ),
    ),
    ModelPricing(
        provider="baidu",
        model_id="ernie-speed-128k",
        input_mtok=0.004,
        output_mtok=0.008,
        context_window=128_000,
        free_tier="Free tier available on Qianfan with rate limits",
        knowledge_cutoff="2024-06",
        pricing_url="https://qianfan.cloud.baidu.com/pricing",
        notes=(
            "Baidu's cheapest Chinese-optimised model. Extremely cheap. "
            "Good for high-volume Chinese-language tasks. Free tier available."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # TENCENT HUNYUAN
    # Source: https://cloud.tencent.com/product/hunyuan
    # Free tier: trial credits on signup; also available via OpenRouter
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="tencent",
        model_id="hunyuan-large",
        input_mtok=0.18,
        output_mtok=0.18,
        context_window=256_000,
        mmlu=88.4,
        mmlu_pro=60.2,
        mgsm=89.1,
        free_tier="Trial credits on signup at cloud.tencent.com",
        knowledge_cutoff="2025-06",
        pricing_url="https://cloud.tencent.com/product/hunyuan",
        notes=(
            "389B MoE (52B active). Best Chinese multilingual model from Tencent. "
            "Strong math, coding, and long-context reasoning. 256K context. "
            "OpenAI-compatible API. Also routed via OpenRouter."
        ),
    ),
    ModelPricing(
        provider="tencent",
        model_id="hunyuan-turbo",
        input_mtok=0.14,
        output_mtok=0.14,
        context_window=128_000,
        free_tier="Trial credits on signup at cloud.tencent.com",
        knowledge_cutoff="2025-06",
        pricing_url="https://cloud.tencent.com/product/hunyuan",
        notes="Faster Hunyuan variant. Good balance of speed and quality for Chinese tasks.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # BYTEDANCE DOUBAO  (Volcano Engine platform)
    # Source: https://console.volcengine.com/ark
    # Among the cheapest frontier-quality models available; dominant in China
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="bytedance",
        model_id="doubao-pro-32k",
        input_mtok=0.11,
        output_mtok=0.11,
        context_window=32_000,
        mmlu=84.2,
        ifeval=86.5,
        free_tier="Trial credits on signup at console.volcengine.com",
        knowledge_cutoff="2025-06",
        pricing_url="https://console.volcengine.com/ark/region:ark+cn-beijing/model",
        notes=(
            "ByteDance flagship — strongest general quality. OpenAI-compatible API. "
            "Among cheapest frontier-quality options per token. Strong instruction-following."
        ),
    ),
    ModelPricing(
        provider="bytedance",
        model_id="doubao-lite-32k",
        input_mtok=0.04,
        output_mtok=0.04,
        context_window=32_000,
        free_tier="Trial credits on signup at console.volcengine.com",
        knowledge_cutoff="2025-06",
        pricing_url="https://console.volcengine.com/ark/region:ark+cn-beijing/model",
        notes="Ultra-cheap. Use for bulk Chinese-language tasks, classification, summarisation.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # HYPERBOLIC  (inference platform — H100 cluster)
    # Source: https://app.hyperbolic.xyz/models
    # OpenAI-compatible; $1 free credit on signup; batch 50% off
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="hyperbolic",
        model_id="meta-llama/Llama-3.3-70B-Instruct",
        input_mtok=0.20,
        output_mtok=0.20,
        context_window=128_000,
        mmlu=86.0,
        mmlu_pro=58.0,
        ifeval=83.4,
        mgsm=78.5,
        free_tier="$1 credit on signup",
        knowledge_cutoff="2024-12",
        pricing_url="https://app.hyperbolic.xyz/models",
        notes=(
            "Llama 3.3 70B on H100 cluster. Fast throughput, competitive pricing. "
            "Batch API at 50% off. OpenAI-compatible."
        ),
    ),
    ModelPricing(
        provider="hyperbolic",
        model_id="deepseek-ai/DeepSeek-V3",
        input_mtok=0.20,
        output_mtok=0.60,
        context_window=128_000,
        mmlu=88.5,
        mmlu_pro=75.9,
        ifeval=85.2,
        mgsm=91.0,
        free_tier="$1 credit on signup",
        knowledge_cutoff="2024-12",
        pricing_url="https://app.hyperbolic.xyz/models",
        notes="DeepSeek V3 on Hyperbolic H100s. Competitive pricing vs DeepSeek direct API.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # SILICONFLOW  (Chinese inference platform — ultra-cheap; 100+ models)
    # Source: https://siliconflow.cn/pricing
    # Free tier: several models permanently free; others very cheap
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="siliconflow",
        model_id="Qwen/Qwen2.5-72B-Instruct",
        input_mtok=0.13,
        output_mtok=0.13,
        context_window=131_072,
        mmlu=86.1,
        mmlu_pro=65.8,
        mgsm=85.0,
        free_tier="Some smaller models permanently free; $14 free credit on signup",
        knowledge_cutoff="2024-09",
        pricing_url="https://siliconflow.cn/pricing",
        notes=(
            "Qwen2.5 72B on SiliconFlow — cheapest available hosting for this model. "
            "OpenAI-compatible. Very popular for bulk Chinese + coding tasks."
        ),
    ),
    ModelPricing(
        provider="siliconflow",
        model_id="deepseek-ai/DeepSeek-V3",
        input_mtok=0.14,
        output_mtok=0.28,
        context_window=64_000,
        free_tier="Some smaller models permanently free",
        knowledge_cutoff="2024-12",
        pricing_url="https://siliconflow.cn/pricing",
        notes="DeepSeek V3 on SiliconFlow — among cheapest DeepSeek hosting options.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # SHANGHAI AI LAB  — InternLM 3 series
    # Source: https://internlm.intern-ai.org.cn/
    # Open weights; cheapest inference via SiliconFlow
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="internlm",
        model_id="internlm3-8b-instruct",
        input_mtok=0.05,
        output_mtok=0.10,
        context_window=32_000,
        mmlu=76.6,
        mmlu_pro=55.0,
        free_tier="Free via SiliconFlow free tier (rate-limited)",
        knowledge_cutoff="2024-09",
        pricing_url="https://siliconflow.cn/pricing",
        notes=(
            "8B instruction-tuned. Strong STEM and coding for its size. "
            "Self-hostable (Apache 2.0). Served cheaply via SiliconFlow."
        ),
    ),
    ModelPricing(
        provider="internlm",
        model_id="internlm3-20b-instruct",
        input_mtok=0.12,
        output_mtok=0.24,
        context_window=32_000,
        mmlu=82.4,
        mmlu_pro=62.0,
        knowledge_cutoff="2024-09",
        pricing_url="https://siliconflow.cn/pricing",
        notes=(
            "20B instruction-tuned. Competitive with Llama-3 70B on STEM/coding at lower cost. "
            "Strong Chinese + English bilingual. Available on SiliconFlow and HuggingFace."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # ALEPH ALPHA  — European GDPR-compliant frontier models
    # Source: https://www.aleph-alpha.com/
    # Pharia-1 family; on-prem option; EU data residency
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="aleph_alpha",
        model_id="pharia-1-llm-7b-control",
        input_mtok=0.20,
        output_mtok=0.20,
        context_window=4_096,
        supports_vision=False,
        knowledge_cutoff="2024-09",
        pricing_url="https://www.aleph-alpha.com/pricing",
        notes=(
            "7B GDPR-compliant model. EU data sovereignty guaranteed. "
            "On-prem deployment available for regulated industries (healthcare, finance, gov). "
            "EU AI Act compliant. Strong on structured data extraction and controlled generation. "
            "Context window is short (4K) — upgrade to larger Pharia variant for doc-level tasks."
        ),
    ),
    ModelPricing(
        provider="aleph_alpha",
        model_id="pharia-1-llm-7b-control-aligned",
        input_mtok=0.25,
        output_mtok=0.25,
        context_window=4_096,
        supports_vision=False,
        knowledge_cutoff="2024-09",
        pricing_url="https://www.aleph-alpha.com/pricing",
        notes=(
            "Aligned / safety-tuned variant. Extra RLHF for enterprise safety requirements. "
            "EU data residency. Best for customer-facing deployments requiring strict content control."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # NSCALE  (UK GPU cloud — H100 serverless inference)
    # Source: https://nscale.com/
    # European data residency; no egress fees; OpenAI-compatible
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="nscale",
        model_id="meta-llama/Llama-3.3-70B-Instruct",
        input_mtok=0.25,
        output_mtok=0.25,
        context_window=128_000,
        mmlu=86.0,
        ifeval=83.4,
        free_tier=None,
        knowledge_cutoff="2024-12",
        pricing_url="https://nscale.com/pricing",
        notes=(
            "Llama 3.3 70B on UK H100 cluster. European data residency. "
            "Good choice when GDPR + high throughput are both required. "
            "No egress fees. OpenAI-compatible."
        ),
    ),
    ModelPricing(
        provider="nscale",
        model_id="mistralai/Mistral-7B-Instruct-v0.3",
        input_mtok=0.07,
        output_mtok=0.07,
        context_window=32_768,
        free_tier=None,
        knowledge_cutoff="2024-03",
        pricing_url="https://nscale.com/pricing",
        notes="Cheapest nScale option. EU-hosted. Good for bulk classification / simple completion.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # MICROSOFT PHI  — small models with outsized benchmark performance
    # Source: https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/
    # Available via Azure AI Foundry (startup-credit-eligible) or local/Ollama
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="phi",
        model_id="microsoft/phi-4",
        input_mtok=0.07,
        output_mtok=0.14,
        context_window=16_384,
        mmlu=84.8,
        mmlu_pro=64.8,
        math_500=80.4,
        humaneval=82.6,
        mgsm=70.0,
        supports_vision=False,
        knowledge_cutoff="2024-06",
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        notes=(
            "14B dense. Matches Llama-3 70B on MMLU at 1/5th the inference cost. "
            "Exceptional for its size on reasoning and coding. "
            "Available via Azure AI Foundry (startup credits apply). "
            "Also runs locally: ollama run phi4"
        ),
    ),
    ModelPricing(
        provider="phi",
        model_id="microsoft/phi-4-mini",
        input_mtok=0.025,
        output_mtok=0.05,
        context_window=16_384,
        mmlu=72.4,
        mmlu_pro=51.0,
        humaneval=74.4,
        supports_vision=False,
        knowledge_cutoff="2024-06",
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        notes=(
            "3.8B — extraordinary reasoning for its size. Best small model for edge/mobile. "
            "Cheaper than most embedding APIs. Runs on CPU. "
            "Azure AI Foundry serverless: startup credits eligible."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # TII UAE — Falcon 3 series  (Arabic-first open weights; Apache 2.0)
    # Source: https://huggingface.co/tiiuae
    # Priced via inference providers (Together AI, Hyperbolic, HF Endpoints)
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="falcon_tii",
        model_id="tiiuae/falcon3-10b-instruct",
        input_mtok=0.08,
        output_mtok=0.08,
        context_window=32_768,
        mmlu=73.9,
        ifeval=72.0,
        supports_vision=False,
        knowledge_cutoff="2024-09",
        pricing_url="https://www.together.ai/pricing",
        notes=(
            "10B instruction-tuned. Apache 2.0. Best open-weight Arabic-language model. "
            "Strong multilingual (Arabic, French, Spanish, German). "
            "Priced via Together AI. Download weights freely from HuggingFace."
        ),
    ),
    ModelPricing(
        provider="falcon_tii",
        model_id="tiiuae/falcon3-40b-instruct",
        input_mtok=0.25,
        output_mtok=0.25,
        context_window=32_768,
        mmlu=81.2,
        ifeval=79.0,
        supports_vision=False,
        knowledge_cutoff="2024-09",
        pricing_url="https://www.together.ai/pricing",
        notes=(
            "40B instruction-tuned. Competitive with Llama-3 70B on multilingual tasks. "
            "Best choice for Arabic-heavy deployments. Apache 2.0 — fully open. "
            "Available via Together AI and Hyperbolic."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # SNOWFLAKE ARCTIC  — 480B MoE; data/SQL focus; Snowflake Cortex
    # Source: https://www.together.ai/pricing (primary inference host)
    # Snowflake Cortex: SQL UDF access inside Snowflake warehouses
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="snowflake",
        model_id="snowflake/snowflake-arctic-instruct",
        input_mtok=0.30,
        output_mtok=0.30,
        context_window=4_096,
        mmlu=67.3,
        supports_vision=False,
        knowledge_cutoff="2024-04",
        pricing_url="https://www.together.ai/pricing",
        notes=(
            "480B dense-MoE (128 experts; 17B active). Apache 2.0. "
            "NOT competitive on general benchmarks — purpose-built for enterprise SQL/data tasks. "
            "Key differentiator: native Snowflake Cortex integration (call as SQL UDF). "
            "Self-serve via Together AI. Very short context (4K) limits document-level use."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # REPLICATE  — per-GPU-second billing; best LoRA/fine-tune API ecosystem
    # signup: replicate.com  |  api_key_env: REPLICATE_API_TOKEN
    # Key for BookCreator: train LoRA → host endpoint → inference per child
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="replicate",
        model_id="meta/meta-llama-3-3-70b-instruct",
        input_mtok=0.23,  # effective rate at ~$0.00115/s H100; varies with length
        output_mtok=0.23,
        context_window=128_000,
        mmlu=86.0,
        mmlu_pro=58.0,
        ifeval=83.4,
        free_tier="Free for cold-start public models (slow queue)",
        knowledge_cutoff="2024-12",
        pricing_url="https://replicate.com/pricing",
        notes=(
            "Per-GPU-second billing (~$0.00115/s on H100); effective rate varies with length. "
            "Use Replicate for fine-tuning (fast-flux-trainer, ostris/flux-dev-lora-trainer). "
            "Trained LoRA weights stay on Replicate — serve at same per-second rate."
        ),
    ),
    ModelPricing(
        provider="replicate",
        model_id="mistralai/mixtral-8x7b-instruct-v0.1",
        input_mtok=0.30,
        output_mtok=1.00,
        context_window=32_768,
        mmlu=71.2,
        knowledge_cutoff="2024-01",
        pricing_url="https://replicate.com/pricing",
        notes="Mixtral 8x7B on Replicate. Cheaper than 70B for bulk tasks. Fast on A40.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # MODAL  — serverless GPU Python; deploy custom fine-tuned models
    # signup: modal.com  |  sdk: pip install modal  |  Free $30/mo included
    # Ideal for: hosting per-child LoRA inference endpoint, batch upscaling
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="modal",
        model_id="custom/llama-3-3-70b-instruct-a100",
        input_mtok=0.40,  # A100 $0.00122/s; ~300 tok/s; ~$0.40/MTok effective
        output_mtok=0.40,
        context_window=128_000,
        free_tier="$30/mo free compute included (no credit card for first 30 days)",
        knowledge_cutoff="2024-12",
        pricing_url="https://modal.com/pricing",
        notes=(
            "Self-deployed Llama 3.3 70B on Modal A100 ($0.00122/s). "
            "Effective rate ~$0.40/MTok at ~300 tok/s. "
            "Deploy with @modal.gpu('A100-40GB') decorator — pure Python, no k8s. "
            "Keep-warm option: pay $0.00122/s idle to eliminate cold starts. "
            "H100 option: $0.00195/s (~2x throughput)."
        ),
    ),
    ModelPricing(
        provider="modal",
        model_id="custom/sdxl-lora-inference-a10g",
        input_mtok=0.0,  # image gen workload — not token-based; see image_gen_pricing.py
        output_mtok=0.0,
        context_window=0,
        free_tier="$30/mo free compute included",
        pricing_url="https://modal.com/pricing",
        notes=(
            "SDXL + LoRA image gen on Modal A10G ($0.000306/s). "
            "~$0.001/image effective (~0.3 img/s on A10G). "
            "Keep custom LoRA weights on Modal Volume — instant swap per child character. "
            "See image_gen_pricing.py for full image gen cost analysis."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # IBM WATSONX.AI  — Granite 3.3 series; enterprise compliance
    # signup: ibm.com/watsonx  |  sdk: pip install ibm-watsonx-ai
    # FedRAMP, HIPAA, SOC 2 — best for regulated industry deployments
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="ibm_watsonx",
        model_id="ibm/granite-3-3-8b-instruct",
        input_mtok=0.60,
        output_mtok=1.80,
        context_window=128_000,
        mmlu=73.2,
        mmlu_pro=52.0,
        ifeval=78.0,
        humaneval=68.0,
        supports_vision=False,
        free_tier="Lite plan: 50K tokens/month free",
        knowledge_cutoff="2025-03",
        pricing_url="https://www.ibm.com/products/watsonx-ai/pricing",
        notes=(
            "128K context. Apache 2.0 open weights. FedRAMP authorized; HIPAA-eligible; SOC 2. "
            "EU/US data residency options. Granite 3.3 series is IBM's best instruction-tuned family. "
            "Strongest choice when regulatory compliance is a hard requirement."
        ),
    ),
    ModelPricing(
        provider="ibm_watsonx",
        model_id="ibm/granite-3-3-2b-instruct",
        input_mtok=0.20,
        output_mtok=0.60,
        context_window=128_000,
        mmlu=62.5,
        supports_vision=False,
        free_tier="Lite plan: 50K tokens/month free",
        knowledge_cutoff="2025-03",
        pricing_url="https://www.ibm.com/products/watsonx-ai/pricing",
        notes=(
            "2B variant. Extremely cheap for classification + extraction pipelines. "
            "Apache 2.0. Same compliance posture as 8B. Run locally or on watsonx. "
            "Useful for high-volume document processing in regulated environments."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # DATABRICKS  — DBRX + Foundation Model APIs; runs inside Databricks workspace
    # signup: databricks.com  |  sdk: openai (compat) or databricks-sdk
    # Key advantage: models run inside your Databricks workspace (data sovereignty)
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="databricks",
        model_id="databricks/dbrx-instruct",
        input_mtok=0.60,
        output_mtok=0.60,
        context_window=32_768,
        mmlu=73.7,
        mmlu_pro=52.0,
        humaneval=70.1,
        mgsm=66.0,
        supports_vision=False,
        free_tier=None,
        knowledge_cutoff="2023-12",
        pricing_url="https://www.databricks.com/product/pricing/foundation-model-serving",
        notes=(
            "132B MoE (36B active). Priced ~$0.60/MTok via Databricks Foundation Model API. "
            "Also available on Together AI at same rate. "
            "Key: if your data is already in Databricks, DBRX avoids data-leaving-warehouse risk. "
            "Apache 2.0 open weights."
        ),
    ),
    ModelPricing(
        provider="databricks",
        model_id="meta-llama/llama-3-3-70b-instruct",
        input_mtok=0.30,
        output_mtok=0.30,
        context_window=128_000,
        mmlu=86.0,
        ifeval=83.4,
        free_tier=None,
        knowledge_cutoff="2024-12",
        pricing_url="https://www.databricks.com/product/pricing/foundation-model-serving",
        notes=(
            "Llama 3.3 70B via Databricks Foundation Model API. "
            "Competitive pricing; stays within Databricks workspace security perimeter. "
            "Good option if already paying for Databricks for data engineering."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # LIQUID AI  — LFM series; novel recurrent architecture; memory-efficient
    # signup: liquid.ai  |  api_key_env: LIQUID_API_KEY
    # LFMs use liquid time-constant networks — different compute profile than Transformers
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="liquid_ai",
        model_id="liquid/lfm-40b",
        input_mtok=0.50,
        output_mtok=1.50,
        context_window=32_768,
        mmlu=80.4,
        mmlu_pro=60.0,
        ifeval=82.0,
        free_tier="Trial credits on signup at liquid.ai",
        knowledge_cutoff="2024-09",
        pricing_url="https://www.liquid.ai/liquid-foundation-models",
        notes=(
            "40B MoE parameters. Outperforms Llama 3.3 70B at 40% fewer active params. "
            "Novel architecture: liquid time-constant (LTC) recurrent networks. "
            "Dramatically lower memory bandwidth vs Transformers of equivalent quality. "
            "Strong on long sequences where quadratic attention cost hurts other models."
        ),
    ),
    ModelPricing(
        provider="liquid_ai",
        model_id="liquid/lfm-7b",
        input_mtok=0.10,
        output_mtok=0.30,
        context_window=32_768,
        mmlu=68.5,
        mmlu_pro=48.0,
        free_tier="Trial credits on signup at liquid.ai",
        knowledge_cutoff="2024-09",
        pricing_url="https://www.liquid.ai/liquid-foundation-models",
        notes=(
            "7B LFM. Competitive with Llama 3 8B at higher throughput and lower memory. "
            "Good for edge/on-device deployment (very memory-efficient). "
            "Run locally or via Liquid AI API."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # META LLAMA API  — Meta's official managed Llama inference (launched 2025)
    # signup: llama.developer.meta.com  |  api_key_env: LLAMA_API_KEY
    # Reference implementation — guaranteed exact model, no quantization variance
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="llama_api",
        model_id="meta-llama/Llama-3.3-70B-Instruct",
        input_mtok=0.20,
        output_mtok=0.20,
        context_window=128_000,
        mmlu=86.0,
        mmlu_pro=58.0,
        ifeval=83.4,
        mgsm=78.5,
        free_tier="Free tier: limited daily tokens for testing",
        knowledge_cutoff="2024-12",
        pricing_url="https://llama.developer.meta.com/docs/overview",
        notes=(
            "Official Meta-hosted Llama. Guaranteed reference implementation — no quantization, "
            "no provider variation. Useful for eval baselines and compliance scenarios. "
            "OpenAI-compatible API. Pricing competitive with top inference providers."
        ),
    ),
    ModelPricing(
        provider="llama_api",
        model_id="meta-llama/Llama-3.1-405B-Instruct",
        input_mtok=0.80,
        output_mtok=0.80,
        context_window=131_072,
        mmlu=88.6,
        mmlu_pro=73.0,
        ifeval=88.0,
        mgsm=89.0,
        free_tier=None,
        knowledge_cutoff="2024-07",
        pricing_url="https://llama.developer.meta.com/docs/overview",
        notes=(
            "Largest publicly available Llama. 405B dense. "
            "Best open-weight model for complex reasoning and long-context synthesis. "
            "Official Meta endpoint. Also available via Together AI, Hyperbolic, Replicate."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # VOYAGE AI  — text + code embeddings; #1 on MTEB leaderboard
    # signup: voyageai.com  |  api_key_env: VOYAGE_API_KEY
    # IMPORTANT: embeddings only — no output tokens; input_mtok = embedding cost
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="voyage_ai",
        model_id="voyage-3",
        input_mtok=0.06,  # cost per 1M input tokens to embed; output = vector, not tokens
        output_mtok=0.0,
        context_window=32_000,
        supports_vision=False,
        supports_tool_use=False,
        knowledge_cutoff="2024-06",
        pricing_url="https://docs.voyageai.com/docs/pricing",
        notes=(
            "EMBEDDINGS MODEL — input_mtok is embedding cost; there are no output tokens. "
            "#1 on MTEB retrieval leaderboard. 1024-dim vectors. "
            "Best for RAG pipelines: document chunking → embed → vector search → LLM context. "
            "voyage-3-lite: $0.02/MTok (10x cheaper; marginal quality loss for bulk use). "
            "voyage-3-large: $0.18/MTok (highest quality). "
            "Reranker: voyage-rerank-2 at $0.05/1K queries."
        ),
    ),
    ModelPricing(
        provider="voyage_ai",
        model_id="voyage-code-3",
        input_mtok=0.06,
        output_mtok=0.0,
        context_window=32_000,
        supports_vision=False,
        supports_tool_use=False,
        knowledge_cutoff="2024-06",
        pricing_url="https://docs.voyageai.com/docs/pricing",
        notes=(
            "EMBEDDINGS MODEL — specialised for code search and code context retrieval. "
            "#1 on code retrieval benchmarks. Understands code structure beyond token overlap. "
            "Use in IDE autocomplete context pipelines, code search, issue→PR matching. "
            "Same $0.06/MTok as voyage-3."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # LG AI RESEARCH  — EXAONE 3.5 series; Korean frontier; Apache-adjacent license
    # signup: no direct API — served via Together AI, SiliconFlow, HF Endpoints
    # Best Korean-language open model; strong coding; research license
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="exaone",
        model_id="LGAI-EXAONE/EXAONE-3.5-32B-Instruct",
        input_mtok=0.25,
        output_mtok=0.25,
        context_window=32_768,
        mmlu=82.9,
        mmlu_pro=61.0,
        humaneval=80.2,
        ifeval=80.0,
        supports_vision=False,
        knowledge_cutoff="2024-12",
        pricing_url="https://www.together.ai/pricing",
        notes=(
            "32B instruction-tuned. Best Korean-language open model. "
            "HumanEval 80.2% — competitive with Llama 3.3 70B on coding. "
            "Research license: free non-commercial; commercial use requires LG agreement. "
            "Served via Together AI. Weights on HuggingFace."
        ),
    ),
    ModelPricing(
        provider="exaone",
        model_id="LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct",
        input_mtok=0.08,
        output_mtok=0.08,
        context_window=32_768,
        mmlu=75.1,
        humaneval=70.8,
        supports_vision=False,
        knowledge_cutoff="2024-12",
        pricing_url="https://siliconflow.cn/pricing",
        notes=(
            "7.8B instruction-tuned. Strong Korean + English bilingual. "
            "Cheapest EXAONE variant. Via SiliconFlow or HuggingFace Inference Endpoints. "
            "Research license (non-commercial free)."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # AI71 / JAIS  — G42 + MBZUAI Arabic-English frontier; best Arabic open LLM
    # signup: ai71.ai  |  api_key_env: AI71_API_KEY
    # Apache 2.0; UAE data residency; outperforms GPT-3.5 on Arabic benchmarks
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="ai71",
        model_id="tiiuae/jais-30b-chat",
        input_mtok=0.60,
        output_mtok=0.60,
        context_window=8_192,
        mmlu=70.8,  # English; Arabic MMLU higher (Arabic-native)
        supports_vision=False,
        knowledge_cutoff="2023-09",
        pricing_url="https://ai71.ai/pricing",
        notes=(
            "30B Arabic-English bilingual. Apache 2.0. "
            "Best Arabic-language open model — trained on 178B Arabic tokens. "
            "Outperforms GPT-3.5 on Arabic NLP benchmarks. "
            "AI71 API: OpenAI-compatible. UAE data residency. "
            "Also available via HuggingFace. Context is limited (8K) — consider chunking."
        ),
    ),
    ModelPricing(
        provider="ai71",
        model_id="tiiuae/jais-13b-chat",
        input_mtok=0.25,
        output_mtok=0.25,
        context_window=8_192,
        supports_vision=False,
        knowledge_cutoff="2023-09",
        pricing_url="https://ai71.ai/pricing",
        notes="13B Arabic-English. Cheaper than 30B. Good for bulk Arabic classification/summarisation.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # BASETEN  — production model serving; truss framework; hot replicas
    # signup: baseten.co  |  sdk: pip install baseten
    # Better SLAs than Replicate; good for production API traffic
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="baseten",
        model_id="llama-3-3-70b-instruct-a100",
        input_mtok=0.35,  # A100 $2.45/hr; ~280 tok/s; ~$0.35/MTok effective
        output_mtok=0.35,
        context_window=128_000,
        mmlu=86.0,
        free_tier=None,
        knowledge_cutoff="2024-12",
        pricing_url="https://www.baseten.co/pricing/",
        notes=(
            "Llama 3.3 70B deployed on Baseten A100 ($2.45/hr). "
            "Effective rate ~$0.35/MTok at ~280 tok/s. "
            "Hot replicas: zero cold start for production traffic. "
            "Truss framework: deploy any custom fine-tuned model in minutes. "
            "Better latency SLA than Replicate for production APIs."
        ),
    ),
    ModelPricing(
        provider="baseten",
        model_id="whisper-large-v3-a10g",
        input_mtok=0.0,  # audio transcription — price is per audio minute, not tokens
        output_mtok=0.0,
        context_window=0,
        supports_vision=False,
        supports_tool_use=False,
        pricing_url="https://www.baseten.co/pricing/",
        notes=(
            "Whisper large-v3 on Baseten A10G. ~$0.006/audio minute effective. "
            "Hot replica option: always-on, ~$50/mo for a single A10G keep-warm. "
            "Good for BookCreator: parent voice-to-text for book customisation input. "
            "Deploy custom fine-tuned Whisper for noisy audio / child voices via Truss."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # NEBIUS AI — EU H100 inference cloud; cheapest EU open-weight hosting
    # Source: https://nebius.com/prices  (via LiteLLM model DB)
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="nebius",
        model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
        input_mtok=0.01,
        output_mtok=0.03,
        context_window=131_072,
        supports_vision=False,
        pricing_url="https://nebius.com/prices",
        notes="Cheapest coding model on EU infrastructure. Great for high-volume code generation at pennies.",
    ),
    ModelPricing(
        provider="nebius",
        model_id="meta-llama/Meta-Llama-3.1-8B-Instruct",
        input_mtok=0.02,
        output_mtok=0.06,
        context_window=131_072,
        supports_vision=False,
        pricing_url="https://nebius.com/prices",
        notes="Cheapest Llama 3.1 8B with EU data residency. Netherlands region.",
    ),
    ModelPricing(
        provider="nebius",
        model_id="meta-llama/Llama-3.3-70B-Instruct",
        input_mtok=0.08,
        output_mtok=0.08,
        context_window=131_072,
        supports_vision=False,
        pricing_url="https://nebius.com/prices",
        notes="Flat in/out pricing. Llama 3.3 70B on EU H100s. Strong general-purpose at low EU cost.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # LAMBDA LABS — GPU cloud; serverless inference API
    # Source: https://lambdalabs.com/inference  (via LiteLLM model DB)
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="lambda_ai",
        model_id="llama3.2-3b-instruct",
        input_mtok=0.015,
        output_mtok=0.025,
        context_window=131_072,
        supports_vision=False,
        pricing_url="https://lambdalabs.com/service/gpu-cloud",
        notes="Cheapest Lambda inference option. Sub-cent per 1K tokens.",
    ),
    ModelPricing(
        provider="lambda_ai",
        model_id="llama3.3-70b-instruct-fp8",
        input_mtok=0.04,
        output_mtok=0.04,
        context_window=131_072,
        supports_vision=False,
        pricing_url="https://lambdalabs.com/service/gpu-cloud",
        notes="Flat in/out rate. FP8 quantized Llama 3.3 70B — minimal quality loss, fast throughput.",
    ),
    ModelPricing(
        provider="lambda_ai",
        model_id="llama4-maverick-instruct-17b-128e",
        input_mtok=0.05,
        output_mtok=0.10,
        context_window=524_288,
        supports_vision=True,
        pricing_url="https://lambdalabs.com/service/gpu-cloud",
        notes="Llama 4 Maverick MoE (17B active / 128 experts). Multimodal, 524K context.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # OLLAMA — local inference; $0 cost; runs 100+ models offline
    # Source: https://ollama.com/library
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="ollama",
        model_id="llama3.3",
        input_mtok=0.0,
        output_mtok=0.0,
        context_window=131_072,
        free_tier="All models free — runs locally on your hardware",
        supports_vision=False,
        pricing_url="https://ollama.com/library/llama3.3",
        notes="Run locally: ollama pull llama3.3 && ollama run llama3.3. OpenAI-compat on localhost:11434.",
    ),
    ModelPricing(
        provider="ollama",
        model_id="qwen3:32b",
        input_mtok=0.0,
        output_mtok=0.0,
        context_window=128_000,
        free_tier="All models free — runs locally on your hardware",
        supports_vision=False,
        pricing_url="https://ollama.com/library/qwen3",
        notes="Qwen3 32B locally. Requires ~20GB VRAM (or CPU offload). Best local reasoning model.",
    ),
    ModelPricing(
        provider="ollama",
        model_id="phi4",
        input_mtok=0.0,
        output_mtok=0.0,
        context_window=16_384,
        free_tier="All models free — runs locally on your hardware",
        supports_vision=False,
        pricing_url="https://ollama.com/library/phi4",
        notes="Microsoft Phi-4 14B locally. 8GB VRAM sufficient. Best small-model local reasoning.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # ALIBABA DASHSCOPE — direct Qwen API; free flash tier
    # Source: https://help.aliyun.com/zh/dashscope/ (via LiteLLM model DB)
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="dashscope",
        model_id="qwen-flash",
        input_mtok=0.0,
        output_mtok=0.0,
        context_window=997_952,
        free_tier="Free up to 1M tokens/day (rate-limited)",
        supports_vision=False,
        pricing_url="https://help.aliyun.com/zh/dashscope/developer-reference/tongyi-qianwen-7b-14b-72b-metering-and-billing",
        notes="Almost-1M context at $0. Useful for long-document processing during dev. Chinese market only.",
    ),
    ModelPricing(
        provider="dashscope",
        model_id="qwen-turbo-latest",
        input_mtok=0.14,
        output_mtok=0.60,
        context_window=1_000_000,
        supports_vision=False,
        pricing_url="https://help.aliyun.com/zh/dashscope/developer-reference/tongyi-qianwen-7b-14b-72b-metering-and-billing",
        notes="Qwen Turbo direct from Alibaba. 1M context. Cheaper than via OpenRouter for high volume.",
    ),
    ModelPricing(
        provider="dashscope",
        model_id="qwen-max-latest",
        input_mtok=1.60,
        output_mtok=4.80,
        context_window=32_768,
        supports_vision=False,
        pricing_url="https://help.aliyun.com/zh/dashscope/developer-reference/tongyi-qianwen-7b-14b-72b-metering-and-billing",
        notes="Qwen Max flagship — highest quality in the Qwen family. Strong coding and math.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # ALLEN INSTITUTE FOR AI — OLMo (fully open: weights + data + code)
    # Source: https://openrouter.ai/allenai
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="allenai",
        model_id="OLMo-2-0325-32B-Instruct",
        input_mtok=0.20,
        output_mtok=0.60,
        context_window=65_536,
        supports_vision=False,
        pricing_url="https://openrouter.ai/allenai/olmo-2-0325-32b-instruct",
        notes="Fully open (weights + data + code). Best research-transparency model. Apache 2.0.",
    ),
    ModelPricing(
        provider="allenai",
        model_id="OLMo-2-0325-32B-Think",
        input_mtok=0.15,
        output_mtok=0.50,
        context_window=65_536,
        supports_thinking=True,
        supports_vision=False,
        pricing_url="https://openrouter.ai/allenai/olmo-2-0325-32b-think",
        notes="OLMo reasoning variant with chain-of-thought. Cheaper than base for thinking tasks.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # INFLECTION AI — Pi conversational / productivity models
    # Source: https://openrouter.ai/inflection
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="inflection",
        model_id="inflection-3-pi",
        input_mtok=2.50,
        output_mtok=10.00,
        context_window=8_000,
        supports_vision=False,
        pricing_url="https://openrouter.ai/inflection/inflection-3-pi",
        notes="Personal AI companion model. High EQ / empathetic tone. Not suitable for coding tasks.",
    ),
    ModelPricing(
        provider="inflection",
        model_id="inflection-3-productivity",
        input_mtok=2.50,
        output_mtok=10.00,
        context_window=8_000,
        supports_vision=False,
        pricing_url="https://openrouter.ai/inflection/inflection-3-productivity",
        notes="Business/productivity-tuned variant of Pi. Strong at structured task completion and summarisation.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # ARCEE AI — distillation/merging specialists; efficient compressed models
    # Source: https://openrouter.ai/arcee-ai
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="arcee_ai",
        model_id="arcee-ai/arcee-spotlight",
        input_mtok=0.18,
        output_mtok=0.18,
        context_window=131_072,
        supports_vision=False,
        pricing_url="https://openrouter.ai/arcee-ai/arcee-spotlight",
        notes="Document understanding specialist. Flat rate. Strong for PDF/report extraction tasks.",
    ),
    ModelPricing(
        provider="arcee_ai",
        model_id="arcee-ai/maestro-reasoning",
        input_mtok=0.90,
        output_mtok=3.30,
        context_window=131_072,
        supports_thinking=True,
        supports_vision=False,
        pricing_url="https://openrouter.ai/arcee-ai/maestro-reasoning",
        notes="Frontier-class reasoning via distillation. o1-class capability at lower cost.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # POOLSIDE AI — enterprise code generation; proprietary code corpus
    # Source: https://openrouter.ai/poolside (free preview pricing)
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="poolside",
        model_id="poolside-ai/laguna-xs.2",
        input_mtok=0.0,
        output_mtok=0.0,
        context_window=131_072,
        free_tier="Free during public preview",
        supports_vision=False,
        pricing_url="https://openrouter.ai/poolside-ai/laguna-xs.2",
        notes="Fast code-focused model. Trained on proprietary enterprise code, not public GitHub.",
    ),
    ModelPricing(
        provider="poolside",
        model_id="poolside-ai/laguna-m.1",
        input_mtok=0.0,
        output_mtok=0.0,
        context_window=131_072,
        free_tier="Free during public preview",
        supports_vision=False,
        pricing_url="https://openrouter.ai/poolside-ai/laguna-m.1",
        notes="Medium-size Laguna model. Better quality than XS.2 for complex enterprise code tasks.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # STEPFUN AI — Chinese frontier; 262K context; competitive coding + math
    # Source: https://openrouter.ai/stepfun-ai
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="stepfun",
        model_id="step-3-5-flash",
        input_mtok=0.10,
        output_mtok=0.30,
        context_window=262_144,
        supports_vision=False,
        pricing_url="https://openrouter.ai/stepfun-ai/step-3-5-flash",
        notes="Fast Chinese frontier model. 262K context. Strong Chinese + coding at $0.10/$0.30.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # XIAOMI — MiMo math reasoning; up to 1M context
    # Source: https://openrouter.ai/xiaomi
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="xiaomi",
        model_id="xiaomi/mimo-vl-7b-rl",
        input_mtok=0.0,
        output_mtok=0.0,
        context_window=131_072,
        free_tier="Free during preview",
        supports_vision=True,
        pricing_url="https://openrouter.ai/xiaomi",
        notes="MiMo multimodal 7B. Free during preview. Math + vision reasoning.",
    ),
    ModelPricing(
        provider="xiaomi",
        model_id="xiaomi/mimo-v2-flash",
        input_mtok=0.09,
        output_mtok=0.29,
        context_window=262_144,
        supports_vision=False,
        pricing_url="https://openrouter.ai/xiaomi/mimo-v2-flash",
        notes="Fast MiMo variant. 262K context. STEM-optimised at sub-$0.30/MTok output.",
    ),
    ModelPricing(
        provider="xiaomi",
        model_id="xiaomi/mimo-v2.5",
        input_mtok=0.40,
        output_mtok=2.00,
        context_window=1_048_576,
        supports_thinking=True,
        supports_vision=False,
        pricing_url="https://openrouter.ai/xiaomi/mimo-v2.5",
        notes="Full MiMo v2.5 with 1M context and reasoning mode. Designed for AIME / competition math.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # MORPH LABS — Fast Apply: code diff application specialist
    # Source: https://openrouter.ai/morph
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="morph",
        model_id="morph/morph-v3-fast",
        input_mtok=0.80,
        output_mtok=1.20,
        context_window=81_920,
        supports_vision=False,
        supports_tool_use=False,
        pricing_url="https://openrouter.ai/morph/morph-v3-fast",
        notes="Fast Apply model: input=original file + edit instruction, output=patched file. Not a general LLM.",
    ),
    ModelPricing(
        provider="morph",
        model_id="morph/morph-v3-large",
        input_mtok=0.90,
        output_mtok=1.90,
        context_window=262_144,
        supports_vision=False,
        supports_tool_use=False,
        pricing_url="https://openrouter.ai/morph/morph-v3-large",
        notes="Larger Fast Apply model with 262K context — handles bigger files than v3-fast.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # INCLUSION AI — Ling-2.6: 1 trillion parameter MoE; free public tier
    # Source: https://openrouter.ai/inclusion-ai
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="inclusionai",
        model_id="inclusion-ai/ling-2.6-1t",
        input_mtok=0.0,
        output_mtok=0.0,
        context_window=262_144,
        free_tier="Free during public preview",
        supports_vision=False,
        pricing_url="https://openrouter.ai/inclusion-ai/ling-2.6-1t",
        notes="1 trillion parameter MoE — largest freely accessible model. Free via OpenRouter preview.",
    ),
    ModelPricing(
        provider="inclusionai",
        model_id="inclusion-ai/ling-2.6-flash",
        input_mtok=0.08,
        output_mtok=0.24,
        context_window=262_144,
        supports_vision=False,
        pricing_url="https://openrouter.ai/inclusion-ai/ling-2.6-flash",
        notes="Fast paid variant of Ling-2.6. $0.08/$0.24 for latency-sensitive applications.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # BYTEDANCE SEED — research arm models (separate from Doubao product)
    # Source: https://openrouter.ai/bytedance-research
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="bytedance_seed",
        model_id="bytedance-research/seed-1.6-flash",
        input_mtok=0.075,
        output_mtok=0.30,
        context_window=262_144,
        supports_vision=False,
        pricing_url="https://openrouter.ai/bytedance-research/seed-1.6-flash",
        notes="ByteDance Seed research model (not Doubao). Fast, cheap, 262K context.",
    ),
    ModelPricing(
        provider="bytedance_seed",
        model_id="bytedance-research/seed-2.0-mini",
        input_mtok=0.10,
        output_mtok=0.40,
        context_window=262_144,
        supports_vision=False,
        pricing_url="https://openrouter.ai/bytedance-research/seed-2.0-mini",
        notes="Seed 2.0 mini — improved quality over 1.6 at similar price point.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # GITHUB COPILOT API — LLM access included in Copilot subscription ($0 marginal)
    # Source: https://docs.github.com/en/copilot
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # LLAMAGATE — ultra-cheap 7-8B inference; ≤16K context
    # Source: LiteLLM model DB
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="llamagate",
        model_id="llama-3.1-8b",
        input_mtok=0.03,
        output_mtok=0.05,
        context_window=8_192,
        supports_vision=False,
        pricing_url="https://llamagate.com/pricing",
        notes="Cheapest Llama 3.1 8B available. 8K context only. Good for bulk classification/routing.",
    ),
    ModelPricing(
        provider="llamagate",
        model_id="qwen3-8b",
        input_mtok=0.04,
        output_mtok=0.14,
        context_window=8_192,
        supports_vision=False,
        pricing_url="https://llamagate.com/pricing",
        notes="Qwen3 8B at $0.04/$0.14. Strong reasoning for size. 8K context limit.",
    ),
    ModelPricing(
        provider="llamagate",
        model_id="deepseek-r1-8b",
        input_mtok=0.10,
        output_mtok=0.20,
        context_window=16_384,
        supports_thinking=True,
        supports_vision=False,
        pricing_url="https://llamagate.com/pricing",
        notes="DeepSeek-R1 distill at 8B. Cheapest reasoning model. 16K context.",
    ),
    ModelPricing(
        provider="llamagate",
        model_id="qwen3-vl-8b",
        input_mtok=0.15,
        output_mtok=0.55,
        context_window=8_192,
        supports_vision=True,
        pricing_url="https://llamagate.com/pricing",
        notes="Cheapest multimodal option on the platform. 8K context.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # OCI (Oracle Cloud) — Generative AI Service; enterprise; Llama + Cohere + Mistral
    # Source: LiteLLM model DB / oracle.com/artificial-intelligence/generative-ai/pricing/
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="oci",
        model_id="meta.llama-3.3-70b-instruct",
        input_mtok=0.72,
        output_mtok=0.72,
        context_window=128_000,
        supports_vision=False,
        pricing_url="https://www.oracle.com/artificial-intelligence/generative-ai/pricing/",
        notes="Flat in/out rate. Llama 3.3 70B on OCI. FedRAMP-authorized US/EU regions.",
    ),
    ModelPricing(
        provider="oci",
        model_id="meta.llama-3.2-90b-vision-instruct",
        input_mtok=2.00,
        output_mtok=2.00,
        context_window=128_000,
        supports_vision=True,
        pricing_url="https://www.oracle.com/artificial-intelligence/generative-ai/pricing/",
        notes="Vision-capable Llama 3.2 90B on OCI. Flat rate.",
    ),
    ModelPricing(
        provider="oci",
        model_id="meta.llama-3.1-405b-instruct",
        input_mtok=10.68,
        output_mtok=10.68,
        context_window=128_000,
        supports_vision=False,
        pricing_url="https://www.oracle.com/artificial-intelligence/generative-ai/pricing/",
        notes="Llama 405B on OCI — premium tier. Flat rate, likely for enterprise regulated workloads.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # OVH CLOUD — EU-based open-weight inference; GDPR; French data residency
    # Source: LiteLLM model DB / endpoints.ai.cloud.ovh.net
    # ══════════════════════════════════════════════════════════════════════
    ModelPricing(
        provider="ovhcloud",
        model_id="Llama-3.1-8B-Instruct",
        input_mtok=0.10,
        output_mtok=0.10,
        context_window=128_000,
        supports_vision=False,
        pricing_url="https://endpoints.ai.cloud.ovh.net/",
        notes="Flat rate. EU-hosted Llama 8B. Good for GDPR-sensitive bulk workloads.",
    ),
    ModelPricing(
        provider="ovhcloud",
        model_id="Meta-Llama-3_1-70B-Instruct",
        input_mtok=0.67,
        output_mtok=0.67,
        context_window=128_000,
        supports_vision=False,
        pricing_url="https://endpoints.ai.cloud.ovh.net/",
        notes="Flat rate. EU-hosted Llama 70B. French datacenter, GDPR-compliant.",
    ),
    ModelPricing(
        provider="ovhcloud",
        model_id="DeepSeek-R1-Distill-Llama-70B",
        input_mtok=0.67,
        output_mtok=0.67,
        context_window=128_000,
        supports_thinking=True,
        supports_vision=False,
        pricing_url="https://endpoints.ai.cloud.ovh.net/",
        notes="EU-hosted DeepSeek-R1 distill at 70B. GDPR-compliant reasoning model.",
    ),
    ModelPricing(
        provider="github_copilot",
        model_id="gpt-4o",
        input_mtok=0.0,
        output_mtok=0.0,
        context_window=128_000,
        free_tier="Covered by GitHub Copilot Individual ($10/mo) or Business ($19/user/mo)",
        supports_vision=True,
        pricing_url="https://github.com/features/copilot/plans",
        notes="GPT-4o via Copilot API — $0 per token if team has Copilot subscription. Also Claude + Gemini.",
    ),
    ModelPricing(
        provider="github_copilot",
        model_id="claude-sonnet-4-6",
        input_mtok=0.0,
        output_mtok=0.0,
        context_window=200_000,
        free_tier="Covered by GitHub Copilot Individual ($10/mo) or Business ($19/user/mo)",
        supports_vision=True,
        pricing_url="https://github.com/features/copilot/plans",
        notes="Claude Sonnet via Copilot API — $0 marginal cost. 30+ models available in same subscription.",
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
    "upstage": "https://console.upstage.ai/pricing",
    "01ai": "https://platform.01.ai/pricing",
    "lepton": "https://www.lepton.ai/pricing",
    "baidu": "https://qianfan.cloud.baidu.com/pricing",
    "reka": "https://platform.reka.ai/pricing",
    "tencent": "https://cloud.tencent.com/product/hunyuan",
    "bytedance": "https://console.volcengine.com/ark/region:ark+cn-beijing/model",
    "hyperbolic": "https://app.hyperbolic.xyz/models",
    "siliconflow": "https://siliconflow.cn/pricing",
    "internlm": "https://internlm.intern-ai.org.cn/",
    "aleph_alpha": "https://www.aleph-alpha.com/pricing",
    "nscale": "https://nscale.com/pricing",
    "phi": "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
    "falcon_tii": "https://huggingface.co/tiiuae",
    "snowflake": "https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions",
    "replicate": "https://replicate.com/pricing",
    "modal": "https://modal.com/pricing",
    "ibm_watsonx": "https://www.ibm.com/products/watsonx-ai/pricing",
    "databricks": "https://www.databricks.com/product/pricing/foundation-model-serving",
    "liquid_ai": "https://www.liquid.ai/liquid-foundation-models",
    "llama_api": "https://llama.developer.meta.com/docs/overview",
    "voyage_ai": "https://docs.voyageai.com/docs/pricing",
    "exaone": "https://huggingface.co/LGAI-EXAONE",
    "ai71": "https://ai71.ai/pricing",
    "baseten": "https://www.baseten.co/pricing/",
    "nebius": "https://nebius.com/prices",
    "lambda_ai": "https://lambdalabs.com/service/gpu-cloud",
    "ollama": "https://ollama.com/library",
    "dashscope": "https://help.aliyun.com/zh/dashscope/developer-reference/tongyi-qianwen-7b-14b-72b-metering-and-billing",
    "allenai": "https://openrouter.ai/allenai",
    "inflection": "https://openrouter.ai/inflection",
    "arcee_ai": "https://openrouter.ai/arcee-ai",
    "poolside": "https://openrouter.ai/poolside-ai",
    "stepfun": "https://openrouter.ai/stepfun-ai",
    "xiaomi": "https://openrouter.ai/xiaomi",
    "morph": "https://openrouter.ai/morph",
    "inclusionai": "https://openrouter.ai/inclusion-ai",
    "bytedance_seed": "https://openrouter.ai/bytedance-research",
    "github_copilot": "https://github.com/features/copilot/plans",
    "llamagate": "https://llamagate.com/pricing",
    "oci": "https://www.oracle.com/artificial-intelligence/generative-ai/pricing/",
    "ovhcloud": "https://endpoints.ai.cloud.ovh.net/",
}


# ---------------------------------------------------------------------------
# API quickstart reference — signup, keys, base URL, SDK, usage dashboard
# ---------------------------------------------------------------------------
#
# openai_compat = True  →  use the OpenAI Python SDK / LiteLLM with the given
#                          api_base_url and api_key_env. No provider-specific SDK needed.
#
# litellm_prefix          →  prefix to use in LiteLLM model strings, e.g.
#                             "anthropic/claude-sonnet-4-6" or "gemini/gemini-2.5-pro"

API_QUICKSTART: dict[str, dict] = {
    "anthropic": {
        "signup_url": "https://console.anthropic.com/",
        "api_key_url": "https://console.anthropic.com/settings/keys",
        "api_base_url": "https://api.anthropic.com/v1",
        "openai_compat": False,
        "api_key_env": "ANTHROPIC_API_KEY",
        "python_sdk": "pip install anthropic",
        "litellm_prefix": "anthropic/",
        "usage_url": "https://console.anthropic.com/settings/billing",
        "rate_limits_url": "https://docs.anthropic.com/en/api/rate-limits",
        "docs_url": "https://docs.anthropic.com/en/api/getting-started",
        "models_url": "https://docs.anthropic.com/en/docs/about-claude/models/overview",
        "free_trial": None,
    },
    "openai": {
        "signup_url": "https://platform.openai.com/signup",
        "api_key_url": "https://platform.openai.com/api-keys",
        "api_base_url": "https://api.openai.com/v1",
        "openai_compat": True,
        "api_key_env": "OPENAI_API_KEY",
        "python_sdk": "pip install openai",
        "litellm_prefix": "",
        "usage_url": "https://platform.openai.com/usage",
        "rate_limits_url": "https://platform.openai.com/account/limits",
        "docs_url": "https://platform.openai.com/docs",
        "models_url": "https://platform.openai.com/docs/models",
        "free_trial": None,
    },
    "google": {
        "signup_url": "https://aistudio.google.com/",
        "api_key_url": "https://aistudio.google.com/app/apikey",
        "api_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "openai_compat": True,
        "openai_compat_base": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "python_sdk": "pip install google-generativeai",
        "litellm_prefix": "gemini/",
        "usage_url": "https://aistudio.google.com/app/apikey",
        "rate_limits_url": "https://ai.google.dev/gemini-api/docs/rate-limits",
        "docs_url": "https://ai.google.dev/gemini-api/docs",
        "models_url": "https://ai.google.dev/gemini-api/docs/models",
        "free_trial": "Free tier on AI Studio (all Gemini models, rate-limited)",
    },
    "deepseek": {
        "signup_url": "https://platform.deepseek.com/",
        "api_key_url": "https://platform.deepseek.com/api_keys",
        "api_base_url": "https://api.deepseek.com/v1",
        "openai_compat": True,
        "api_key_env": "DEEPSEEK_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "deepseek/",
        "usage_url": "https://platform.deepseek.com/usage",
        "rate_limits_url": "https://api-docs.deepseek.com/quick_start/rate_limit",
        "docs_url": "https://api-docs.deepseek.com/",
        "models_url": "https://api-docs.deepseek.com/quick_start/pricing/",
        "free_trial": "Trial credits on signup",
    },
    "xai": {
        "signup_url": "https://console.x.ai/",
        "api_key_url": "https://console.x.ai/team/default/api-keys",
        "api_base_url": "https://api.x.ai/v1",
        "openai_compat": True,
        "api_key_env": "XAI_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "xai/",
        "usage_url": "https://console.x.ai/team/default/usage",
        "rate_limits_url": "https://docs.x.ai/docs/rate-limits",
        "docs_url": "https://docs.x.ai/docs",
        "models_url": "https://docs.x.ai/docs/models",
        "free_trial": "Limited free credits for new accounts",
    },
    "mistral": {
        "signup_url": "https://console.mistral.ai/",
        "api_key_url": "https://console.mistral.ai/api-keys/",
        "api_base_url": "https://api.mistral.ai/v1",
        "openai_compat": True,
        "api_key_env": "MISTRAL_API_KEY",
        "python_sdk": "pip install mistralai",
        "litellm_prefix": "mistral/",
        "usage_url": "https://console.mistral.ai/billing/",
        "rate_limits_url": "https://docs.mistral.ai/deployment/laplateforme/rate_limits/",
        "docs_url": "https://docs.mistral.ai/",
        "models_url": "https://docs.mistral.ai/getting-started/models/",
        "free_trial": "Free tier on La Plateforme (no credit card; rate-limited)",
        "notes": (
            "Codestral FREE for individuals at https://codestral.mistral.ai "
            "(separate API key from main; use for IDE integrations)"
        ),
    },
    "cohere": {
        "signup_url": "https://dashboard.cohere.com/",
        "api_key_url": "https://dashboard.cohere.com/api-keys",
        "api_base_url": "https://api.cohere.ai/v1",
        "openai_compat": False,
        "api_key_env": "COHERE_API_KEY",
        "python_sdk": "pip install cohere",
        "litellm_prefix": "cohere/",
        "usage_url": "https://dashboard.cohere.com/billing",
        "rate_limits_url": "https://docs.cohere.com/docs/rate-limits",
        "docs_url": "https://docs.cohere.com/",
        "models_url": "https://docs.cohere.com/docs/models",
        "free_trial": "Trial API key (non-commercial, rate-limited)",
    },
    "perplexity": {
        "signup_url": "https://www.perplexity.ai/settings/api",
        "api_key_url": "https://www.perplexity.ai/settings/api",
        "api_base_url": "https://api.perplexity.ai",
        "openai_compat": True,
        "api_key_env": "PERPLEXITY_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "perplexity/",
        "usage_url": "https://www.perplexity.ai/settings/api",
        "rate_limits_url": "https://docs.perplexity.ai/guides/rate-limits",
        "docs_url": "https://docs.perplexity.ai/",
        "models_url": "https://docs.perplexity.ai/models/model-cards",
        "free_trial": None,
        "notes": "+$0.005/search call on top of token cost for Sonar models",
    },
    "amazon": {
        "signup_url": "https://aws.amazon.com/bedrock/",
        "api_key_url": "https://console.aws.amazon.com/iam/home#/security_credentials",
        "api_base_url": "https://bedrock-runtime.<region>.amazonaws.com",
        "openai_compat": False,
        "api_key_env": "AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY + AWS_REGION",
        "python_sdk": "pip install boto3  # or: pip install anthropic[bedrock]",
        "litellm_prefix": "bedrock/",
        "usage_url": "https://console.aws.amazon.com/billing/home",
        "rate_limits_url": "https://docs.aws.amazon.com/bedrock/latest/userguide/quotas.html",
        "docs_url": "https://docs.aws.amazon.com/bedrock/",
        "models_url": "https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html",
        "free_trial": "AWS Free Tier: limited Nova Micro/Lite calls in first 12 months",
    },
    "groq": {
        "signup_url": "https://console.groq.com/",
        "api_key_url": "https://console.groq.com/keys",
        "api_base_url": "https://api.groq.com/openai/v1",
        "openai_compat": True,
        "api_key_env": "GROQ_API_KEY",
        "python_sdk": "pip install groq",
        "litellm_prefix": "groq/",
        "usage_url": "https://console.groq.com/usage",
        "rate_limits_url": "https://console.groq.com/docs/rate-limits",
        "docs_url": "https://console.groq.com/docs/openai",
        "models_url": "https://console.groq.com/docs/models",
        "free_trial": "Free API key — no credit card required",
    },
    "fireworks": {
        "signup_url": "https://fireworks.ai/login",
        "api_key_url": "https://fireworks.ai/account/api-keys",
        "api_base_url": "https://api.fireworks.ai/inference/v1",
        "openai_compat": True,
        "api_key_env": "FIREWORKS_API_KEY",
        "python_sdk": "pip install fireworks-ai",
        "litellm_prefix": "fireworks_ai/",
        "usage_url": "https://fireworks.ai/account/billing",
        "rate_limits_url": "https://docs.fireworks.ai/guides/rate-limits",
        "docs_url": "https://docs.fireworks.ai/",
        "models_url": "https://fireworks.ai/models",
        "free_trial": "$1 free credit on signup",
    },
    "cloudflare": {
        "signup_url": "https://dash.cloudflare.com/sign-up",
        "api_key_url": "https://dash.cloudflare.com/profile/api-tokens",
        "api_base_url": "https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/run/",
        "openai_compat": True,
        "openai_compat_base": "https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/v1",
        "api_key_env": "CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "cloudflare/",
        "usage_url": "https://dash.cloudflare.com/?to=/:account/ai/workers-ai",
        "rate_limits_url": "https://developers.cloudflare.com/workers-ai/platform/limits/",
        "docs_url": "https://developers.cloudflare.com/workers-ai/",
        "models_url": "https://developers.cloudflare.com/workers-ai/models/",
        "free_trial": "10K Neurons/day free on ALL plans (resets daily)",
    },
    "together": {
        "signup_url": "https://api.together.ai/",
        "api_key_url": "https://api.together.ai/settings/api-keys",
        "api_base_url": "https://api.together.xyz/v1",
        "openai_compat": True,
        "api_key_env": "TOGETHER_API_KEY",
        "python_sdk": "pip install together",
        "litellm_prefix": "together_ai/",
        "usage_url": "https://api.together.ai/settings/billing",
        "rate_limits_url": "https://docs.together.ai/docs/rate-limits",
        "docs_url": "https://docs.together.ai/",
        "models_url": "https://docs.together.ai/docs/serverless-models",
        "free_trial": "$1 free credit on signup",
    },
    "cerebras": {
        "signup_url": "https://cloud.cerebras.ai/",
        "api_key_url": "https://cloud.cerebras.ai/platform/apikeys",
        "api_base_url": "https://api.cerebras.ai/v1",
        "openai_compat": True,
        "api_key_env": "CEREBRAS_API_KEY",
        "python_sdk": "pip install cerebras-cloud-sdk",
        "litellm_prefix": "cerebras/",
        "usage_url": "https://cloud.cerebras.ai/platform/billing",
        "rate_limits_url": "https://inference-docs.cerebras.ai/api-reference/chat",
        "docs_url": "https://inference-docs.cerebras.ai/",
        "models_url": "https://cloud.cerebras.ai/platform/models",
        "free_trial": "Free trial tier (no credit card required)",
    },
    "sambanova": {
        "signup_url": "https://cloud.sambanova.ai/",
        "api_key_url": "https://cloud.sambanova.ai/apis",
        "api_base_url": "https://api.sambanova.ai/v1",
        "openai_compat": True,
        "api_key_env": "SAMBANOVA_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "sambanova/",
        "usage_url": "https://cloud.sambanova.ai/",
        "rate_limits_url": "https://community.sambanova.ai/t/rate-limits/",
        "docs_url": "https://community.sambanova.ai/",
        "models_url": "https://cloud.sambanova.ai/apis",
        "free_trial": "Free tier at cloud.sambanova.ai (no credit card)",
    },
    "openrouter": {
        "signup_url": "https://openrouter.ai/",
        "api_key_url": "https://openrouter.ai/settings/keys",
        "api_base_url": "https://openrouter.ai/api/v1",
        "openai_compat": True,
        "api_key_env": "OPENROUTER_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openrouter/",
        "usage_url": "https://openrouter.ai/settings/billing",
        "rate_limits_url": "https://openrouter.ai/api/v1/auth/key",
        "docs_url": "https://openrouter.ai/docs",
        "models_url": "https://openrouter.ai/models",
        "free_trial": "Small free credit + free $0/tok models",
        "notes": (
            "Single key for 200+ providers. "
            "Useful headers: HTTP-Referer and X-Title for leaderboard attribution. "
            "Free models: openrouter.ai/models?q=free"
        ),
    },
    "nvidia": {
        "signup_url": "https://build.nvidia.com/",
        "api_key_url": "https://build.nvidia.com/settings/api-key",
        "api_base_url": "https://integrate.api.nvidia.com/v1",
        "openai_compat": True,
        "api_key_env": "NVIDIA_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "nvidia_nim/",
        "usage_url": "https://build.nvidia.com/settings/usage",
        "rate_limits_url": "https://docs.api.nvidia.com/nim/reference/rate-limits",
        "docs_url": "https://docs.api.nvidia.com/",
        "models_url": "https://build.nvidia.com/explore/discover",
        "free_trial": "1000 free API credits on signup",
    },
    "mistral_codestral": {
        "signup_url": "https://codestral.mistral.ai/",
        "api_key_url": "https://codestral.mistral.ai/",
        "api_base_url": "https://codestral.mistral.ai/v1",
        "openai_compat": True,
        "api_key_env": "CODESTRAL_API_KEY",
        "python_sdk": "pip install mistralai",
        "usage_url": "https://codestral.mistral.ai/",
        "docs_url": "https://docs.mistral.ai/capabilities/code_generation/",
        "free_trial": "FREE for individuals — no credit card, no rate-limit issues for IDE use",
        "notes": (
            "Separate endpoint + API key from main Mistral API. "
            "Use for IDE integrations: VS Code Copilot, Continue, Cursor. "
            "model_id = 'codestral-latest'"
        ),
    },
    "zhipu": {
        "signup_url": "https://open.bigmodel.cn/",
        "api_key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "api_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "openai_compat": True,
        "api_key_env": "ZHIPUAI_API_KEY",
        "python_sdk": "pip install zhipuai",
        "litellm_prefix": "zhipuai/",
        "usage_url": "https://open.bigmodel.cn/usercenter/recharge",
        "docs_url": "https://open.bigmodel.cn/dev/api",
        "models_url": "https://open.bigmodel.cn/pricing",
        "free_trial": "Trial credits on signup",
    },
    "deepinfra": {
        "signup_url": "https://deepinfra.com/dash/deployments",
        "api_key_url": "https://deepinfra.com/dash/api_keys",
        "api_base_url": "https://api.deepinfra.com/v1/openai",
        "openai_compat": True,
        "api_key_env": "DEEPINFRA_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "deepinfra/",
        "usage_url": "https://deepinfra.com/dash/billing",
        "docs_url": "https://deepinfra.com/docs",
        "models_url": "https://deepinfra.com/models",
        "free_trial": "Trial API credits on signup",
    },
    "upstage": {
        "signup_url": "https://console.upstage.ai/",
        "api_key_url": "https://console.upstage.ai/api-keys",
        "api_base_url": "https://api.upstage.ai/v1/solar",
        "openai_compat": True,
        "api_key_env": "UPSTAGE_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "usage_url": "https://console.upstage.ai/billing",
        "docs_url": "https://developers.upstage.ai/docs/getting-started",
        "models_url": "https://console.upstage.ai/pricing",
        "free_trial": "$10 credit on signup",
    },
    "01ai": {
        "signup_url": "https://platform.01.ai/",
        "api_key_url": "https://platform.01.ai/apikeys",
        "api_base_url": "https://api.01.ai/v1",
        "openai_compat": True,
        "api_key_env": "YI_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "usage_url": "https://platform.01.ai/usage",
        "docs_url": "https://platform.01.ai/docs",
        "models_url": "https://platform.01.ai/pricing",
        "free_trial": "Trial credits on signup",
    },
    "reka": {
        "signup_url": "https://platform.reka.ai/",
        "api_key_url": "https://platform.reka.ai/api-keys",
        "api_base_url": "https://api.reka.ai/v1",
        "openai_compat": True,
        "api_key_env": "REKA_API_KEY",
        "python_sdk": "pip install reka-api",
        "usage_url": "https://platform.reka.ai/billing",
        "docs_url": "https://docs.reka.ai/",
        "models_url": "https://platform.reka.ai/pricing",
        "free_trial": "Trial credits on signup",
    },
    "lepton": {
        "signup_url": "https://www.lepton.ai/",
        "api_key_url": "https://www.lepton.ai/dashboard/settings",
        "api_base_url": "https://llama3-1-8b.lepton.run/api/v1",
        "openai_compat": True,
        "api_key_env": "LEPTON_API_TOKEN",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "usage_url": "https://www.lepton.ai/dashboard/billing",
        "docs_url": "https://www.lepton.ai/docs",
        "models_url": "https://www.lepton.ai/pricing",
        "free_trial": "$10 credit on signup",
        "notes": "Each model has its own subdomain base URL: <model-slug>.lepton.run/api/v1",
    },
    "ai21": {
        "signup_url": "https://studio.ai21.com/",
        "api_key_url": "https://studio.ai21.com/account/api-key",
        "api_base_url": "https://api.ai21.com/studio/v1",
        "openai_compat": False,
        "api_key_env": "AI21_API_KEY",
        "python_sdk": "pip install ai21",
        "litellm_prefix": "ai21/",
        "usage_url": "https://studio.ai21.com/account/billing",
        "docs_url": "https://docs.ai21.com/",
        "models_url": "https://www.ai21.com/pricing",
        "free_trial": "$10 free credit on signup",
    },
    "huggingface": {
        "signup_url": "https://huggingface.co/join",
        "api_key_url": "https://huggingface.co/settings/tokens",
        "api_base_url": "https://api-inference.huggingface.co/models/<model-id>",
        "openai_compat": True,
        "openai_compat_base": "https://api-inference.huggingface.co/v1",
        "api_key_env": "HF_TOKEN",
        "python_sdk": "pip install huggingface_hub",
        "litellm_prefix": "huggingface/",
        "usage_url": "https://huggingface.co/settings/billing",
        "docs_url": "https://huggingface.co/docs/api-inference",
        "models_url": "https://huggingface.co/models?pipeline_tag=text-generation",
        "free_trial": "Free serverless inference for popular models (rate-limited); PRO $9/mo for higher limits",
    },
    "novita": {
        "signup_url": "https://novita.ai/",
        "api_key_url": "https://novita.ai/settings/key-management",
        "api_base_url": "https://api.novita.ai/v3/openai",
        "openai_compat": True,
        "api_key_env": "NOVITA_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "usage_url": "https://novita.ai/settings/billing",
        "docs_url": "https://novita.ai/docs",
        "models_url": "https://novita.ai/model-api/pricing",
        "free_trial": "Some models permanently free; batch 50% off",
    },
    "moonshot": {
        "signup_url": "https://platform.moonshot.ai/",
        "api_key_url": "https://platform.moonshot.ai/console/api-keys",
        "api_base_url": "https://api.moonshot.ai/v1",
        "openai_compat": True,
        "api_key_env": "MOONSHOT_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "usage_url": "https://platform.moonshot.ai/console/billing",
        "docs_url": "https://platform.moonshot.ai/docs",
        "models_url": "https://platform.moonshot.ai/docs/pricing/chat",
        "free_trial": "Trial credits on signup",
    },
    "tencent": {
        "signup_url": "https://cloud.tencent.com/",
        "api_key_url": "https://console.cloud.tencent.com/hunyuan/api-key",
        "api_base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "openai_compat": True,
        "api_key_env": "HUNYUAN_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openai/",
        "usage_url": "https://console.cloud.tencent.com/hunyuan",
        "docs_url": "https://cloud.tencent.com/document/product/1729",
        "models_url": "https://cloud.tencent.com/product/hunyuan",
        "free_trial": "Trial credits on signup at cloud.tencent.com",
    },
    "bytedance": {
        "signup_url": "https://console.volcengine.com/ark/",
        "api_key_url": "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
        "api_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "openai_compat": True,
        "api_key_env": "ARK_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openai/",
        "usage_url": "https://console.volcengine.com/ark/region:ark+cn-beijing/billing",
        "docs_url": "https://www.volcengine.com/docs/82379/1182403",
        "models_url": "https://console.volcengine.com/ark/region:ark+cn-beijing/model",
        "free_trial": "Trial credits on signup; some models have free quota",
        "notes": "Model ID format: endpoint ID (created in console), not model name directly",
    },
    "hyperbolic": {
        "signup_url": "https://app.hyperbolic.xyz/",
        "api_key_url": "https://app.hyperbolic.xyz/settings",
        "api_base_url": "https://api.hyperbolic.xyz/v1",
        "openai_compat": True,
        "api_key_env": "HYPERBOLIC_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openai/",
        "usage_url": "https://app.hyperbolic.xyz/billing",
        "docs_url": "https://docs.hyperbolic.xyz/",
        "models_url": "https://app.hyperbolic.xyz/models",
        "free_trial": "$1 free credit on signup",
        "notes": "Batch API available at 50% off standard rate. H100-backed.",
    },
    "siliconflow": {
        "signup_url": "https://cloud.siliconflow.cn/",
        "api_key_url": "https://cloud.siliconflow.cn/account/ak",
        "api_base_url": "https://api.siliconflow.cn/v1",
        "openai_compat": True,
        "api_key_env": "SILICONFLOW_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openai/",
        "usage_url": "https://cloud.siliconflow.cn/account/billing",
        "docs_url": "https://docs.siliconflow.cn/",
        "models_url": "https://siliconflow.cn/pricing",
        "free_trial": "$14 free credit on signup; several models permanently free",
    },
    "internlm": {
        "signup_url": "https://internlm.intern-ai.org.cn/",
        "api_key_url": "https://internlm.intern-ai.org.cn/api/document",
        "api_base_url": "https://internlm-chat.intern-ai.org.cn/puyu/api/v1",
        "openai_compat": True,
        "api_key_env": "INTERNLM_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openai/",
        "usage_url": "https://internlm.intern-ai.org.cn/",
        "docs_url": "https://internlm.intern-ai.org.cn/api/document",
        "models_url": "https://internlm.intern-ai.org.cn/",
        "free_trial": "Free tier available; also served via SiliconFlow (free models)",
        "notes": "Open weights also available on HuggingFace for self-hosting",
    },
    "aleph_alpha": {
        "signup_url": "https://app.aleph-alpha.com/signup",
        "api_key_url": "https://app.aleph-alpha.com/profile",
        "api_base_url": "https://api.aleph-alpha.com",
        "openai_compat": False,
        "api_key_env": "AA_TOKEN",
        "python_sdk": "pip install aleph-alpha-client",
        "litellm_prefix": "aleph_alpha/",
        "usage_url": "https://app.aleph-alpha.com/usage",
        "docs_url": "https://docs.aleph-alpha.com/",
        "models_url": "https://www.aleph-alpha.com/pricing",
        "free_trial": None,
        "notes": "GDPR/EU AI Act compliant. On-prem deployment available. EU data residency guaranteed.",
    },
    "nscale": {
        "signup_url": "https://nscale.com/",
        "api_key_url": "https://console.nscale.com/api-keys",
        "api_base_url": "https://inference.nscale.com/v1",
        "openai_compat": True,
        "api_key_env": "NSCALE_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openai/",
        "usage_url": "https://console.nscale.com/billing",
        "docs_url": "https://docs.nscale.com/",
        "models_url": "https://nscale.com/pricing",
        "free_trial": None,
        "notes": "UK-based H100 cluster. EU/UK data residency. No egress fees.",
    },
    "phi": {
        "signup_url": "https://portal.azure.com",
        "api_key_url": "https://ai.azure.com",
        "api_base_url": "https://<endpoint>.services.ai.azure.com/models",
        "openai_compat": True,
        "api_key_env": "AZURE_INFERENCE_CREDENTIAL",
        "python_sdk": "pip install azure-ai-inference",
        "litellm_prefix": "azure_ai/",
        "usage_url": "https://portal.azure.com/#view/Microsoft_Azure_CostManagement",
        "docs_url": "https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models",
        "models_url": "https://ai.azure.com/explore/models?task=text-generation&publisher=Microsoft",
        "free_trial": "Azure startup credits apply (Microsoft for Startups); also free via Ollama",
        "notes": "phi-4 and phi-4-mini available via Azure AI Foundry serverless OR ollama run phi4",
    },
    "falcon_tii": {
        "signup_url": "https://www.together.ai/",
        "api_key_url": "https://api.together.ai/settings/api-keys",
        "api_base_url": "https://api.together.xyz/v1",
        "openai_compat": True,
        "api_key_env": "TOGETHER_API_KEY",
        "python_sdk": "pip install together",
        "litellm_prefix": "together_ai/",
        "usage_url": "https://api.together.ai/settings/billing",
        "docs_url": "https://docs.together.ai/",
        "models_url": "https://www.together.ai/pricing",
        "free_trial": "$1 free credit on signup",
        "notes": "Falcon models served via Together AI. Weights free on HuggingFace (Apache 2.0).",
    },
    "snowflake": {
        "signup_url": "https://www.together.ai/",
        "api_key_url": "https://api.together.ai/settings/api-keys",
        "api_base_url": "https://api.together.xyz/v1",
        "openai_compat": True,
        "api_key_env": "TOGETHER_API_KEY",
        "python_sdk": "pip install together",
        "litellm_prefix": "together_ai/",
        "usage_url": "https://api.together.ai/settings/billing",
        "docs_url": "https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions",
        "models_url": "https://www.together.ai/pricing",
        "free_trial": "$1 free credit on signup (Together AI)",
        "notes": (
            "Arctic served via Together AI (external). "
            "Inside Snowflake: use SNOWFLAKE.CORTEX.COMPLETE('snowflake-arctic', ...) SQL UDF. "
            "No API key needed inside Snowflake — billed to Snowflake credits."
        ),
    },
    "replicate": {
        "signup_url": "https://replicate.com/signin",
        "api_key_url": "https://replicate.com/account/api-tokens",
        "api_base_url": "https://api.replicate.com/v1",
        "openai_compat": False,
        "api_key_env": "REPLICATE_API_TOKEN",
        "python_sdk": "pip install replicate",
        "litellm_prefix": "replicate/",
        "usage_url": "https://replicate.com/account/billing",
        "rate_limits_url": "https://replicate.com/docs/reference/http#rate-limits",
        "docs_url": "https://replicate.com/docs",
        "models_url": "https://replicate.com/explore",
        "free_trial": "Free for public model cold-start queue (slow); credit card for priority",
        "notes": "Per-GPU-second billing. Fine-tune API: POST /trainings. Webhook on job complete.",
    },
    "modal": {
        "signup_url": "https://modal.com/signup",
        "api_key_url": "https://modal.com/settings/tokens",
        "api_base_url": "https://api.modal.com",
        "openai_compat": False,
        "api_key_env": "MODAL_TOKEN_ID + MODAL_TOKEN_SECRET",
        "python_sdk": "pip install modal && modal setup",
        "litellm_prefix": None,
        "usage_url": "https://modal.com/settings/billing",
        "docs_url": "https://modal.com/docs",
        "models_url": "https://modal.com/pricing",
        "free_trial": "$30/mo free compute (no credit card for first 30 days)",
        "notes": (
            "Write pure Python; deploy with @app.function(gpu='A100'). "
            "Not a traditional LLM API — you deploy custom inference code. "
            "Best for: hosting fine-tuned LoRA models, batch upscaling pipelines, custom inference."
        ),
    },
    "ibm_watsonx": {
        "signup_url": "https://www.ibm.com/products/watsonx-ai",
        "api_key_url": "https://cloud.ibm.com/iam/apikeys",
        "api_base_url": "https://us-south.ml.cloud.ibm.com/ml/v1/text/generation",
        "openai_compat": False,
        "api_key_env": "IBM_CLOUD_API_KEY",
        "python_sdk": "pip install ibm-watsonx-ai",
        "litellm_prefix": "watsonx/",
        "usage_url": "https://cloud.ibm.com/billing",
        "docs_url": "https://dataplatform.cloud.ibm.com/docs/content/wsj/analyze-data/fm-api.html",
        "models_url": "https://www.ibm.com/products/watsonx-ai/foundation-models",
        "free_trial": "Lite plan: 50K tokens/month free",
        "notes": "Region in URL: us-south, eu-de, jp-tok, etc. Also requires project_id in body.",
    },
    "databricks": {
        "signup_url": "https://www.databricks.com/try-databricks",
        "api_key_url": "https://<workspace>.azuredatabricks.net/settings/user/developer/access-tokens",
        "api_base_url": "https://<workspace>.azuredatabricks.net/serving-endpoints",
        "openai_compat": True,
        "api_key_env": "DATABRICKS_TOKEN",
        "python_sdk": "pip install databricks-sdk  # or: pip install openai with workspace URL",
        "litellm_prefix": "databricks/",
        "usage_url": "https://<workspace>.azuredatabricks.net/sql/warehouses",
        "docs_url": "https://docs.databricks.com/en/machine-learning/foundation-models/index.html",
        "models_url": "https://www.databricks.com/product/pricing/foundation-model-serving",
        "free_trial": None,
        "notes": "Workspace URL varies by cloud (AWS/Azure/GCP). OpenAI-compat via /serving-endpoints/<name>/invocations.",
    },
    "liquid_ai": {
        "signup_url": "https://liquid.ai/",
        "api_key_url": "https://liquid.ai/",
        "api_base_url": "https://api.liquid.ai/v1",
        "openai_compat": True,
        "api_key_env": "LIQUID_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openai/",
        "usage_url": "https://liquid.ai/",
        "docs_url": "https://docs.liquid.ai/",
        "models_url": "https://www.liquid.ai/liquid-foundation-models",
        "free_trial": "Trial credits on signup",
    },
    "llama_api": {
        "signup_url": "https://llama.developer.meta.com/",
        "api_key_url": "https://llama.developer.meta.com/dashboard",
        "api_base_url": "https://api.llama.com/v1",
        "openai_compat": True,
        "api_key_env": "LLAMA_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openai/",
        "usage_url": "https://llama.developer.meta.com/dashboard",
        "docs_url": "https://llama.developer.meta.com/docs/api",
        "models_url": "https://llama.developer.meta.com/docs/overview",
        "free_trial": "Free tier: limited daily tokens",
        "notes": "Official Meta-hosted reference implementation. No quantization variance vs other providers.",
    },
    "voyage_ai": {
        "signup_url": "https://dash.voyageai.com/",
        "api_key_url": "https://dash.voyageai.com/api-keys",
        "api_base_url": "https://api.voyageai.com/v1",
        "openai_compat": False,
        "api_key_env": "VOYAGE_API_KEY",
        "python_sdk": "pip install voyageai",
        "litellm_prefix": "voyage/",
        "usage_url": "https://dash.voyageai.com/billing",
        "docs_url": "https://docs.voyageai.com/",
        "models_url": "https://docs.voyageai.com/docs/pricing",
        "free_trial": "200M tokens free on signup",
        "notes": "Embeddings only. POST /embeddings with input=[text list], model=voyage-3. Returns float32 vectors.",
    },
    "exaone": {
        "signup_url": "https://www.together.ai/",
        "api_key_url": "https://api.together.ai/settings/api-keys",
        "api_base_url": "https://api.together.xyz/v1",
        "openai_compat": True,
        "api_key_env": "TOGETHER_API_KEY",
        "python_sdk": "pip install together",
        "litellm_prefix": "together_ai/",
        "usage_url": "https://api.together.ai/settings/billing",
        "docs_url": "https://huggingface.co/LGAI-EXAONE",
        "models_url": "https://www.together.ai/pricing",
        "free_trial": "$1 free credit on signup (Together AI)",
        "notes": "EXAONE models served via Together AI. Research license — confirm commercial use with LG AI Research.",
    },
    "ai71": {
        "signup_url": "https://ai71.ai/",
        "api_key_url": "https://ai71.ai/dashboard",
        "api_base_url": "https://api.ai71.ai/v1",
        "openai_compat": True,
        "api_key_env": "AI71_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openai/",
        "usage_url": "https://ai71.ai/dashboard",
        "docs_url": "https://docs.ai71.ai/",
        "models_url": "https://ai71.ai/pricing",
        "free_trial": "Trial credits on signup",
        "notes": "UAE data residency. Best Arabic-English bilingual API. G42 / MBZUAI venture.",
    },
    "baseten": {
        "signup_url": "https://app.baseten.co/signup",
        "api_key_url": "https://app.baseten.co/settings/api_keys",
        "api_base_url": "https://model-<model-id>.api.baseten.co/production/predict",
        "openai_compat": False,
        "api_key_env": "BASETEN_API_KEY",
        "python_sdk": "pip install baseten",
        "litellm_prefix": None,
        "usage_url": "https://app.baseten.co/settings/billing",
        "docs_url": "https://docs.baseten.co/",
        "models_url": "https://www.baseten.co/pricing/",
        "free_trial": None,
        "notes": (
            "Each deployed model gets its own endpoint URL. "
            "Truss framework: define model class in Python, push to Baseten, auto-containerised. "
            "Hot replicas available — always-on GPU for zero cold starts."
        ),
    },
    "nebius": {
        "signup_url": "https://nebius.com/auth/sign-up",
        "api_key_url": "https://console.nebius.com/folders/*/credentials",
        "api_base_url": "https://api.studio.nebius.ai/v1",
        "openai_compat": True,
        "api_key_env": "NEBIUS_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "nebius/",
        "usage_url": "https://console.nebius.com/billing",
        "docs_url": "https://nebius.com/docs/ai-studio",
        "models_url": "https://nebius.com/prices",
        "free_trial": "Trial credits on signup",
        "notes": "Netherlands HQ, GDPR compliant. 30+ models from $0.01/MTok. H100 SXM5 cluster.",
    },
    "lambda_ai": {
        "signup_url": "https://lambdalabs.com/",
        "api_key_url": "https://cloud.lambdalabs.com/api-keys",
        "api_base_url": "https://api.lambdalabs.com/v1",
        "openai_compat": True,
        "api_key_env": "LAMBDA_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openai/",
        "usage_url": "https://cloud.lambdalabs.com/billing",
        "docs_url": "https://docs.lambdalabs.com/inference/",
        "models_url": "https://lambdalabs.com/service/gpu-cloud",
        "free_trial": "Trial available",
        "notes": "Also rents GPU instances: H100 SXM5 $2.49/hr on-demand. Same key works for both inference API and GPU.",
    },
    "ollama": {
        "signup_url": "https://ollama.com/",
        "api_key_url": None,
        "api_base_url": "http://localhost:11434/v1",
        "openai_compat": True,
        "api_key_env": None,
        "python_sdk": "curl -fsSL https://ollama.com/install.sh | sh  # then: pip install openai",
        "litellm_prefix": "ollama/",
        "usage_url": None,
        "docs_url": "https://github.com/ollama/ollama/blob/main/docs/api.md",
        "models_url": "https://ollama.com/library",
        "free_trial": "All models free — runs locally",
        "notes": "ollama pull <model> && ollama serve. No API key — local only. Supports NVIDIA/AMD/Apple Silicon.",
    },
    "dashscope": {
        "signup_url": "https://dashscope.aliyuncs.com/",
        "api_key_url": "https://dashscope.console.aliyun.com/apiKey",
        "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "openai_compat": True,
        "api_key_env": "DASHSCOPE_API_KEY",
        "python_sdk": "pip install dashscope  # or: pip install openai with base_url override",
        "litellm_prefix": "dashscope/",
        "usage_url": "https://dashscope.console.aliyun.com/billing",
        "docs_url": "https://help.aliyun.com/zh/dashscope/",
        "models_url": "https://help.aliyun.com/zh/dashscope/developer-reference/tongyi-qianwen-7b-14b-72b-metering-and-billing",
        "free_trial": "qwen-flash: 1M tokens/day free",
        "notes": "Requires Aliyun (Alibaba Cloud) account. Compatible-mode base URL for OpenAI SDK.",
    },
    "allenai": {
        "signup_url": "https://openrouter.ai/",
        "api_key_url": "https://openrouter.ai/settings/keys",
        "api_base_url": "https://openrouter.ai/api/v1",
        "openai_compat": True,
        "api_key_env": "OPENROUTER_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base=openrouter.ai/api/v1",
        "litellm_prefix": "openrouter/",
        "usage_url": "https://openrouter.ai/settings/credits",
        "docs_url": "https://huggingface.co/allenai",
        "models_url": "https://openrouter.ai/allenai",
        "free_trial": None,
        "notes": "OLMo weights also on HuggingFace (Apache 2.0). Self-host or use via OpenRouter.",
    },
    "inflection": {
        "signup_url": "https://openrouter.ai/",
        "api_key_url": "https://openrouter.ai/settings/keys",
        "api_base_url": "https://openrouter.ai/api/v1",
        "openai_compat": True,
        "api_key_env": "OPENROUTER_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base=openrouter.ai/api/v1",
        "litellm_prefix": "openrouter/",
        "usage_url": "https://openrouter.ai/settings/credits",
        "docs_url": "https://developers.inflection.ai/",
        "models_url": "https://openrouter.ai/inflection",
        "free_trial": None,
        "notes": "Pi also available directly at pi.ai (consumer product). API via OpenRouter.",
    },
    "arcee_ai": {
        "signup_url": "https://openrouter.ai/",
        "api_key_url": "https://openrouter.ai/settings/keys",
        "api_base_url": "https://openrouter.ai/api/v1",
        "openai_compat": True,
        "api_key_env": "OPENROUTER_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base=openrouter.ai/api/v1",
        "litellm_prefix": "openrouter/",
        "usage_url": "https://openrouter.ai/settings/credits",
        "docs_url": "https://docs.arcee.ai/",
        "models_url": "https://openrouter.ai/arcee-ai",
        "free_trial": None,
        "notes": "Direct Arcee API also available at arcee.ai — same models, check for startup discounts.",
    },
    "poolside": {
        "signup_url": "https://openrouter.ai/",
        "api_key_url": "https://openrouter.ai/settings/keys",
        "api_base_url": "https://openrouter.ai/api/v1",
        "openai_compat": True,
        "api_key_env": "OPENROUTER_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base=openrouter.ai/api/v1",
        "litellm_prefix": "openrouter/",
        "usage_url": "https://openrouter.ai/settings/credits",
        "docs_url": "https://www.poolside.ai/",
        "models_url": "https://openrouter.ai/poolside-ai",
        "free_trial": "Free during public preview",
        "notes": "Contact poolside.ai for enterprise API access with SLA. OpenRouter is the public preview path.",
    },
    "stepfun": {
        "signup_url": "https://platform.stepfun.com/",
        "api_key_url": "https://platform.stepfun.com/account/api-key",
        "api_base_url": "https://api.stepfun.com/v1",
        "openai_compat": True,
        "api_key_env": "STEPFUN_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openrouter/",
        "usage_url": "https://platform.stepfun.com/billing",
        "docs_url": "https://platform.stepfun.com/docs",
        "models_url": "https://openrouter.ai/stepfun-ai",
        "free_trial": "Trial credits on signup",
        "notes": "Direct API at api.stepfun.com/v1. Also available via OpenRouter.",
    },
    "xiaomi": {
        "signup_url": "https://openrouter.ai/",
        "api_key_url": "https://openrouter.ai/settings/keys",
        "api_base_url": "https://openrouter.ai/api/v1",
        "openai_compat": True,
        "api_key_env": "OPENROUTER_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base=openrouter.ai/api/v1",
        "litellm_prefix": "openrouter/",
        "usage_url": "https://openrouter.ai/settings/credits",
        "docs_url": "https://github.com/XiaoMi/MiMo",
        "models_url": "https://openrouter.ai/xiaomi",
        "free_trial": "MiMo VL free during preview",
        "notes": "Open weights on HuggingFace (Apache 2.0). Self-host or use via OpenRouter.",
    },
    "morph": {
        "signup_url": "https://openrouter.ai/",
        "api_key_url": "https://openrouter.ai/settings/keys",
        "api_base_url": "https://openrouter.ai/api/v1",
        "openai_compat": True,
        "api_key_env": "OPENROUTER_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base=openrouter.ai/api/v1",
        "litellm_prefix": "openrouter/",
        "usage_url": "https://openrouter.ai/settings/credits",
        "docs_url": "https://morphlabs.ai/",
        "models_url": "https://openrouter.ai/morph",
        "free_trial": None,
        "notes": "Specialised for diff application — pipe LLM-generated edits through Morph before writing to disk.",
    },
    "inclusionai": {
        "signup_url": "https://openrouter.ai/",
        "api_key_url": "https://openrouter.ai/settings/keys",
        "api_base_url": "https://openrouter.ai/api/v1",
        "openai_compat": True,
        "api_key_env": "OPENROUTER_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base=openrouter.ai/api/v1",
        "litellm_prefix": "openrouter/",
        "usage_url": "https://openrouter.ai/settings/credits",
        "docs_url": "https://inclusionai.github.io/ling/",
        "models_url": "https://openrouter.ai/inclusion-ai",
        "free_trial": "Ling-2.6-1T free during public preview",
        "notes": "1T MoE free tier is extremely valuable for long-context tasks during preview period.",
    },
    "bytedance_seed": {
        "signup_url": "https://openrouter.ai/",
        "api_key_url": "https://openrouter.ai/settings/keys",
        "api_base_url": "https://openrouter.ai/api/v1",
        "openai_compat": True,
        "api_key_env": "OPENROUTER_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base=openrouter.ai/api/v1",
        "litellm_prefix": "openrouter/",
        "usage_url": "https://openrouter.ai/settings/credits",
        "docs_url": "https://github.com/ByteDance-Seed",
        "models_url": "https://openrouter.ai/bytedance-research",
        "free_trial": None,
        "notes": "Research arm of ByteDance. Distinct from Doubao/Skylark product API (console.volcengine.com).",
    },
    "github_copilot": {
        "signup_url": "https://github.com/features/copilot",
        "api_key_url": "https://github.com/settings/copilot",
        "api_base_url": "https://api.githubcopilot.com",
        "openai_compat": True,
        "api_key_env": "GITHUB_TOKEN",
        "python_sdk": "pip install openai  # use GITHUB_TOKEN + api_base https://api.githubcopilot.com",
        "litellm_prefix": None,
        "usage_url": "https://github.com/settings/billing/summary",
        "docs_url": "https://docs.github.com/en/copilot/using-github-copilot",
        "models_url": "https://github.com/features/copilot/plans",
        "free_trial": "Free for verified students/teachers/OSS maintainers (copilot.github.com)",
        "notes": (
            "Use GITHUB_TOKEN (OAuth or fine-grained PAT). "
            "30+ models (GPT-4o, Claude Sonnet, Gemini) — all $0 marginal cost if on Copilot plan. "
            "Copilot Individual $10/mo; Business $19/user/mo. "
            "Rate limits apply per subscription tier."
        ),
    },
    "llamagate": {
        "signup_url": "https://llamagate.com/",
        "api_key_url": "https://llamagate.com/dashboard",
        "api_base_url": "https://api.llamagate.com/v1",
        "openai_compat": True,
        "api_key_env": "LLAMAGATE_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "llamagate/",
        "usage_url": "https://llamagate.com/dashboard",
        "docs_url": "https://llamagate.com/docs",
        "models_url": "https://llamagate.com/pricing",
        "free_trial": None,
        "notes": "Budget 7-8B inference only. Context ≤16K. Good for bulk classification/routing/embedding tasks.",
    },
    "oci": {
        "signup_url": "https://signup.cloud.oracle.com/",
        "api_key_url": "https://cloud.oracle.com/identity/domains/my-profile/auth-tokens",
        "api_base_url": "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com/20231130",
        "openai_compat": False,
        "api_key_env": "OCI_API_KEY",
        "python_sdk": "pip install oci  # OCI Python SDK; or: pip install openai for compat endpoint",
        "litellm_prefix": "oci/",
        "usage_url": "https://cloud.oracle.com/usage-reports",
        "docs_url": "https://docs.oracle.com/en-us/iaas/Content/generative-ai/overview.htm",
        "models_url": "https://www.oracle.com/artificial-intelligence/generative-ai/pricing/",
        "free_trial": "Oracle for Startups: up to $300K in OCI credits",
        "notes": (
            "Region in URL: us-chicago-1, eu-frankfurt-1, ap-osaka-1, etc. "
            "Requires OCI tenancy + API key (RSA key pair, not bearer token). "
            "FedRAMP authorized (US Gov). Oracle for Startups program: apply at oracle.com/startups."
        ),
    },
    "ovhcloud": {
        "signup_url": "https://www.ovhcloud.com/en/public-cloud/ai-machine-learning/",
        "api_key_url": "https://www.ovh.com/manager/#/dedicated/tokens",
        "api_base_url": "https://api.ai.cloud.ovh.net/v1",
        "openai_compat": True,
        "api_key_env": "OVH_AI_API_KEY",
        "python_sdk": "pip install openai  # use OpenAI SDK with api_base override",
        "litellm_prefix": "openai/",
        "usage_url": "https://www.ovh.com/manager/#/billing",
        "docs_url": "https://docs.ovh.com/gb/en/publiccloud/ai/",
        "models_url": "https://endpoints.ai.cloud.ovh.net/",
        "free_trial": None,
        "notes": "French HQ, EU data residency, GDPR. AI Endpoints: pay-per-token, no GPU management needed.",
    },
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
        "no_equity_path": (
            "HARD WALL — no no-equity path exists. "
            "Google's own free accelerator does NOT qualify alone. "
            "Requires institutional equity investment (VC SAFE or priced round). "
            "Angel, friends/family, grants, prizes, crowdfunding all explicitly EXCLUDED. "
            "Only path without traditional VC: raise a SAFE from a micro-VC or institutional angel."
        ),
        "notes": (
            "AI-first startup required. Seed to Series A (Series A must be within last 12 months). "
            "Founded within 10 years. Cap: not yet received $5K+ in Google Cloud credits. "
            "Includes $10K Anthropic partner credit via Vertex AI marketplace."
        ),
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
        "credit_detail": "Up to $100K; AI/FM tier (2026): up to $300K for foundational AI startups on Bedrock/Trainium",
        "duration_note": "12-24 months depending on provider",
        "funding_required": "seed",  # OR: membership in a confirmed Activate Provider program
        "multiple_entities_ok": True,  # each legal entity applies independently
        "ai_inference_covered": True,
        "ai_detail": "Amazon Bedrock (Claude, Llama, Mistral, Cohere, Nova)",
        "other_perks": "Up to $10,000 Business Support (24/7 cloud engineers)",
        "url": "https://aws.amazon.com/activate/",
        "no_equity_path": (
            "NVIDIA Inception is a confirmed AWS Activate Provider — gives $25K-$100K AWS credits "
            "via the Inception benefits portal (no equity, no VC needed). "
            "On Deck ODF fellowship also confirmed. Plug and Play strongly implied. "
            "Provider Org IDs are private — ask your accelerator directly."
        ),
        "notes": (
            "Org ID from an Activate Provider unlocks this tier (funding OR program membership). "
            "NVIDIA Inception = best no-equity path to Portfolio tier. "
            "Apply within 12 months of most recent funding or program start. Pre-Series B only. "
            "Upgrade path from Founders: receive difference up to lifetime $100K cap. "
            "AI/FM tier ($300K) requires top-tier partner referral; targets foundational AI builders."
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
        "credit_detail": "$2,500 direct; $50K via OpenAI Grove (no equity, cohort); $100K+ via VC partner referral",
        "duration_note": "Not publicly specified",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Full OpenAI API access (GPT-5.x, o3, codex-mini-latest, etc.)",
        "other_perks": "Partner network introductions, early model access",
        "url": "https://openai.com/startups/",
        "grove_url": "https://openai.com/index/openai-grove/",
        "no_equity_path": (
            "OpenAI Grove: $50K API credits + 5-week SF mentorship, EQUITY-FREE. "
            "~15 spots/cohort; highly selective; Cohort 2 closed Jan 2026 — watch for Cohort 3. "
            "$100K tier requires VC/accelerator with OpenAI partner status (200+ partners); list not public."
        ),
        "notes": (
            "Direct apply (no investor): $2,500. < 5 years old; formally incorporated; functional product; "
            "API meaningfully integrated in product. Sole proprietors not eligible. "
            "OpenAI VC Partnership network: 200+ VCs; ask your investor for referral code format PARTNER-XXXX-XXXX."
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
        "funding_required": "seed",  # OR partner affiliation (several no-equity partners confirmed)
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "GitHub Copilot (Business + premium models + agentic), 50K Actions minutes, Advanced Security",
        "other_perks": "GitHub Enterprise (20 seats), GitHub Actions, GitHub Packages, Advanced Security",
        "url": "https://github.com/enterprise/startups",
        "partners_url": "https://github.com/enterprise/startups/partners",
        "no_equity_path": (
            "Multiple no-equity partners confirmed on github.com/enterprise/startups/partners: "
            "Plug and Play Tech Center (no equity), "
            "MassChallenge (nonprofit, no equity), "
            "StartX / Stanford (no equity), "
            "On Deck ODF fellowship (no equity for fellowship itself). "
            "Founder Institute (2.5% warrants only) also confirmed partner. "
            "Apply via partner referral OR email startups@github.com"
        ),
        "notes": (
            "Requires Series B or earlier + never used GitHub Enterprise before. "
            "Azure credits can also fund Copilot if Azure subscription linked to GitHub account. "
            "YC reportedly NOT on the GitHub partners list (surprising)."
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
    # ── Modal ─────────────────────────────────────────────────────────────
    "modal_for_startups": {
        "name": "Modal for Startups",
        "provider": "Modal",
        "credits_usd": 10_000,
        "credit_detail": "$10,000 in Modal compute credits",
        "duration_note": "Not publicly specified; typically 12 months",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "All Modal GPU compute (A10G, A100, H100) — custom inference and training",
        "other_perks": "$30/mo free compute already included for all accounts before applying",
        "url": "https://modal.com/startups",
        "notes": (
            "No equity, no investor required. Apply at modal.com/startups. "
            "Useful specifically for BookCreator: host per-child LoRA inference endpoints, "
            "batch upscaling pipeline, custom fine-tuning jobs — all on Modal compute credits. "
            "Stack with AWS Activate: Modal covers custom deployment; AWS covers standard infra."
        ),
    },
    # ── Together AI ────────────────────────────────────────────────────────
    "together_for_startups": {
        "name": "Together AI for Startups (AI Accelerate)",
        "provider": "Together AI",
        "credits_usd": 25_000,
        "credit_detail": "$25,000 in Together AI inference credits",
        "duration_note": "Not publicly specified",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Together AI serverless inference (DeepSeek-V3, Llama-3.3-70B, Qwen, Flux, SDXL, etc.)",
        "other_perks": "Priority support, access to Together Research team, community events",
        "url": "https://www.together.ai/startups",
        "notes": (
            "Together AI hosts both LLMs and image gen models under one API. "
            "$25K covers: ~125M Llama-3.3-70B tokens, or ~13M Flux Schnell images. "
            "No equity required. Apply at together.ai/startups. "
            "Combined with $1 signup credit and free Flux Schnell tier for prototyping."
        ),
    },
    # ── IBM Build ──────────────────────────────────────────────────────────
    "ibm_build": {
        "name": "IBM Build — Startup Program",
        "provider": "IBM",
        "credits_usd": 6_000,
        "credit_detail": "$6,000 in IBM Cloud credits + free watsonx.ai access",
        "duration_note": "12 months",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "watsonx.ai (Granite 3.3 series) + IBM Cloud services",
        "other_perks": (
            "1-on-1 IBM technical advisor, go-to-market co-selling, "
            "IBM partner ecosystem access, IBM Developer community"
        ),
        "url": "https://www.ibm.com/partnerplus/isv",
        "notes": (
            "IBM Build targets ISVs (Independent Software Vendors) building on IBM platforms. "
            "Best reason to apply: FedRAMP/HIPAA/SOC 2 compliance via watsonx.ai at no cost. "
            "If targeting healthcare, finance, or government customers, IBM credentials add credibility. "
            "No equity required. Founded < 10 years, building a software product."
        ),
    },
    # ── Databricks ────────────────────────────────────────────────────────
    "databricks_startups": {
        "name": "Databricks Startup Program",
        "provider": "Databricks",
        "credits_usd": 10_000,
        "credit_detail": "$10,000 in Databricks DBU credits (Data Bundle Units)",
        "duration_note": "12 months",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Databricks Foundation Model APIs (DBRX, Llama, Mistral) + Mosaic AI",
        "other_perks": "Databricks Ventures consideration, partner ecosystem, go-to-market support",
        "url": "https://www.databricks.com/company/partner-program",
        "notes": (
            "DBUs cover: Foundation Model API (DBRX, Llama 3.3 70B), "
            "Delta Lake storage, Spark compute, MLflow experiment tracking. "
            "No equity required. Early-stage (pre-Series B). "
            "Stronger if your data pipeline already uses Spark/Delta — "
            "calling DBRX from inside a Databricks notebook is zero-egress, zero-latency."
        ),
    },
    # ── Groq ──────────────────────────────────────────────────────────────
    "groq_for_startups": {
        "name": "Groq for Startups",
        "provider": "Groq",
        "credits_usd": 5_000,
        "credit_detail": "$5,000 in GroqCloud inference credits",
        "duration_note": "Not publicly specified",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "GroqCloud inference (Llama-3.3-70B at 2000+ tok/s, Mixtral, Gemma, DeepSeek-R1-distil)",
        "other_perks": "Priority rate limits, Groq engineering support",
        "url": "https://groq.com/startups/",
        "notes": (
            "Groq's LPU (Language Processing Unit) is 10-100x faster than GPU inference. "
            "Llama 3.3 70B at 2000+ tok/s — near-instant responses. "
            "Primary use case: latency-critical agentic chains, real-time voice/chat features. "
            "For BookCreator: story generation in <1s vs 5-10s on other providers. "
            "No equity required."
        ),
    },
    # ── Cerebras ──────────────────────────────────────────────────────────
    "cerebras_for_startups": {
        "name": "Cerebras for Startups",
        "provider": "Cerebras Systems",
        "credits_usd": 5_000,
        "credit_detail": "$5,000 in Cerebras Cloud inference credits",
        "duration_note": "Not publicly specified",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Cerebras Cloud inference (Llama 3.3 70B at 2000+ tok/s on wafer-scale chip)",
        "other_perks": "Engineering support, early access to new Cerebras chip generations",
        "url": "https://cloud.cerebras.ai/",
        "notes": (
            "Cerebras wafer-scale engine: single chip the size of a dinner plate, "
            "850K AI cores. Llama 3.3 70B at 2100+ tokens/sec — fastest available. "
            "Similar pitch to Groq: ultra-low latency for interactive applications. "
            "No equity required. Apply via cloud.cerebras.ai."
        ),
    },
    # ── Replicate ─────────────────────────────────────────────────────────
    "replicate_for_startups": {
        "name": "Replicate Growth Program",
        "provider": "Replicate",
        "credits_usd": 2_500,
        "credit_detail": "$2,500 in Replicate compute credits",
        "duration_note": "Not publicly specified",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Replicate GPU-second compute (LLM inference + image gen + LoRA fine-tuning)",
        "other_perks": "Priority support, Replicate team introductions",
        "url": "https://replicate.com/",
        "notes": (
            "Apply via replicate.com (contact support for startup program details — not publicly listed). "
            "Most valuable for: LoRA fine-tune pipeline ($1.50/run) + inference hosting for trained models. "
            "$2.5K = ~1,666 LoRA training runs OR ~833K image gen calls. "
            "Stack with other programs: use Replicate for fine-tuning, AWS/GCP/Azure for raw compute."
        ),
    },
    # ── Baseten ───────────────────────────────────────────────────────────
    "baseten_for_startups": {
        "name": "Baseten Startup Program",
        "provider": "Baseten",
        "credits_usd": 5_000,
        "credit_detail": "$5,000 in Baseten compute credits",
        "duration_note": "Not publicly specified",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "Baseten GPU compute (A10G, A100, H100) for custom model serving",
        "other_perks": "Dedicated ML engineer support, production deployment guidance",
        "url": "https://www.baseten.co/startups/",
        "notes": (
            "Focused on production ML serving — not just prototyping. "
            "Best use: deploy custom fine-tuned models (e.g. Whisper for audio input, "
            "SDXL+LoRA for image gen) with hot replicas and autoscaling SLAs. "
            "No equity required. Apply at baseten.co/startups."
        ),
    },
    # ── Voyage AI ─────────────────────────────────────────────────────────
    "voyage_ai_free_tier": {
        "name": "Voyage AI — 200M Free Embedding Tokens",
        "provider": "Voyage AI",
        "credits_usd": 12,  # 200M tokens x $0.06/MTok = $12 equivalent
        "credit_detail": "200M embedding tokens free on signup (no credit card)",
        "duration_note": "One-time on signup; no expiry stated",
        "funding_required": False,
        "multiple_entities_ok": True,
        "ai_inference_covered": True,
        "ai_detail": "voyage-3, voyage-code-3, voyage-3-lite, voyage-3-large embeddings",
        "other_perks": "Access to voyage-rerank-2 reranker",
        "url": "https://dash.voyageai.com/",
        "notes": (
            "200M free tokens = enough to embed ~150K average-length documents. "
            "For BookCreator RAG: embed your entire book template library + user preference history. "
            "Not a large dollar amount but covers early-stage embedding pipeline entirely. "
            "No startup program beyond this — but 200M tokens is generous for a seed-stage app."
        ),
    },
}


# ---------------------------------------------------------------------------
# No-equity accelerators that unlock higher startup credit tiers
# ---------------------------------------------------------------------------
#
# "no_equity" = the accelerator itself does not take company equity.
# Investment arms (e.g. Plug and Play Ventures, ODX) are separate opt-in.
#
# AWS Portfolio Org IDs and Microsoft/OpenAI partner lists are PRIVATE —
# contact the accelerator directly and ask for their referral code/Org ID.
#
# Columns: program_unlocks = {program_key: credit_tier_unlocked_usd}

NO_EQUITY_ACCELERATORS: dict[str, dict] = {
    "nvidia_inception": {
        "name": "NVIDIA Inception",
        "equity": False,
        "cost": "Free",
        "eligibility": "Incorporated, <10yr old, 1+ developer, active website; no consulting/crypto/resellers",
        "apply_url": "https://programs.nvidia.com/phoenix/application",
        "contact": "inceptionprogram@nvidia.com",
        "program_unlocks": {
            "aws_activate_portfolio": "$25K-$100K (confirmed AWS Activate Provider)",
            "microsoft_investor_offer": "Likely (confirmed Microsoft collaboration for AI startups)",
        },
        "notes": (
            "Single best no-equity accelerator for cloud credits. "
            "AWS credits claimed via Inception benefits portal after acceptance. "
            "Two separate incorporated startups each qualify independently."
        ),
    },
    "plug_and_play": {
        "name": "Plug and Play Tech Center",
        "equity": False,
        "cost": "Free (investment arm Plug and Play Ventures is separate/optional)",
        "eligibility": "Open batches by vertical (fintech, health, sustainability, etc.); global",
        "apply_url": "https://www.plugandplaytechcenter.com/",
        "program_unlocks": {
            "aws_activate_portfolio": "Strongly implied (AWS partner; Org ID on request)",
            "github_for_startups": "Confirmed GitHub partner",
        },
        "notes": "Largest no-equity accelerator globally. 50+ corporate partners. Batch programs 2x/year.",
    },
    "on_deck_odf": {
        "name": "On Deck Founders Fellowship (ODF)",
        "equity": False,
        "cost": "Paid fellowship (~$3,500-$5,000/cohort)",
        "eligibility": "Founders at any stage; cohort-based; global",
        "apply_url": "https://www.beondeck.com/",
        "program_unlocks": {
            "aws_activate_portfolio": "Confirmed AWS Activate Provider",
            "github_for_startups": "Confirmed GitHub partner",
        },
        "notes": (
            "ODF fellowship = no equity. ODX follow-on fund takes 7% + $125K (separate opt-in). "
            "Strong network for B2B SaaS founders."
        ),
    },
    "masschallenge": {
        "name": "MassChallenge",
        "equity": False,
        "cost": "Free (nonprofit accelerator)",
        "eligibility": "Early-stage startups globally; multiple verticals including tech, health, energy",
        "apply_url": "https://masschallenge.org/",
        "program_unlocks": {
            "github_for_startups": "Confirmed GitHub partner",
            "aws_activate_portfolio": "Likely (major accelerator; Org ID on request)",
        },
        "notes": "Cash prizes up to $100K, no equity taken. Strong for impact-oriented startups.",
    },
    "startx_stanford": {
        "name": "StartX (Stanford University)",
        "equity": False,
        "cost": "Free (Stanford-affiliated founders/alumni)",
        "eligibility": "Stanford students, alumni, faculty, and staff",
        "apply_url": "https://startx.com/",
        "program_unlocks": {
            "github_for_startups": "Confirmed GitHub partner",
        },
        "notes": "No equity. Stanford affiliation required. Strong West Coast network.",
    },
    "openai_grove": {
        "name": "OpenAI Grove",
        "equity": False,
        "cost": "Free (equity-free program)",
        "eligibility": "Pre-idea or early-stage founders; SF in-person; ~15 spots/cohort",
        "apply_url": "https://openai.com/index/openai-grove/",
        "program_unlocks": {
            "openai_for_startups": "$50K API credits included in program",
        },
        "notes": (
            "5-week SF-based cohort. Cohort 2 closed Jan 2026 — check for Cohort 3 announcement. "
            "Highly selective. Best no-equity path to substantial OpenAI credits."
        ),
    },
    "founder_institute": {
        "name": "Founder Institute",
        "equity": "2.5% warrants via Equity Collective (very low)",
        "cost": "$899 tuition (waived for some)",
        "eligibility": "Pre-seed founders globally; 200+ cities",
        "apply_url": "https://fi.co/",
        "program_unlocks": {
            "aws_activate_portfolio": "Confirmed ($10K AWS credits; full Portfolio tier uncertain)",
            "github_for_startups": "Confirmed GitHub partner",
        },
        "notes": (
            "2.5% warrants = lowest equity of any structured accelerator. "
            "Largest pre-seed program globally. Strong for first-time founders."
        ),
    },
    "google_for_startups_accelerator": {
        "name": "Google for Startups Accelerator",
        "equity": False,
        "cost": "Free (Google-run, equity-free)",
        "eligibility": "Seed to Series A; AI-first products preferred; batches by geography/vertical",
        "apply_url": "https://startup.google.com/programs/accelerator/",
        "program_unlocks": {
            "aws_activate_portfolio": "Likely (major accelerator; Org ID available on request)",
            "microsoft_investor_offer": "Likely",
            "google_cloud_scale_ai": (
                "DOES NOT QUALIFY ALONE — Scale/AI tier requires separate institutional equity investment. "
                "Being in Google's accelerator without VC funding only gets the $2K Start tier."
            ),
        },
        "notes": (
            "Intensive 10-week equity-free program with Google engineers. "
            "IMPORTANT: Does NOT unlock Google Cloud Scale credits by itself — "
            "institutional equity investment is still required for that tier."
        ),
    },
}


def no_equity_accelerator_table() -> str:
    """
    Markdown table of no-equity accelerators sorted by number of programs they unlock.
    """
    rows = []
    for _key, a in NO_EQUITY_ACCELERATORS.items():
        unlocks = ", ".join(
            k.replace("_", " ")
            .replace("aws activate portfolio", "AWS $100K")
            .replace("github for startups", "GitHub $10K")
            .replace("microsoft investor offer", "MSFT $100K")
            .replace("openai for startups", "OpenAI $50K")
            .replace("google cloud scale ai", "GCP Scale (needs VC)")
            for k in a["program_unlocks"]
        )
        equity_str = "none" if a["equity"] is False else str(a["equity"])
        rows.append(f"| {a['name']:<35} | {equity_str:<25} | {a['cost']:<28} | {unlocks} |")
    header = (
        "### No-Equity Accelerators That Unlock Higher Credit Tiers\n\n"
        "| Accelerator                        | Equity                    | Cost                         | Unlocks |\n"
        "|------------------------------------|---------------------------|------------------------------|---------|\n"
    )
    footer = (
        "\nAll Org IDs / referral codes are private — ask your accelerator directly.\n"
        "Google Cloud Scale tier has a HARD WALL: requires institutional equity regardless of accelerator.\n"
        "NVIDIA Inception is the single best no-equity unlock for AWS Portfolio ($25K-$100K).\n"
    )
    return header + "\n".join(rows) + "\n" + footer


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
# Accelerator programs — low to medium barrier, researched for BookCreator
# (AI-powered book creation startup, pre-seed, no revenue, small team)
# ---------------------------------------------------------------------------
#
# equity_pct: approximate founder dilution from the accelerator itself
#             (not counting future VC rounds).  0 = no equity taken.
# barrier: "low" = essentially auto-approved if eligible
#           "medium" = competitive but realistic for early-stage
#           "high" = <5% acceptance or hard in-person/revenue gate
# remote: True = can participate from home; False = in-person relocation required
# revenue_required: None = not required; string = minimum threshold
# deadline_2026: next known application deadline (None = rolling)
# credits_usd_approx: cloud/tool credits included (approximate)
# STATUS: "active" / "inactive" / "pivoted" — VERIFY before applying

ACCELERATOR_PROGRAMS: dict[str, dict] = {
    # ── Tier 1: Apply now — no revenue, high fit, low-medium barrier ──────
    "cdl_ai": {
        "name": "Creative Destruction Lab — AI Stream",
        "equity_pct": 0,
        "cash_usd": 0,
        "facilitated_investment": "$100K-$1M (from mentors/VCs who choose to invest; not guaranteed)",
        "barrier": "medium",
        "remote": True,
        "remote_note": "1 full-day in-person session every ~8 weeks at chosen site (16 global sites)",
        "revenue_required": None,
        "deadline_2026": "2026-07-24",
        "credits_usd_approx": 0,
        "status": "active",
        "apply_url": "https://creativedestructionlab.com/streams/ai/",
        "selection_criteria": (
            "Science/tech-based venture with massively scalable trajectory. "
            "Objectives-based review every 8 weeks — teams that miss objectives are removed. "
            "No revenue or team size minimum. Strong AI-first product required."
        ),
        "bookcreator_fit": "Very high",
        "fit_reason": "0% equity, free, world-class AI mentorship, remote-friendly. Best value program globally.",
        "cloud_credits": "No direct credits — value is mentor network and facilitated investor introductions.",
    },
    "ai2_incubator": {
        "name": "AI2 Incubator (Allen Institute for AI)",
        "equity_pct": 6.0,
        "cash_usd": 600_000,
        "barrier": "medium",
        "remote": True,
        "remote_note": "Explicitly remote-friendly; quarterly Seattle visits optional or full relocation",
        "revenue_required": None,
        "deadline_2026": None,  # rolling admissions year-round
        "credits_usd_approx": 1_000_000,
        "status": "active",
        "apply_url": "https://apply.ai2incubator.com/apply",
        "selection_criteria": (
            "AI-first startups; ~15 companies/year. No revenue required. "
            "Technical depth and AI model expertise are key differentiators. "
            "Strong bias toward startups with proprietary AI capabilities."
        ),
        "bookcreator_fit": "Very high",
        "fit_reason": (
            "$1M in cloud credits (non-dilutive) for AI training. Remote-friendly. "
            "Track record: 90%+ raise follow-on VC; acquisitions by Apple, Thomson Reuters."
        ),
        "cloud_credits": "Up to $1M combined AWS/GCP/Azure non-dilutive credits for AI model work.",
    },
    "techstars_anywhere": {
        "name": "Techstars Anywhere",
        "equity_pct": 5.0,
        "cash_usd": 220_000,
        "cash_note": "$200K uncapped MFN SAFE + $20K Post-Money Convertible Equity",
        "barrier": "high",  # ~1% acceptance rate
        "remote": True,
        "remote_note": "Fully remote; 3 optional in-person meetings",
        "revenue_required": None,
        "deadline_2026": "2026-06-10",
        "credits_usd_approx": 600_000,
        "status": "active",
        "apply_url": "https://www.techstars.com/accelerators/anywhere",
        "selection_criteria": (
            "~1% acceptance rate. Industry-agnostic. Strong team and large market required. "
            "Solo founders accepted. No revenue required. "
            "Fall 2026 cohort starts Sept 14, 2026."
        ),
        "bookcreator_fit": "High",
        "fit_reason": "Fully remote, no revenue required, industry-agnostic. $600K+ in perks.",
        "cloud_credits": "Up to $100K AWS Activate + up to $350K GCP + up to $150K Azure + $2.5K+ OpenAI.",
    },
    "entrepreneur_first": {
        "name": "Entrepreneur First (EF)",
        "equity_pct": 8.5,
        "cash_usd": 250_000,
        "cash_note": "Up to $250K at ~8-9%; equity-free $10K exploration grant + housing in FORM phase for pre-idea founders",
        "barrier": "medium",
        "remote": False,
        "remote_note": "In-person required: SF, London, or Bangalore",
        "revenue_required": None,
        "deadline_2026": None,  # rolling admissions
        "credits_usd_approx": 600_000,
        "status": "active",
        "apply_url": "https://apply.joinef.com/",
        "selection_criteria": (
            "Solo individuals accepted (EF builds teams from scratch). "
            "Strong bias toward technical founders with deep domain expertise (AI/ML preferred). "
            "Pre-idea is fine — EF is specifically designed for this stage."
        ),
        "bookcreator_fit": "High (solo technical founders especially)",
        "fit_reason": (
            "Best program for solo technical founders. Co-founder matching built in. "
            "$600K+ in AI/cloud credits: $350K Azure + $250K+ OpenAI + Anthropic + GitHub + ElevenLabs."
        ),
        "cloud_credits": "$350K Azure + $250K+ OpenAI + Anthropic + GitHub + ElevenLabs + PostHog.",
    },
    # ── Tier 2: Strong fit, higher bar or in-person requirement ───────────
    "betaworks_camp": {
        "name": "Betaworks Camp — Agent Systems",
        "equity_pct": 5.0,
        "cash_usd": 500_000,
        "cash_note": "Up to $500K: $250K from Betaworks (uncapped SAFE, 25% discount) + $250K syndicate match",
        "barrier": "medium",
        "remote": False,
        "remote_note": "NYC-based; international founders must relocate for part of 12-week program",
        "revenue_required": None,
        "deadline_2026": "2026-07-01",  # approximate; Fall 2026 window opens June-July
        "credits_usd_approx": None,
        "status": "active",
        "apply_url": "https://www.betaworks.com/camp/application",
        "selection_criteria": (
            "~10 companies per cohort. Very early-stage focus; no revenue required. "
            "Spring 2026 theme: 'Agent Systems' — agentic AI delivering work across domains. "
            "Fall 2026 theme TBD. Strong concept fit with AI book creation as an agent-delivered workflow."
        ),
        "bookcreator_fit": "Very high (theme fit)",
        "fit_reason": (
            "'Agent Systems' theme maps directly to an AI agent that takes a brief and produces a publishable book. "
            "$500K for 5% is a competitive deal. Watch for Fall 2026 application window June-July."
        ),
        "cloud_credits": "Via NYC network and partner introductions; no fixed published amount.",
    },
    "antler_us": {
        "name": "Antler (US — Austin / NYC / SF)",
        "equity_pct": 9.1,
        "cash_usd": 250_000,
        "cash_note": "$250K at $2.75M post-money (9.1%); some cohorts up to $500K. $2,500 relocation grant.",
        "barrier": "low",
        "remote": False,
        "remote_note": "6-week in-person residency required (Austin, NYC, or SF)",
        "revenue_required": None,
        "deadline_2026": None,  # rolling
        "credits_usd_approx": 4_000_000,
        "status": "active",
        "apply_url": "https://www.antler.co/residency",
        "selection_criteria": (
            "Solo founders accepted; co-founder matching is Antler's core value-add. "
            "Pre-idea is fine. <3% acceptance from 100K+ applications — but low bar if technical. "
            "20-45% of each residency cohort actually receives investment (IC decision at end of 6 weeks)."
        ),
        "bookcreator_fit": "High (especially for solo founders)",
        "fit_reason": (
            "Best for solo founders needing a co-founder. $4M+ in credits including NVIDIA + OpenAI. "
            "No equity taken if IC doesn't invest — risk-free to try if you can relocate 6 weeks."
        ),
        "cloud_credits": "$4M+ total: NVIDIA DGX credits, OpenAI credits, AWS, GCP, Azure.",
    },
    # ── Tier 3: Apply once MVP + early traction exist ─────────────────────
    "500_global": {
        "name": "500 Global Flagship",
        "equity_pct": 6.0,
        "cash_usd": 150_000,
        "barrier": "high",
        "remote": False,
        "remote_note": "Palo Alto in-person required for ~4 months",
        "revenue_required": "Soft preference for post-revenue / working MVP with traction",
        "deadline_2026": None,  # rolling admissions
        "credits_usd_approx": 1_000_000,
        "status": "active",
        "apply_url": "https://flagship.aplica.500.co/",
        "selection_criteria": (
            "Rolling admissions. ~1-3% acceptance from ~3,000 apps/batch. "
            "At least one full-time founder required. MVP or working prototype expected. "
            "Global founders welcome but must relocate to Palo Alto."
        ),
        "bookcreator_fit": "Medium",
        "fit_reason": "Strong brand. $1M+ credits via FounderHub. Wait until MVP ships.",
        "cloud_credits": "$1M+ total via 500 FounderHub (AWS, GCP, Azure, AI tools).",
    },
    "a16z_speedrun": {
        "name": "a16z Speedrun",
        "equity_pct": 10.0,
        "cash_usd": 500_000,
        "cash_note": "$500K upfront (10% SAFE, uncapped) + $500K pro-rata reserved = up to $1M",
        "barrier": "high",
        "remote": False,
        "remote_note": "12-week in-person SF program (one structured day/week)",
        "revenue_required": None,
        "deadline_2026": "2026-05-17",  # SR007 closed; SR008 expected late 2026
        "credits_usd_approx": 5_000_000,
        "status": "active",
        "apply_url": "https://speedrun.a16z.com/apply",
        "selection_criteria": (
            "Sub-0.4% acceptance rate. 60-70 teams per cohort. "
            "Strong preference for teams with shipping product and early user metrics. "
            "Creative tech, AI, prosumer tools, and entertainment are strong fits thematically."
        ),
        "bookcreator_fit": "Medium (aspirational until traction)",
        "fit_reason": "$1M + $5M credits for 10%. Target once product has active users.",
        "cloud_credits": "$5M+ across 250+ partner tools including all major cloud + AI providers.",
    },
    # ── Dead ends — do not apply ──────────────────────────────────────────
    "newchip": {
        "name": "Newchip Accelerator",
        "status": "CLOSED — bankrupt May 2023. Do not apply.",
        "equity_pct": None,
        "cash_usd": None,
        "barrier": None,
        "remote": None,
        "revenue_required": None,
        "deadline_2026": None,
        "credits_usd_approx": None,
        "apply_url": None,
        "bookcreator_fit": "N/A — defunct",
        "fit_reason": "Program no longer exists.",
        "cloud_credits": None,
    },
    "matter_vc": {
        "name": "Matter Media Accelerator",
        "status": "INACTIVE — last cohort was 2018. Website now promotes Columbia journalism fellowship only.",
        "equity_pct": None,
        "cash_usd": None,
        "barrier": None,
        "remote": None,
        "revenue_required": None,
        "deadline_2026": None,
        "credits_usd_approx": None,
        "apply_url": None,
        "bookcreator_fit": "N/A — inactive",
        "fit_reason": "No active accelerator cohort as of May 2026.",
        "cloud_credits": None,
    },
}


def bookcreator_accelerator_table() -> str:
    """
    Markdown table of accelerator programs for BookCreator, sorted by barrier then fit.
    Excludes dead/inactive programs.
    """
    active = {k: v for k, v in ACCELERATOR_PROGRAMS.items() if v.get("status") == "active"}
    tier_order = {"low": 0, "medium": 1, "high": 2}
    sorted_programs = sorted(active.items(), key=lambda kv: tier_order.get(kv[1]["barrier"], 3))

    rows = []
    for _, p in sorted_programs:
        equity = f"{p['equity_pct']}%" if p["equity_pct"] is not None else "0%"
        cash = f"${p['cash_usd']:,}" if p.get("cash_usd") else "-"
        remote = "yes" if p.get("remote") else "no"
        rev = p.get("revenue_required") or "none"
        deadline = p.get("deadline_2026") or "rolling"
        rows.append(
            f"| {p['name'][:38]:<38} | {equity:>6} | {cash:>10} | {p['barrier']:^6} "
            f"| {remote:^6} | {rev[:20]:<20} | {deadline} |"
        )

    header = (
        "### BookCreator — Accelerator Roadmap (May 2026)\n\n"
        "| Program                                | Equity | Cash invest |Barrier| Remote | Revenue req          | Deadline |\n"
        "|----------------------------------------|--------|-------------|-------|--------|----------------------|----------|\n"
    )
    footer = (
        "\nBarrier: low=auto-approved if eligible, medium=competitive, high=<5% acceptance\n"
        "Apply Tier 1 now: CDL (July 24) + AI2 (rolling) + Techstars Anywhere (June 10)\n"
        "Watch for: Betaworks Fall 2026 window (June-July)\n"
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
