"""
Image generation, LoRA fine-tuning, and GPU cloud pricing for AI pipelines.

All prices USD as of May 2026.  Prices move fast in this space — verify at
the pricing URLs before committing to a provider.

## BookCreator pipeline context

  User photo → character extraction → page generation → inpainting/refinement → print

  Key cost drivers (in order of importance for unit economics):
    1. Image generation: per-image cost x pages x variants shown to user
    2. LoRA fine-tuning: one-time per child character (amortises over lifetime)
    3. GPU hosting: only relevant if you self-host fine-tuned models

  At $14.99/book + shipping, image gen must cost < $0.50/book to be viable.
  A 20-page book at $0.01/image + 3 variants = $0.60 — tight but workable at Runware/Together.

## Refinement loop design (see model_pricing.py for full discussion)

  1. Show 4 variants upfront  →  user picks best  →  99% stop here
  2. Targeted inpainting  →  face/expression adjustments  →  only redoes masked region
  3. LoRA refinement queue  →  corrections fed back into character model

## LoRA character lock-in strategy

  Book 1:  generic face-swap LoRA (fast, cheap, good enough)
  Book 3+: child-specific LoRA trained on approval history (better than competitors)
  Book 6+: character has consistent age, style vocabulary, props → churn resistance

## CivitAI as LoRA source

  civitai.com hosts 100K+ community LoRAs.  For BookCreator:
    - Search for style LoRAs that match your book illustration style
    - Use as a starting point before fine-tuning on a specific child
    - Free to download; CivitAI Red ($15/mo) gives cloud generation + early access

## Recommended stack for <5K books/month

  Generation:    Runware (Flux Schnell $0.0006 or SDXL $0.0026/image)
  Fine-tuning:   Replicate Flux LoRA trainer (<$2/run, H100, under 2 min)
  Inpainting:    FAL.ai Flux Inpainting ($0.025/call — only for refinement round 2+)
  Self-hosting:  RunPod A10G ($0.67/hr) if volume justifies dedicated GPU

## Recommended stack for 5K-50K books/month

  Generation:    Runware (volume discount) or self-hosted SDXL on AWS g5.xlarge spot
  Fine-tuning:   Replicate (API-driven, async queue per child)
  Inpainting:    Self-hosted on same GPU as generation (amortise instance cost)
  Storage:       S3 + LoRA weights per child stored indefinitely (~50MB each)
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Image generation pricing
# ---------------------------------------------------------------------------


@dataclass
class ImageGenPricing:
    provider: str
    model_id: str
    price_per_image: float  # USD at standard resolution (1024x1024 or closest)

    # Billing model — affects how you optimise
    # "per_image"     = fixed per output image (easiest to budget)
    # "per_second"    = GPU seconds consumed (varies with resolution/steps)
    # "per_credit"    = provider credit system (convert to USD at account level)
    # "per_megapixel" = scales with resolution
    billing_model: str = "per_image"

    resolution_options: list[str] = field(default_factory=list)
    supports_inpainting: bool = False
    supports_lora: bool = False  # accepts LoRA weights at inference
    supports_controlnet: bool = False
    latency_seconds: float | None = None
    signup_url: str = ""
    pricing_url: str = ""
    notes: str | None = None

    # Startup credit programs that cover this model's inference cost.
    # Values match keys in STARTUP_PROGRAMS in model_pricing.py.
    # e.g. ["aws_activate", "google_cloud_start"] means costs are creditable.
    credit_programs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LoRA / fine-tuning pricing
# ---------------------------------------------------------------------------


@dataclass
class FinetunePricing:
    provider: str
    service_id: str
    base_models: list[str]
    method: str  # "lora", "dreambooth", "full-finetune"

    typical_cost_usd: float | None = None  # per training run at recommended settings
    price_model: str = ""  # "per_run", "per_step", "per_hour", "per_image_in_dataset"
    price_per_unit: float | None = None  # unit defined by price_model
    min_images: int | None = None
    latency_minutes: float | None = None  # wall-clock training time

    # Inference: how do you call the fine-tuned model?
    inference_cost_per_image: float | None = None
    inference_via: str | None = None  # "same_platform", "self_hosted", "download_weights"

    signup_url: str = ""
    pricing_url: str = ""
    notes: str | None = None


# ---------------------------------------------------------------------------
# GPU cloud instance pricing (for self-hosted inference / training)
# ---------------------------------------------------------------------------


@dataclass
class GPUInstancePricing:
    provider: str
    instance_id: str
    gpu_type: str
    vram_gb: int

    price_per_hour: float  # on-demand / standard rate
    spot_price_per_hour: float | None = None  # spot/preemptible where available

    gpu_count: int = 1
    vcpus: int | None = None
    ram_gb: int | None = None

    # What image-gen models fit in this VRAM?
    # SDXL: needs 8GB+; Flux Dev: 12GB+; Flux full-precision: 24GB+
    suitable_for: str | None = None

    pricing_url: str = ""
    notes: str | None = None

    # Startup credit programs whose compute credits cover this instance.
    credit_programs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Image generation catalogue
# ---------------------------------------------------------------------------

IMAGE_GEN_MODELS: list[ImageGenPricing] = [
    # ══════════════════════════════════════════════════════════════════════
    # RUNWARE  — consistently cheapest per-image; good LoRA support
    # signup: runware.ai  |  api_base: api.runware.ai/v1
    # OpenAI-compat endpoint; free trial credits on signup
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="runware",
        model_id="runware:100@1",  # Flux Schnell
        price_per_image=0.0006,
        billing_model="per_credit",
        resolution_options=["512x512", "1024x1024"],
        supports_lora=True,
        latency_seconds=1.0,
        signup_url="https://runware.ai",
        pricing_url="https://runware.ai/pricing",
        notes=(
            "Cheapest image-gen option: ~1,666 images/$1. "
            "Volume discounts available. LoRA weights accepted. "
            "API: api.runware.ai/v1 (REST + WebSocket)."
        ),
    ),
    ImageGenPricing(
        provider="runware",
        model_id="runware:101@1",  # SDXL
        price_per_image=0.0026,
        billing_model="per_credit",
        resolution_options=["512x512", "768x768", "1024x1024"],
        supports_inpainting=True,
        supports_lora=True,
        latency_seconds=3.0,
        signup_url="https://runware.ai",
        pricing_url="https://runware.ai/pricing",
        notes="~384 images/$1. Inpainting supported — key for refinement loop step 2.",
    ),
    ImageGenPricing(
        provider="runware",
        model_id="runware:107@1",  # Flux Dev
        price_per_image=0.0038,
        billing_model="per_credit",
        resolution_options=["512x512", "1024x1024"],
        supports_lora=True,
        latency_seconds=3.0,
        signup_url="https://runware.ai",
        pricing_url="https://runware.ai/pricing",
        notes="~263 images/$1. Better quality than Schnell; still very cheap.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # TOGETHER AI  — per-megapixel model; cheapest for small output sizes
    # signup: api.together.ai  |  api_base: api.together.xyz/v1
    # $1 free credit on signup; OpenAI-compat
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="together",
        model_id="stability-ai/stable-diffusion-3-medium",
        price_per_image=0.0019,  # at 1 megapixel (1024x1024)
        billing_model="per_megapixel",
        resolution_options=["512x512", "768x768", "1024x1024", "1344x768"],
        latency_seconds=5.0,
        signup_url="https://api.together.ai/",
        pricing_url="https://www.together.ai/pricing",
        notes=(
            "$0.0019/megapixel — scales with resolution. "
            "Same Together API as LLMs: single key. Good for book page generation."
        ),
    ),
    ImageGenPricing(
        provider="together",
        model_id="black-forest-labs/FLUX.1-schnell-Free",
        price_per_image=0.0,
        billing_model="per_image",
        resolution_options=["1024x1024"],
        latency_seconds=2.0,
        signup_url="https://api.together.ai/",
        pricing_url="https://www.together.ai/pricing",
        notes="Free tier — rate-limited. Good for prototyping character variants at zero cost.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # REPLICATE  — per-GPU-second billing; best LoRA fine-tune ecosystem
    # signup: replicate.com  |  api_base: api.replicate.com/v1
    # Pay-as-you-go; excellent fine-tuning API (see FINETUNE_MODELS below)
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="replicate",
        model_id="black-forest-labs/flux-schnell",
        price_per_image=0.003,  # typical at 1024x1024; varies with GPU seconds used
        billing_model="per_second",
        resolution_options=["256x256", "512x512", "1024x1024", "1440x1440"],
        supports_lora=True,
        latency_seconds=1.5,
        signup_url="https://replicate.com/signin",
        pricing_url="https://replicate.com/pricing",
        notes=(
            "Per-second GPU billing: ~$0.00115/sec on H100. "
            "LoRA weights hosted on Replicate — deploy your fine-tuned character models here. "
            "Free tier: slow cold-starts."
        ),
    ),
    ImageGenPricing(
        provider="replicate",
        model_id="black-forest-labs/flux-dev",
        price_per_image=0.055,  # typical; higher resolution = more seconds = higher cost
        billing_model="per_second",
        resolution_options=["512x512", "1024x1024", "1440x1440"],
        supports_lora=True,
        latency_seconds=4.0,
        signup_url="https://replicate.com/signin",
        pricing_url="https://replicate.com/pricing",
        notes=(
            "Higher quality than Schnell; more expensive at ~$0.055 typical. "
            "Best choice for final book page generation when quality matters. "
            "Fine-tuned LoRAs run directly on Replicate after training."
        ),
    ),
    ImageGenPricing(
        provider="replicate",
        model_id="stability-ai/sdxl",
        price_per_image=0.0032,
        billing_model="per_second",
        resolution_options=["512x512", "768x768", "1024x1024"],
        supports_inpainting=True,
        supports_lora=True,
        latency_seconds=4.0,
        signup_url="https://replicate.com/signin",
        pricing_url="https://replicate.com/pricing",
        notes="SDXL on Replicate. Inpainting variant available. Mature LoRA ecosystem.",
    ),
    ImageGenPricing(
        provider="replicate",
        model_id="stability-ai/stable-diffusion-3.5-large",
        price_per_image=0.065,
        billing_model="per_second",
        resolution_options=["512x512", "1024x1024", "1344x768"],
        latency_seconds=8.0,
        signup_url="https://replicate.com/signin",
        pricing_url="https://replicate.com/pricing",
        notes="No LoRA support. Higher quality than SDXL; expensive for volume use.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # FAL.AI  — fixed per-image pricing; fast; strong fine-tuning API
    # signup: fal.ai/dashboard  |  api_key_env: FAL_KEY
    # pip install fal-client; REST + WebSocket; good async queue support
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="fal_ai",
        model_id="fal-ai/flux/schnell",
        price_per_image=0.003,
        billing_model="per_image",
        resolution_options=["512x512", "1024x1024", "1536x1536"],
        supports_lora=True,
        latency_seconds=1.0,
        signup_url="https://fal.ai/dashboard",
        pricing_url="https://fal.ai/pricing",
        notes="Fixed per-image. Predictable cost. LoRA accepted. Fast queue.",
    ),
    ImageGenPricing(
        provider="fal_ai",
        model_id="fal-ai/flux/dev",
        price_per_image=0.025,
        billing_model="per_image",
        resolution_options=["512x512", "1024x1024", "1536x1536"],
        supports_lora=True,
        latency_seconds=4.0,
        signup_url="https://fal.ai/dashboard",
        pricing_url="https://fal.ai/pricing",
        notes=(
            "Best FAL quality. After training a LoRA on FAL, inference runs here. "
            "Good character consistency when combined with fine-tuned LoRA."
        ),
    ),
    ImageGenPricing(
        provider="fal_ai",
        model_id="fal-ai/flux-pro/v1.1-ultra",
        price_per_image=0.06,
        billing_model="per_megapixel",
        resolution_options=["1024x1024", "1920x1080", "2K", "4K"],
        latency_seconds=8.0,
        signup_url="https://fal.ai/dashboard",
        pricing_url="https://fal.ai/pricing",
        notes="Highest FAL quality. Megapixel-based pricing. Use for hero/cover page only.",
    ),
    ImageGenPricing(
        provider="fal_ai",
        model_id="fal-ai/flux/dev/image-to-image",
        price_per_image=0.025,
        billing_model="per_image",
        resolution_options=["1024x1024"],
        supports_inpainting=True,
        latency_seconds=4.0,
        signup_url="https://fal.ai/dashboard",
        pricing_url="https://fal.ai/pricing",
        notes=(
            "Image-to-image + inpainting. Key for refinement loop step 2: "
            "user requests 'make her smile more' → inpaint face region only."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # OPENAI  — GPT Image 1.5 (replaces DALL-E 3 which was removed May 2026)
    # signup: platform.openai.com  |  OpenAI SDK / REST
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="openai",
        model_id="gpt-image-1.5",
        price_per_image=0.03,  # standard quality 1024x1024
        billing_model="per_image",
        resolution_options=["1024x1024", "1792x1024", "1024x1792"],
        supports_inpainting=True,
        latency_seconds=5.0,
        signup_url="https://platform.openai.com/signup",
        pricing_url="https://openai.com/api/pricing/",
        notes=(
            "Replaces DALL-E 3 (removed May 12 2026). "
            "HD quality: $0.08/image. Inpainting supported. "
            "Strong photorealism but no LoRA support."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # STABILITY AI
    # signup: platform.stability.ai  |  api_key_env: STABILITY_API_KEY
    # Credit-based: $10 = 1000 credits; verify current rates
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="stability_ai",
        model_id="stable-image/generate/core",
        price_per_image=0.03,
        billing_model="per_credit",
        resolution_options=["1024x1024", "1344x768", "768x1344"],
        latency_seconds=3.0,
        signup_url="https://platform.stability.ai/sign-up",
        pricing_url="https://platform.stability.ai/pricing",
        notes="3 credits/image. Best Stability value for throughput.",
    ),
    ImageGenPricing(
        provider="stability_ai",
        model_id="stable-image/generate/sd3-5-large",
        price_per_image=0.065,
        billing_model="per_credit",
        resolution_options=["1024x1024", "1344x768", "768x1344"],
        latency_seconds=8.0,
        signup_url="https://platform.stability.ai/sign-up",
        pricing_url="https://platform.stability.ai/pricing",
        notes="6.5 credits/image. Highest Stability quality. No LoRA.",
    ),
    ImageGenPricing(
        provider="stability_ai",
        model_id="stable-image/edit/inpaint",
        price_per_image=0.03,
        billing_model="per_credit",
        resolution_options=["1024x1024"],
        supports_inpainting=True,
        latency_seconds=4.0,
        signup_url="https://platform.stability.ai/sign-up",
        pricing_url="https://platform.stability.ai/pricing",
        notes="Inpainting API. Search-and-replace also available ($0.04). Key for refinement.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # IDEOGRAM  — best text-in-image; strong for book title/cover text
    # signup: ideogram.ai  |  api_key_env: IDEOGRAM_API_KEY
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="ideogram",
        model_id="V_2",
        price_per_image=0.08,
        billing_model="per_image",
        resolution_options=["1024x1024", "1344x768", "768x1344"],
        latency_seconds=5.0,
        signup_url="https://www.ideogram.ai/accounts/signup",
        pricing_url="https://ideogram.ai/features/api-pricing",
        notes=(
            "Best-in-class text rendering within images. "
            "Use for book covers and title pages where child's name appears in illustration. "
            "Ideogram v3 expected 2026 — check for pricing updates."
        ),
    ),
    ImageGenPricing(
        provider="ideogram",
        model_id="V_2_TURBO",
        price_per_image=0.04,
        billing_model="per_image",
        resolution_options=["1024x1024"],
        latency_seconds=3.0,
        signup_url="https://www.ideogram.ai/accounts/signup",
        pricing_url="https://ideogram.ai/features/api-pricing",
        notes="2x cheaper, slightly lower quality than V2. Good for non-cover pages with text.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # GOOGLE IMAGEN 3  (via Vertex AI)
    # signup: cloud.google.com  |  sdk: google-cloud-aiplatform
    # Free trial: $300 Google Cloud credits for new accounts
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="google",
        model_id="imagegeneration@006",  # Imagen 3
        price_per_image=0.04,
        billing_model="per_image",
        resolution_options=["512x512", "1024x1024", "1536x1536"],
        supports_inpainting=True,
        latency_seconds=8.0,
        signup_url="https://cloud.google.com/free",
        pricing_url="https://cloud.google.com/vertex-ai/generative-ai/pricing",
        credit_programs=["google_cloud_start", "google_cloud_scale_ai"],
        notes=(
            "Inpainting: $0.02/image. Upscaling: $0.003/image. "
            "Google Startup Start credits ($2K): 50K images. "
            "Google Startup Scale AI credits ($350K): 8.75M images. "
            "Best quality image gen API covered by GCP credits."
        ),
    ),
    ImageGenPricing(
        provider="google",
        model_id="imagen-3-fast-generate-001",
        price_per_image=0.02,
        billing_model="per_image",
        resolution_options=["1024x1024", "1536x1536"],
        latency_seconds=3.0,
        signup_url="https://cloud.google.com/free",
        pricing_url="https://cloud.google.com/vertex-ai/generative-ai/pricing",
        credit_programs=["google_cloud_start", "google_cloud_scale_ai"],
        notes=(
            "Speed-optimised Imagen 3. Good for variant generation in refinement loop. "
            "GCP Start credits ($2K): 100K images. Scale AI ($350K): 17.5M images."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # SELF-HOSTED ON GCP CREDITS
    # g2-standard-4 (L4 24GB) spot ~$0.21/hr: ~200 imgs/hr SDXL = $0.001/image
    # $2K GCP credits = 2M images; $350K = 350M images
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="gcp_selfhosted",
        model_id="sdxl-on-g2-standard-4-spot",
        price_per_image=0.0011,  # g2-standard-4 L4 spot ~$0.21/hr / ~200 imgs/hr
        billing_model="per_second",
        resolution_options=["512x512", "768x768", "1024x1024"],
        supports_inpainting=True,
        supports_lora=True,
        supports_controlnet=True,
        latency_seconds=18.0,
        signup_url="https://cloud.google.com/free",
        pricing_url="https://cloud.google.com/compute/gpus-pricing",
        credit_programs=["google_cloud_start", "google_cloud_scale_ai"],
        notes=(
            "Self-hosted SDXL on GCP g2-standard-4 (L4 24GB) spot using GCP credits. "
            "L4 spot: ~$0.21/hr. ~200 imgs/hr = $0.001/image effective. "
            "$2K GCP Start credits = 2M images. $350K Scale AI = 350M images. "
            "Full LoRA + ControlNet + inpainting. Same GPU serves all."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # SELF-HOSTED ON AZURE CREDITS
    # NC24ads A100 v4 spot ($0.68/hr): ~600 imgs/hr SDXL = $0.0011/image
    # $5K Azure credits per entity = 4.5M images; $10K both entities = 9M images
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="azure_selfhosted",
        model_id="sdxl-on-nc24ads-a100-spot",
        price_per_image=0.0011,  # NC24ads A100 spot $0.68/hr / ~600 imgs/hr
        billing_model="per_second",
        resolution_options=["512x512", "768x768", "1024x1024"],
        supports_inpainting=True,
        supports_lora=True,
        supports_controlnet=True,
        latency_seconds=6.0,  # A100 is 3x faster than T4/L4
        signup_url="https://azure.microsoft.com/en-us/free/startups/",
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/virtual-machines/",
        credit_programs=["microsoft_self_service"],
        notes=(
            "Self-hosted SDXL on Azure NC24ads A100 v4 spot using Azure Startup credits. "
            "A100 spot: $0.68/hr. ~600 imgs/hr = $0.0011/image effective. "
            "$5K credits (self-service) = 4.5M images. Both entities = 9M images. "
            "Azure has no native image gen API — self-hosting is the only credit path. "
            "A100 handles batch efficiently; latency ~6s vs 18s on T4."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # AMAZON TITAN IMAGE GENERATOR v2  (via AWS Bedrock)
    # signup: aws.amazon.com/bedrock  |  sdk: boto3
    # Usable with AWS Activate startup credits ($25K-$100K via NVIDIA Inception)
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="amazon",
        model_id="amazon.titan-image-generator-v2:0",
        price_per_image=0.012,  # 1024x1024; verify at Bedrock pricing page
        billing_model="per_image",
        resolution_options=["512x512", "768x768", "1024x1024"],
        supports_inpainting=True,
        latency_seconds=6.0,
        signup_url="https://aws.amazon.com/bedrock/",
        pricing_url="https://aws.amazon.com/bedrock/pricing/",
        credit_programs=["aws_activate"],
        notes=(
            "Inpainting and outpainting supported. "
            "Covered by AWS Activate credits — $100K credits = 8.3M images. "
            "Background removal: $0.002/image. Colour-guided: $0.012/image."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # SELF-HOSTED ON AWS CREDITS  — best images-per-credit-dollar
    # g5.xlarge spot ($0.30/hr) with SDXL: ~200 imgs/hr = $0.0015/image
    # $100K AWS Activate credits = ~66M images at this rate
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="aws_selfhosted",
        model_id="sdxl-on-g5xlarge-spot",
        price_per_image=0.0015,  # g5.xlarge spot $0.30/hr / ~200 imgs/hr
        billing_model="per_second",
        resolution_options=["512x512", "768x768", "1024x1024"],
        supports_inpainting=True,
        supports_lora=True,
        supports_controlnet=True,
        latency_seconds=18.0,
        signup_url="https://aws.amazon.com/ec2/",
        pricing_url="https://aws.amazon.com/ec2/pricing/on-demand/",
        credit_programs=["aws_activate"],
        notes=(
            "Self-hosted SDXL on g5.xlarge spot instance using AWS Activate credits. "
            "Effective cost: ~$0.0015/image ($0.30/hr spot / ~200 imgs/hr). "
            "$25K credits = 16.7M images. $100K credits = 66M images. "
            "Full LoRA + ControlNet support. Inpainting on same GPU. "
            "Setup: Docker image with diffusers + FastAPI; ~15min cold start. "
            "Best images-per-credit-dollar of any approach."
        ),
    ),
    ImageGenPricing(
        provider="aws_selfhosted",
        model_id="flux-dev-on-g5xlarge-spot",
        price_per_image=0.005,  # g5.xlarge spot $0.30/hr / ~60 imgs/hr (Flux is slower)
        billing_model="per_second",
        resolution_options=["512x512", "1024x1024"],
        supports_lora=True,
        latency_seconds=30.0,
        signup_url="https://aws.amazon.com/ec2/",
        pricing_url="https://aws.amazon.com/ec2/pricing/on-demand/",
        credit_programs=["aws_activate"],
        notes=(
            "Self-hosted Flux Dev on g5.xlarge spot using AWS Activate credits. "
            "Flux is slower than SDXL but higher quality. ~60 imgs/hr. "
            "$100K credits = 20M images. "
            "LoRA support. Use for final page renders after variant selection."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # LEONARDO.AI
    # signup: leonardo.ai  |  api_key_env: LEONARDO_API_KEY
    # Credit-based; good LoRA ecosystem; training API available
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="leonardo_ai",
        model_id="phoenix",  # Leonardo Phoenix model
        price_per_image=0.006,  # ~2 tokens; $9/mo = 3500 tokens
        billing_model="per_credit",
        resolution_options=["512x512", "768x768", "1024x1024"],
        supports_inpainting=True,
        supports_lora=True,
        latency_seconds=5.0,
        signup_url="https://leonardo.ai/signup",
        pricing_url="https://leonardo.ai/pricing",
        notes=(
            "Credit/token system: standard image ~2-25 tokens depending on resolution. "
            "LoRA-style fine-tuning via Elements feature. "
            "Good for teams: subscription includes generation credits."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # SEGMIND  — affordable; broad model selection; free tier
    # signup: segmind.com  |  api_key_env: SEGMIND_API_KEY
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="segmind",
        model_id="sdxl1.0-txt2img",
        price_per_image=0.008,
        billing_model="per_image",
        resolution_options=["512x512", "768x768", "1024x1024"],
        supports_inpainting=True,
        supports_lora=True,
        latency_seconds=3.0,
        signup_url="https://www.segmind.com/sign-up",
        pricing_url="https://www.segmind.com/pricing",
        notes="Free tier available. LoRA and ControlNet support.",
    ),
    ImageGenPricing(
        provider="segmind",
        model_id="flux-schnell",
        price_per_image=0.008,
        billing_model="per_image",
        resolution_options=["512x512", "1024x1024"],
        supports_lora=True,
        latency_seconds=1.5,
        signup_url="https://www.segmind.com/sign-up",
        pricing_url="https://www.segmind.com/pricing",
        notes="Flux Schnell on Segmind. Free tier eligible.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # ADOBE FIREFLY API
    # signup: developer.adobe.com  |  enterprise only for production
    # Strong for commercial use — models trained on licensed content only
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="adobe",
        model_id="firefly-image-3",
        price_per_image=0.02,  # approximate; verify at adobe.io
        billing_model="per_credit",
        resolution_options=["1024x1024", "1024x1536", "1536x1024"],
        supports_inpainting=True,
        latency_seconds=4.0,
        signup_url="https://developer.adobe.com/console",
        pricing_url="https://www.adobe.com/products/firefly/plans.html",
        notes=(
            "Commercially safe — trained on licensed/owned content. "
            "Good for publishers concerned about IP liability. "
            "Enterprise pricing ~$1K+/mo minimum for production API access."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # CIVITAI  — community LoRA hub + cloud generation
    # Primary use: source pre-trained style LoRAs before per-child fine-tuning
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="civitai",
        model_id="civitai-cloud-generation",
        price_per_image=0.0032,  # ~8 buzz per image; $15/mo Red = ~4700 buzz
        billing_model="per_credit",  # "Buzz" credits
        resolution_options=["512x512", "768x768", "1024x1024"],
        supports_lora=True,
        supports_controlnet=True,
        latency_seconds=5.0,
        signup_url="https://civitai.com/user/account",
        pricing_url="https://civitai.com/pricing",
        notes=(
            "CivitAI Buzz credit system: earn free Buzz daily or buy. "
            "100K+ community LoRAs and checkpoints available for download. "
            "Use as a source for style LoRAs that match your book illustration aesthetic. "
            "Models downloadable and runnable self-hosted (no API lock-in)."
        ),
    ),
    ImageGenPricing(
        provider="civitai_red",
        model_id="civitai-red-subscription",
        price_per_image=0.003,  # $15/mo Red gives ~5000 Buzz = ~5000 standard images
        billing_model="per_credit",
        resolution_options=["512x512", "1024x1024"],
        supports_lora=True,
        supports_controlnet=True,
        latency_seconds=5.0,
        signup_url="https://civitai.com/pricing",
        pricing_url="https://civitai.com/pricing",
        notes=(
            "CivitAI Red: $15/mo subscription. "
            "Includes: 5000 Buzz/mo, early access to new models, NSFW content unlocked, "
            "priority generation queue, ad-free experience. "
            "Key benefit: access to 100K+ community-trained LoRAs for style/character matching. "
            "Download LoRAs to run self-hosted — zero per-inference cost after download."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # PICSART API  — 20+ model hub; good for B2B integrations
    # signup: picsart.io  |  api_key_env: PICSART_API_KEY
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="picsart",
        model_id="picsart-hub-generation",
        price_per_image=0.02,
        billing_model="per_credit",
        resolution_options=["512x512", "1024x1024"],
        supports_inpainting=True,
        latency_seconds=4.0,
        signup_url="https://picsart.io",
        pricing_url="https://picsart.io/pricing",
        notes=(
            "AI Providers Hub with 20+ models under one API. "
            "Image editing tools: background removal, upscaling, style transfer. "
            "$0.01/edit for image transforms."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # AZURE AI FOUNDRY  — Model Catalog serverless endpoints
    # signup: ai.azure.com  |  sdk: azure-ai-inference (pip install azure-ai-inference)
    # api_key_env: AZURE_INFERENCE_CREDENTIAL
    # api_base: https://<project>.services.ai.azure.com/models
    #
    # IMPORTANT — credit eligibility:
    #   Third-party Marketplace models (FLUX, Stability AI) are billed via
    #   Azure Marketplace, NOT Azure consumption — startup credits do NOT cover them.
    #   Only Azure OpenAI (Microsoft-owned) models are credit-eligible.
    #   Self-hosted VMs ARE credit-eligible (see azure_selfhosted entries above).
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="azure_foundry",
        model_id="black-forest-labs/flux-1-pro",
        price_per_image=0.055,  # Azure Marketplace rate; verify at ai.azure.com
        billing_model="per_image",
        resolution_options=["1024x1024", "1440x1440", "1920x1080"],
        supports_lora=False,
        latency_seconds=8.0,
        signup_url="https://ai.azure.com",
        pricing_url="https://ai.azure.com/explore/models/flux-1-pro/pulaski/BlackForestLabs",
        credit_programs=[],  # Azure Marketplace billing — startup credits NOT applicable
        notes=(
            "FLUX.1 [pro] via Azure AI Foundry Model Catalog serverless endpoint. "
            "SDK: pip install azure-ai-inference. "
            "Billed via Azure Marketplace — NOT covered by Azure startup credits. "
            "Endpoint: https://<project>.services.ai.azure.com/models. "
            "For credit-eligible image gen on Azure: use azure_selfhosted SDXL instead."
        ),
    ),
    ImageGenPricing(
        provider="azure_foundry",
        model_id="black-forest-labs/flux-1-1-pro",
        price_per_image=0.04,  # Azure Marketplace rate; verify at ai.azure.com
        billing_model="per_image",
        resolution_options=["1024x1024", "1440x1440", "1920x1080"],
        supports_lora=False,
        latency_seconds=6.0,
        signup_url="https://ai.azure.com",
        pricing_url="https://ai.azure.com/explore/models/flux-1-1-pro/pulaski/BlackForestLabs",
        credit_programs=[],  # Azure Marketplace billing — startup credits NOT applicable
        notes=(
            "FLUX.1.1 [pro] via Azure AI Foundry serverless. Faster than FLUX.1 [pro]. "
            "Billed via Azure Marketplace — NOT covered by Azure startup credits. "
            "Use for quality-critical pages where Runware/Together quality is insufficient."
        ),
    ),
    ImageGenPricing(
        provider="azure_foundry",
        model_id="black-forest-labs/flux-1-kontext",
        price_per_image=0.04,  # Azure Marketplace rate; verify at ai.azure.com
        billing_model="per_image",
        resolution_options=["1024x1024", "1440x1440"],
        supports_inpainting=True,
        supports_lora=False,  # no LoRA needed — in-context character reference
        latency_seconds=8.0,
        signup_url="https://ai.azure.com",
        pricing_url="https://ai.azure.com/explore/models/flux-kontext-pro/pulaski/BlackForestLabs",
        credit_programs=[],  # Azure Marketplace billing — startup credits NOT applicable
        notes=(
            "FLUX.1 Kontext: multimodal in-context image editing — PIPELINE SIMPLIFICATION OPPORTUNITY. "
            "Pass a reference photo of the child + prompt; model edits/generates with consistent character "
            "WITHOUT requiring LoRA fine-tuning. ~8x faster than prior FLUX at 1024x1024. "
            "Could replace per-child LoRA for Book 1 and 2 (before character-specific LoRA matures). "
            "Inpainting: re-run with masked region + edit instruction (no separate inpaint model needed). "
            "Billed via Azure Marketplace — NOT covered by Azure startup credits. "
            "CRITICAL: test character consistency across 20 pages before committing to this path."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # AZURE OPENAI  — GPT-image-1 (Microsoft-owned, startup-credit-eligible)
    # signup: portal.azure.com  |  sdk: openai (pip install openai)
    # api_key_env: AZURE_OPENAI_API_KEY
    # api_base: https://<resource>.cognitiveservices.azure.com/openai/deployments/
    #           <deployment>/images/generations?api-version=2025-04-01-preview
    #
    # CREDIT NOTE: Azure OpenAI is Microsoft-owned — covered by startup credits.
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="azure_openai",
        model_id="gpt-image-1",
        price_per_image=0.04,  # standard quality 1024x1024; HD = $0.17/image
        billing_model="per_image",
        resolution_options=["1024x1024", "1792x1024", "1024x1792"],
        supports_inpainting=True,
        latency_seconds=10.0,
        signup_url="https://portal.azure.com",
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/",
        credit_programs=["microsoft_self_service", "microsoft_co_sell"],
        notes=(
            "GPT-image-1 via Azure OpenAI — covered by Azure startup credits. "
            "Same model as OpenAI's gpt-image-1 but billed against Azure credits. "
            "Pricing: low-quality $0.01, standard $0.04, HD $0.17 (1024x1024). "
            "SDK: standard openai Python package with AzureOpenAI client. "
            "API: https://<resource>.cognitiveservices.azure.com/openai/deployments/"
            "<deployment>/images/generations?api-version=2025-04-01-preview. "
            "$5K credits = 125K standard images. $10K (both entities) = 250K images. "
            "Inpainting supported. Strong photorealism, no LoRA."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # UPSCALING / BATCH PRINT PREP  — final proof-to-print-ready pipeline
    # Used AFTER variant selection, BEFORE sending to printer.
    # Batch upscaling amortises GPU cost: run overnight / off-peak.
    # ══════════════════════════════════════════════════════════════════════
    ImageGenPricing(
        provider="google",
        model_id="imagen-upscaler-batch",
        price_per_image=0.003,  # Vertex AI upscaling; verify at cloud.google.com/vertex-ai/generative-ai/pricing
        billing_model="per_image",
        resolution_options=["2048x2048", "4096x4096"],
        latency_seconds=15.0,
        signup_url="https://cloud.google.com/free",
        pricing_url="https://cloud.google.com/vertex-ai/generative-ai/pricing",
        credit_programs=["google_cloud_start", "google_cloud_scale_ai"],
        notes=(
            "Vertex AI Imagen upscaler for batch print-ready upscaling. "
            "Run after user approves final page selection — not in the hot path. "
            "GCP credits eligible: $0.003/image x 20 pages = $0.06/book for print prep. "
            "Batch API: submit all 20 pages as a job → retrieve when done (no latency pressure). "
            "Output: 4096x4096 suitable for 8x10in print at 300dpi."
        ),
    ),
    ImageGenPricing(
        provider="replicate",
        model_id="nightmareai/real-esrgan",
        price_per_image=0.002,  # per-second GPU billing; ~0.5s typical
        billing_model="per_second",
        resolution_options=["2x", "4x", "8x upscale"],
        latency_seconds=2.0,
        signup_url="https://replicate.com/signin",
        pricing_url="https://replicate.com/nightmareai/real-esrgan",
        notes=(
            "Real-ESRGAN upscaler on Replicate. 4x upscale: 1024 -> 4096px. "
            "~$0.002/image at standard resolution — cheaper than Imagen upscaler. "
            "No credit programs — pay-as-you-go only. "
            "Batch-friendly: call async via webhook, no timeout pressure. "
            "Use for final proof-to-print-ready upscaling before sending to print partner."
        ),
    ),
    ImageGenPricing(
        provider="aws_selfhosted",
        model_id="real-esrgan-on-g5xlarge-batch",
        price_per_image=0.0008,  # g5.xlarge spot $0.30/hr / ~375 upscales/hr
        billing_model="per_second",
        resolution_options=["2x", "4x upscale"],
        latency_seconds=8.0,
        signup_url="https://aws.amazon.com/ec2/",
        pricing_url="https://aws.amazon.com/ec2/pricing/on-demand/",
        credit_programs=["aws_activate"],
        notes=(
            "Self-hosted Real-ESRGAN batch upscaler on g5.xlarge spot via AWS credits. "
            "~375 upscales/hr on A10G = $0.0008/image. "
            "$100K AWS credits = 125M upscale ops (more than enough for entire print run). "
            "Run as SQS-triggered Lambda or batch job: approved pages queued after user sign-off, "
            "GPU spins up, processes all 20 pages, pushes hi-res to S3, triggers print order. "
            "Zero latency pressure — user never waits for upscaling in the UI."
        ),
    ),
]


# ---------------------------------------------------------------------------
# LoRA / fine-tuning catalogue
# ---------------------------------------------------------------------------

FINETUNE_MODELS: list[FinetunePricing] = [
    # ══════════════════════════════════════════════════════════════════════
    # REPLICATE  — best API-driven LoRA pipeline; under $2/run; under 2 min
    # Train via API → LoRA hosted on Replicate → inference at $0.003-0.055/image
    # Key for BookCreator: async queue, one run per child character
    # ══════════════════════════════════════════════════════════════════════
    FinetunePricing(
        provider="replicate",
        service_id="replicate/fast-flux-trainer",
        base_models=["Flux Dev", "Flux Schnell"],
        method="lora",
        typical_cost_usd=1.50,
        price_model="per_second",
        price_per_unit=0.0122,  # per GPU-second on H100
        min_images=5,
        latency_minutes=2.0,
        inference_cost_per_image=0.003,
        inference_via="same_platform",
        signup_url="https://replicate.com/signin",
        pricing_url="https://replicate.com/replicate/fast-flux-trainer/train",
        notes=(
            "< 2 min training on 8x H100. < $2/run typical. "
            "LoRA weights downloadable (50MB) or deployed to Replicate endpoint. "
            "API-driven: POST to /predictions → webhook when done. "
            "Perfect for async BookCreator pipeline: train after first order, use from book 2+."
        ),
    ),
    FinetunePricing(
        provider="replicate",
        service_id="ostris/flux-dev-lora-trainer",
        base_models=["Flux Dev"],
        method="lora",
        typical_cost_usd=2.50,
        price_model="per_second",
        price_per_unit=0.0122,
        min_images=5,
        latency_minutes=4.0,
        inference_cost_per_image=0.055,
        inference_via="same_platform",
        signup_url="https://replicate.com/signin",
        pricing_url="https://replicate.com/ostris/flux-dev-lora-trainer/train",
        notes="More control over training params. Slower but higher quality for portrait LoRAs.",
    ),
    FinetunePricing(
        provider="replicate",
        service_id="stability-ai/sdxl-lora-training",
        base_models=["SDXL 1.0"],
        method="lora",
        typical_cost_usd=0.80,
        price_model="per_second",
        price_per_unit=0.001528,  # A40 GPU rate
        min_images=5,
        latency_minutes=8.0,
        inference_cost_per_image=0.0032,
        inference_via="same_platform",
        signup_url="https://replicate.com/signin",
        pricing_url="https://replicate.com/pricing",
        notes="Cheapest fine-tuning option on Replicate. SDXL LoRA runs on A40.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # FAL.AI  — fixed per-step pricing; portrait-specialised trainer
    # Good alternative to Replicate; fixed pricing easier to budget
    # ══════════════════════════════════════════════════════════════════════
    FinetunePricing(
        provider="fal_ai",
        service_id="fal-ai/flux-lora-fast-training",
        base_models=["Flux Dev"],
        method="lora",
        typical_cost_usd=2.00,
        price_model="per_run",
        min_images=10,
        latency_minutes=5.0,
        inference_cost_per_image=0.025,
        inference_via="same_platform",
        signup_url="https://fal.ai/dashboard",
        pricing_url="https://fal.ai/models/fal-ai/flux-lora-fast-training",
        notes="Fixed ~$2/run. Good for consistent cost modelling.",
    ),
    FinetunePricing(
        provider="fal_ai",
        service_id="fal-ai/flux-lora-portrait-trainer",
        base_models=["Flux Dev"],
        method="lora",
        typical_cost_usd=2.40,  # 1000 steps minimum
        price_model="per_step",
        price_per_unit=0.0024,
        min_images=10,
        latency_minutes=6.0,
        inference_cost_per_image=0.025,
        inference_via="same_platform",
        signup_url="https://fal.ai/dashboard",
        pricing_url="https://fal.ai/models/fal-ai/flux-lora-portrait-trainer",
        notes=(
            "Specialised for portrait LoRA training. "
            "Minimum 1000 steps = $2.40. 2000 steps = $4.80. "
            "Key for BookCreator: portrait LoRA = child character consistency across pages."
        ),
    ),
    FinetunePricing(
        provider="fal_ai",
        service_id="fal-ai/flux-2-trainer",
        base_models=["Flux 2 Dev"],
        method="lora",
        typical_cost_usd=8.00,  # 1000 steps
        price_model="per_step",
        price_per_unit=0.008,
        min_images=10,
        latency_minutes=10.0,
        inference_cost_per_image=0.025,
        inference_via="same_platform",
        signup_url="https://fal.ai/dashboard",
        pricing_url="https://fal.ai/models/fal-ai/flux-2-trainer",
        notes="Flux 2 trainer — higher quality but 4x cost vs Flux 1 fast trainer.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # HUGGING FACE AUTOTRAIN  — free with HF account; self-service
    # Good for internal team experimentation; not production-API-driven
    # ══════════════════════════════════════════════════════════════════════
    FinetunePricing(
        provider="huggingface",
        service_id="autotrain-dreambooth-sdxl",
        base_models=["SDXL 1.0", "Stable Diffusion"],
        method="dreambooth",
        typical_cost_usd=0.0,  # free with HF Spaces compute allowance
        price_model="per_run",
        min_images=5,
        latency_minutes=20.0,
        inference_cost_per_image=0.0,
        inference_via="self_hosted",
        signup_url="https://huggingface.co/join",
        pricing_url="https://huggingface.co/docs/autotrain/dreambooth",
        notes=(
            "Free with HF Spaces compute (rate-limited). "
            "PRO tier ($9/mo) removes rate limits. "
            "Good for internal style experimentation. "
            "Not API-driven — manual UI or CLI, not suitable for per-customer automation."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # AWS SAGEMAKER JUMPSTART
    # Use with AWS Activate credits ($25K-$100K via NVIDIA Inception)
    # ══════════════════════════════════════════════════════════════════════
    FinetunePricing(
        provider="aws",
        service_id="sagemaker-jumpstart-sdxl-dreambooth",
        base_models=["SDXL 1.0"],
        method="dreambooth",
        typical_cost_usd=3.06,  # 1hr on p3.2xlarge
        price_model="per_hour",
        price_per_unit=3.06,  # p3.2xlarge on-demand; use spot for ~$0.92/hr
        min_images=10,
        latency_minutes=60.0,
        inference_cost_per_image=None,  # separate SageMaker endpoint cost
        inference_via="self_hosted",
        signup_url="https://aws.amazon.com/sagemaker/",
        pricing_url="https://aws.amazon.com/sagemaker/pricing/",
        notes=(
            "Use with AWS Activate credits. "
            "Spot pricing: ~$0.92/hr (70% discount) = $0.92/run. "
            "Best when you have AWS credits to burn. "
            "More setup than Replicate but credits offset cash cost."
        ),
    ),
    FinetunePricing(
        provider="aws",
        service_id="sagemaker-flux-lora-custom",
        base_models=["Flux Dev", "SDXL"],
        method="lora",
        typical_cost_usd=2.00,  # g5.xlarge spot ~$0.30/hr x ~6hr setup+train
        price_model="per_hour",
        price_per_unit=1.006,  # g5.xlarge on-demand; spot $0.30/hr
        min_images=5,
        latency_minutes=30.0,
        inference_via="self_hosted",
        signup_url="https://aws.amazon.com/sagemaker/",
        pricing_url="https://aws.amazon.com/sagemaker/pricing/",
        notes=(
            "Custom training script on SageMaker (not JumpStart). "
            "g5.xlarge spot ($0.30/hr) + S3 storage. "
            "Requires diffusers training script setup — more engineering. "
            "Good path once volume justifies dedicated infrastructure."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # GCP VERTEX AI  — custom training with diffusers
    # Use with Google for Startups Cloud credits ($2K-$350K)
    # ══════════════════════════════════════════════════════════════════════
    FinetunePricing(
        provider="gcp",
        service_id="vertex-ai-custom-training-lora",
        base_models=["SDXL", "Flux Dev", "Stable Diffusion"],
        method="lora",
        typical_cost_usd=1.50,  # ~2hr on L4 spot
        price_model="per_hour",
        price_per_unit=0.707,  # g2-standard-4 (L4) on-demand; spot ~$0.21/hr
        min_images=5,
        latency_minutes=30.0,
        inference_via="self_hosted",
        signup_url="https://cloud.google.com/free",
        pricing_url="https://cloud.google.com/vertex-ai/pricing",
        notes=(
            "Run diffusers LoRA training on Vertex AI custom job. "
            "L4 GPU spot: ~$0.21/hr. A100 spot: ~$1.10/hr. "
            "Sample notebooks: github.com/GoogleCloudPlatform/vertex-ai-samples. "
            "Use Google Startup credits ($2K self-service, up to $350K Scale AI)."
        ),
    ),
    FinetunePricing(
        provider="gcp",
        service_id="vertex-ai-imagen-fine-tuning",
        base_models=["Imagen 3"],
        method="full-finetune",
        typical_cost_usd=None,  # pricing not publicly listed; contact Google
        price_model="per_hour",
        min_images=100,
        inference_cost_per_image=0.04,
        inference_via="same_platform",
        signup_url="https://cloud.google.com/vertex-ai/generative-ai/docs/image/fine-tune-models",
        pricing_url="https://cloud.google.com/vertex-ai/generative-ai/pricing",
        notes=(
            "Fine-tune Imagen 3 on your own illustration style dataset. "
            "Subject fine-tuning (for character consistency) supported. "
            "Pricing not public — request via Google Cloud console. "
            "Requires 100+ images; output stays within Vertex AI."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # AZURE ML  — custom training; use with Azure for Startups credits ($5K)
    # ══════════════════════════════════════════════════════════════════════
    FinetunePricing(
        provider="azure",
        service_id="azure-ml-sdxl-dreambooth",
        base_models=["SDXL 1.0"],
        method="dreambooth",
        typical_cost_usd=2.00,
        price_model="per_hour",
        price_per_unit=3.673,  # NC24ads A100 v4 on-demand; spot $0.68/hr
        min_images=10,
        latency_minutes=30.0,
        inference_via="self_hosted",
        signup_url="https://azure.microsoft.com/en-us/products/machine-learning",
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/machine-learning/",
        notes=(
            "NC24ads A100 v4 spot: $0.68/hr — very competitive. "
            "Use Azure for Startups credits ($5K self-service per entity). "
            "Azure ML Pipelines for automated per-customer LoRA training. "
            "GitHub Copilot can be linked to Azure subscription."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # RUNPOD  — cheap GPU rental; good for self-managed training
    # ══════════════════════════════════════════════════════════════════════
    FinetunePricing(
        provider="runpod",
        service_id="runpod-a10g-lora",
        base_models=["SDXL", "Flux Dev", "Any"],
        method="lora",
        typical_cost_usd=0.67,  # 1hr A10G
        price_model="per_hour",
        price_per_unit=0.67,  # A10G community cloud rate; verify at runpod.io
        min_images=5,
        latency_minutes=30.0,
        inference_via="self_hosted",
        signup_url="https://www.runpod.io/",
        pricing_url="https://www.runpod.io/pricing",
        notes=(
            "Per-millisecond billing — stops the clock when idle. "
            "Good for batch training jobs. "
            "Community cloud pricing may vary; stable options cost more. "
            "GPU pods: any model you want, full control."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # VAST.AI  — spot GPU market; cheapest for bursty training workloads
    # ══════════════════════════════════════════════════════════════════════
    FinetunePricing(
        provider="vast_ai",
        service_id="vast-spot-a100-lora",
        base_models=["SDXL", "Flux Dev", "Any"],
        method="lora",
        typical_cost_usd=0.78,  # A100 80GB at benchmark spot price x 1hr
        price_model="per_hour",
        price_per_unit=0.78,  # benchmark A100 80GB spot; varies by market
        min_images=5,
        latency_minutes=20.0,
        inference_via="self_hosted",
        signup_url="https://vast.ai/",
        pricing_url="https://vast.ai/pricing",
        notes=(
            "Spot GPU marketplace: 40-65% cheaper than on-demand. "
            "A100 80GB benchmark $0.78/hr; H100 80GB benchmark $1.38/hr. "
            "Prices fluctuate with supply/demand — great for overnight batch training. "
            "Not reliable for latency-sensitive inference."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # CIVITAI  — source for pre-trained LoRAs (not a training platform)
    # Key value: 100K+ style/character LoRAs to use as starting points
    # ══════════════════════════════════════════════════════════════════════
    FinetunePricing(
        provider="civitai",
        service_id="civitai-lora-library",
        base_models=["SDXL", "Flux Dev", "SD 1.5", "Pony Diffusion"],
        method="lora",
        typical_cost_usd=0.0,  # download is free (some require CivitAI account)
        price_model="per_run",
        min_images=None,
        latency_minutes=0.0,
        inference_via="self_hosted",
        signup_url="https://civitai.com/user/account",
        pricing_url="https://civitai.com/pricing",
        notes=(
            "100K+ community LoRAs available for download. "
            "Strategy for BookCreator: "
            "1) Find a children's book illustration style LoRA on CivitAI "
            "2) Use it as the style base "
            "3) Train a second LoRA on top for the specific child character "
            "This layering (style LoRA + character LoRA) is the core of BookCreator character consistency. "
            "CivitAI API: api.civitai.com/v1/models — search/filter/download programmatically. "
            "CivitAI Red ($15/mo): early access to new models + cloud generation credits."
        ),
    ),
]


# ---------------------------------------------------------------------------
# GPU cloud instances for self-hosted inference
# ---------------------------------------------------------------------------

GPU_CLOUD_INSTANCES: list[GPUInstancePricing] = [
    # ══════════════════════════════════════════════════════════════════════
    # AWS EC2  — use with AWS Activate credits ($25K-$100K via NVIDIA Inception)
    # ══════════════════════════════════════════════════════════════════════
    GPUInstancePricing(
        provider="aws",
        instance_id="g4dn.xlarge",
        gpu_type="NVIDIA T4",
        vram_gb=16,
        price_per_hour=0.526,
        spot_price_per_hour=0.158,
        vcpus=4,
        ram_gb=16,
        suitable_for="SDXL, SD3 Medium, small Flux variants (≤16GB VRAM)",
        pricing_url="https://aws.amazon.com/ec2/pricing/on-demand/",
        credit_programs=["aws_activate"],
        notes="Entry-level GPU. Spot saves 70%. Good for SDXL at moderate volume.",
    ),
    GPUInstancePricing(
        provider="aws",
        instance_id="g5.xlarge",
        gpu_type="NVIDIA A10G",
        vram_gb=24,
        price_per_hour=1.006,
        spot_price_per_hour=0.302,
        vcpus=4,
        ram_gb=16,
        suitable_for="SDXL, Flux Dev, SD3 (≤24GB VRAM) — best price/performance for BookCreator",
        pricing_url="https://aws.amazon.com/ec2/pricing/on-demand/",
        credit_programs=["aws_activate"],
        notes=(
            "Best AWS instance for BookCreator self-hosting. "
            "Spot: $0.30/hr = ~200 imgs/hr SDXL = $0.0015/image effective. "
            "$100K AWS Activate = 66M images. 24GB VRAM handles Flux Dev + inpainting."
        ),
    ),
    GPUInstancePricing(
        provider="aws",
        instance_id="g5.2xlarge",
        gpu_type="NVIDIA A10G",
        vram_gb=24,
        price_per_hour=1.212,
        spot_price_per_hour=0.364,
        vcpus=8,
        ram_gb=32,
        suitable_for="Same as g5.xlarge but more CPU for preprocessing + postprocessing",
        pricing_url="https://aws.amazon.com/ec2/pricing/on-demand/",
        credit_programs=["aws_activate"],
        notes="Use when CPU-bound (image resizing, face detection, order processing) alongside GPU.",
    ),
    GPUInstancePricing(
        provider="aws",
        instance_id="p3.2xlarge",
        gpu_type="NVIDIA V100",
        vram_gb=16,
        price_per_hour=3.060,
        spot_price_per_hour=0.918,
        vcpus=8,
        ram_gb=61,
        suitable_for="SDXL, legacy models — prefer g5 for new deployments",
        pricing_url="https://aws.amazon.com/ec2/pricing/on-demand/",
        credit_programs=["aws_activate"],
        notes="Older hardware; g5.xlarge gives better price/performance for inference.",
    ),
    GPUInstancePricing(
        provider="aws",
        instance_id="p4d.24xlarge",
        gpu_type="NVIDIA A100 40GB",
        vram_gb=40,
        price_per_hour=32.77,
        spot_price_per_hour=9.83,
        gpu_count=8,
        vcpus=96,
        ram_gb=1152,
        suitable_for="Multi-model serving, Flux full-precision, enterprise batch (needs ≥24GB)",
        pricing_url="https://aws.amazon.com/ec2/pricing/on-demand/",
        credit_programs=["aws_activate"],
        notes=(
            "33% price reduction in June 2025. "
            "Spot: $9.83/hr for 8x A100 = $1.23/A100-hr. "
            "Use when serving 10+ concurrent models."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # GCP Compute Engine  — use with Google for Startups credits
    # ══════════════════════════════════════════════════════════════════════
    GPUInstancePricing(
        provider="gcp",
        instance_id="n1-standard-4+T4",
        gpu_type="NVIDIA T4",
        vram_gb=16,
        price_per_hour=0.35,
        spot_price_per_hour=0.10,
        vcpus=4,
        ram_gb=15,
        suitable_for="SDXL, SD3 (≤16GB VRAM)",
        pricing_url="https://cloud.google.com/compute/gpus-pricing",
        credit_programs=["google_cloud_start", "google_cloud_scale_ai"],
        notes="T4 + n1 instance. Spot: 60-91% discount varies by region.",
    ),
    GPUInstancePricing(
        provider="gcp",
        instance_id="g2-standard-4",
        gpu_type="NVIDIA L4",
        vram_gb=24,
        price_per_hour=0.707,
        spot_price_per_hour=0.212,
        vcpus=4,
        ram_gb=16,
        suitable_for="SDXL, Flux Dev (≤24GB) — best GCP price/performance",
        pricing_url="https://cloud.google.com/compute/gpus-pricing",
        credit_programs=["google_cloud_start", "google_cloud_scale_ai"],
        notes=(
            "Newer L4 architecture. ~30% cheaper than g5.xlarge AWS equivalent. "
            "Spot $0.21/hr / ~200 imgs/hr = $0.001/image. "
            "$2K GCP Start credits = 2M images."
        ),
    ),
    GPUInstancePricing(
        provider="gcp",
        instance_id="a2-highgpu-1g",
        gpu_type="NVIDIA A100 40GB",
        vram_gb=40,
        price_per_hour=4.50,
        spot_price_per_hour=1.35,
        vcpus=12,
        ram_gb=85,
        suitable_for="Flux full-precision, multi-model, large batch (≥24GB)",
        pricing_url="https://cloud.google.com/compute/gpus-pricing",
        credit_programs=["google_cloud_start", "google_cloud_scale_ai"],
        notes="Google Startup Scale credits ($350K) can cover significant A2 usage.",
    ),
    GPUInstancePricing(
        provider="gcp",
        instance_id="a3-highgpu-1g",
        gpu_type="NVIDIA H100 80GB",
        vram_gb=80,
        price_per_hour=11.06,
        spot_price_per_hour=3.32,
        vcpus=26,
        ram_gb=234,
        suitable_for="Flux full, enterprise multi-model, LoRA training at scale",
        pricing_url="https://cloud.google.com/compute/gpus-pricing",
        credit_programs=["google_cloud_scale_ai"],
        notes="H100 SXM5 on GCP. Use for training — overkill for SDXL inference.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # Azure  — use with Azure for Startups credits ($5K self-service)
    # ══════════════════════════════════════════════════════════════════════
    GPUInstancePricing(
        provider="azure",
        instance_id="NC4as_T4_v3",
        gpu_type="NVIDIA T4",
        vram_gb=16,
        price_per_hour=0.526,
        spot_price_per_hour=0.105,
        vcpus=4,
        ram_gb=28,
        suitable_for="SDXL, SD3 (≤16GB VRAM)",
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/virtual-machines/",
        credit_programs=["microsoft_self_service", "microsoft_investor_offer"],
        notes="Azure T4. Spot: ~80% discount. Good use of $5K Azure startup credits.",
    ),
    GPUInstancePricing(
        provider="azure",
        instance_id="NC6s_v3",
        gpu_type="NVIDIA V100",
        vram_gb=16,
        price_per_hour=2.70,
        vcpus=6,
        ram_gb=56,
        suitable_for="SDXL, legacy models — prefer NC_T4 for new deployments",
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/virtual-machines/",
        credit_programs=["microsoft_self_service", "microsoft_investor_offer"],
        notes="Older V100; use startup credits here as last resort.",
    ),
    GPUInstancePricing(
        provider="azure",
        instance_id="NC24ads_A100_v4",
        gpu_type="NVIDIA A100 80GB",
        vram_gb=80,
        price_per_hour=3.673,
        spot_price_per_hour=0.679,
        vcpus=24,
        ram_gb=220,
        suitable_for="Flux full, multi-model, LoRA training (≥24GB)",
        pricing_url="https://azure.microsoft.com/en-us/pricing/details/virtual-machines/",
        credit_programs=["microsoft_self_service", "microsoft_investor_offer"],
        notes=(
            "Best Azure GPU for image gen. Spot: $0.68/hr. "
            "~600 imgs/hr SDXL = $0.0011/image. "
            "$5K Azure credits = 4.5M images. Both entities ($10K) = 9M images. "
            "Azure has no native image gen API — self-hosting is the only credits path."
        ),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # Lambda Labs  — no egress fees; transparent pricing; great for sustained use
    # signup: lambda.ai  |  ssh key access; OpenAI-compat inference API available
    # ══════════════════════════════════════════════════════════════════════
    GPUInstancePricing(
        provider="lambda",
        instance_id="a10-24gb",
        gpu_type="NVIDIA A10",
        vram_gb=24,
        price_per_hour=0.75,
        vcpus=30,
        ram_gb=200,
        suitable_for="SDXL, Flux Dev (≤24GB) — best Lambda option for BookCreator",
        pricing_url="https://lambda.ai/pricing",
        notes="No egress fees. $0.75/hr flat. Good for dedicated BookCreator inference server.",
    ),
    GPUInstancePricing(
        provider="lambda",
        instance_id="a100-40gb",
        gpu_type="NVIDIA A100 40GB",
        vram_gb=40,
        price_per_hour=1.10,
        vcpus=30,
        ram_gb=200,
        suitable_for="Flux Dev full, multi-model serving (≤40GB)",
        pricing_url="https://lambda.ai/pricing",
        notes="No egress. Best A100 price-per-hour among major providers.",
    ),
    GPUInstancePricing(
        provider="lambda",
        instance_id="h100-80gb",
        gpu_type="NVIDIA H100 80GB",
        vram_gb=80,
        price_per_hour=2.49,
        vcpus=26,
        ram_gb=200,
        suitable_for="Flux full-precision, multi-model, LoRA training",
        pricing_url="https://lambda.ai/pricing",
        notes=(
            "No egress fees. ~$2.49/hr flat. "
            "Best H100 pricing among major cloud providers. "
            "B200 also available at $4.99/hr (2x VRAM, 3x faster training)."
        ),
    ),
    GPUInstancePricing(
        provider="lambda",
        instance_id="b200-192gb",
        gpu_type="NVIDIA B200",
        vram_gb=192,
        price_per_hour=4.99,
        vcpus=36,
        ram_gb=400,
        suitable_for="Extreme batch inference, frontier model hosting, fast LoRA training",
        pricing_url="https://lambda.ai/pricing",
        notes="Newest GPU architecture. 15x faster inference vs H100 for some workloads.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # RunPod  — per-millisecond billing; community + secure options
    # signup: runpod.io  |  ssh + API access; good for bursty workloads
    # ══════════════════════════════════════════════════════════════════════
    GPUInstancePricing(
        provider="runpod",
        instance_id="rtx-3090-24gb",
        gpu_type="NVIDIA RTX 3090",
        vram_gb=24,
        price_per_hour=0.50,
        vcpus=8,
        ram_gb=50,
        suitable_for="SDXL, Flux Dev (≤24GB) — cheapest 24GB option",
        pricing_url="https://www.runpod.io/pricing",
        notes="Community cloud — variable availability. Per-millisecond billing reduces idle waste.",
    ),
    GPUInstancePricing(
        provider="runpod",
        instance_id="a10g-24gb",
        gpu_type="NVIDIA A10G",
        vram_gb=24,
        price_per_hour=0.67,
        vcpus=12,
        ram_gb=50,
        suitable_for="SDXL, Flux Dev, inpainting (≤24GB)",
        pricing_url="https://www.runpod.io/pricing",
        notes="Good alternative to AWS g5 at 30% lower cost.",
    ),
    GPUInstancePricing(
        provider="runpod",
        instance_id="a100-pcie-40gb",
        gpu_type="NVIDIA A100 PCIe 40GB",
        vram_gb=40,
        price_per_hour=1.39,
        vcpus=16,
        ram_gb=100,
        suitable_for="Flux Dev full, multi-model, LoRA training",
        pricing_url="https://www.runpod.io/pricing",
        notes="Stable option (not community). Per-millisecond billing.",
    ),
    GPUInstancePricing(
        provider="runpod",
        instance_id="h100-sxm-80gb",
        gpu_type="NVIDIA H100 SXM",
        vram_gb=80,
        price_per_hour=2.69,
        vcpus=20,
        ram_gb=200,
        suitable_for="Flux full, enterprise batch, LoRA training at scale",
        pricing_url="https://www.runpod.io/pricing",
        notes="Community: $1.99/hr (variable). Stable: $2.69/hr. Best for training jobs.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # Vast.ai  — spot GPU marketplace; 40-65% cheaper than on-demand
    # signup: vast.ai  |  market-rate pricing; best for overnight batch
    # ══════════════════════════════════════════════════════════════════════
    GPUInstancePricing(
        provider="vast_ai",
        instance_id="t4-16gb-spot",
        gpu_type="NVIDIA T4",
        vram_gb=16,
        price_per_hour=0.15,  # benchmark; range $0.15-0.50
        suitable_for="SDXL, SD3 (≤16GB) — ultra-cheap for overnight batch",
        pricing_url="https://vast.ai/pricing",
        notes="Market-driven. $0.15-0.50/hr range. Best for bulk non-urgent generation.",
    ),
    GPUInstancePricing(
        provider="vast_ai",
        instance_id="a10g-24gb-spot",
        gpu_type="NVIDIA A10G",
        vram_gb=24,
        price_per_hour=0.40,  # benchmark; range $0.40-1.50
        suitable_for="SDXL, Flux Dev (≤24GB)",
        pricing_url="https://vast.ai/pricing",
        notes="Range $0.40-1.50/hr. Shop for best rates. Good for LoRA training jobs.",
    ),
    GPUInstancePricing(
        provider="vast_ai",
        instance_id="a100-80gb-spot",
        gpu_type="NVIDIA A100 80GB",
        vram_gb=80,
        price_per_hour=0.78,  # benchmark; range $0.78-5.07
        suitable_for="Flux full, multi-model, training",
        pricing_url="https://vast.ai/pricing",
        notes="Benchmark $0.78/hr — 40-65% cheaper than AWS on-demand. Wide availability.",
    ),
    GPUInstancePricing(
        provider="vast_ai",
        instance_id="h100-80gb-spot",
        gpu_type="NVIDIA H100 80GB",
        vram_gb=80,
        price_per_hour=1.38,  # benchmark; range $1.38-11.01
        suitable_for="LoRA training, Flux full, enterprise batch",
        pricing_url="https://vast.ai/pricing",
        notes="Benchmark $1.38/hr. Significant price variation — bid aggressively for training.",
    ),
    # ══════════════════════════════════════════════════════════════════════
    # CoreWeave  — no egress fees; enterprise SLAs; good for sustained GPU
    # signup: coreweave.com  |  Kubernetes-native; custom pricing for scale
    # ══════════════════════════════════════════════════════════════════════
    GPUInstancePricing(
        provider="coreweave",
        instance_id="a100-80gb-nvlink",
        gpu_type="NVIDIA A100 80GB NVLink",
        vram_gb=80,
        price_per_hour=2.21,  # GPU only; add CPU/RAM ~$0.80/hr typical
        suitable_for="Flux full, multi-model, training — no egress fees",
        pricing_url="https://www.coreweave.com/pricing",
        notes=(
            "No egress fees. No IOPS charges. Free internal transfers. "
            "Better for sustained workloads vs spot markets. "
            "Custom volume pricing for >$10K/mo spend."
        ),
    ),
    GPUInstancePricing(
        provider="coreweave",
        instance_id="h100-pcie-80gb",
        gpu_type="NVIDIA H100 PCIe",
        vram_gb=80,
        price_per_hour=4.25,
        suitable_for="Fast LoRA training, frontier model inference",
        pricing_url="https://www.coreweave.com/pricing",
        notes="Full 8x H100 HGX nodes available at $49/hr. Enterprise SLA.",
    ),
]


# ---------------------------------------------------------------------------
# Batch-first pipeline strategy
# ---------------------------------------------------------------------------
# Golden rule: anything NOT in the user's direct wait path should be batched.
# Batching reduces cost by: (a) enabling spot/preemptible instances, (b) allowing
# off-peak scheduling, (c) reducing per-job cold-start amortisation overhead.
#
# Operations that CAN be batched (user does not wait):
#   - LoRA training            → SQS → async Replicate webhook
#   - Batch upscaling          → SQS → g5.xlarge spot job (after approval)
#   - Preview email generation → overnight batch (new template release)
#   - S3 cleanup               → S3 lifecycle rule (free)
#   - LoRA weight backup       → S3 event → async replication
#
# Operations that CANNOT be batched (user waits in browser):
#   - Initial variant generation  → must be <30s (parallel async calls help)
#   - Inpainting refinement       → must be <15s (single call, per user action)
#
# Spot instance strategy for batch jobs:
#   - Keep instance at 0 during off hours
#   - SQS triggers auto-start via Lambda → EC2 RunInstances
#   - Interruption handler: checkpoint job state → requeue to SQS → terminate
#   - AWS g5.xlarge spot $0.30/hr vs $1.19 on-demand = 75% savings on batch
# ---------------------------------------------------------------------------

BATCH_PIPELINE: dict[str, dict] = {
    "lora_training": {
        "trigger": "after_book1_payment",
        "queue": "SQS",
        "worker": "replicate_webhook",
        "provider": "replicate",
        "model": "replicate/fast-flux-trainer",
        "latency": "async_2min",
        "batchable": True,
        "user_waits": False,
        "spot_eligible": True,
        "cost_per_job": 1.50,
        "notes": "Train per-child LoRA after Book 1 delivered. Use for Book 2+ generation.",
    },
    "variant_generation": {
        "trigger": "user_opens_page_review",
        "queue": "parallel_async",
        "provider": "runware",
        "model": "runware:101@1",  # SDXL + LoRA
        "latency": "realtime_30s",
        "batchable": False,  # user waits — parallel API calls, not batch queue
        "user_waits": True,
        "spot_eligible": False,
        "cost_per_job": 0.0026 * 80,  # 20 pages x 4 variants
        "notes": "80 parallel image calls. Fire all at once; await all; render grid.",
    },
    "inpainting_refinement": {
        "trigger": "user_clicks_refine",
        "queue": "direct_api",
        "provider": "fal_ai",
        "model": "fal-ai/flux/dev/image-to-image",
        "latency": "realtime_15s",
        "batchable": False,  # synchronous with user action
        "user_waits": True,
        "spot_eligible": False,
        "cost_per_job": 0.025,
        "notes": "Only for users who click Refine. Optional upgrade flow.",
    },
    "batch_upscaling": {
        "trigger": "all_pages_approved",
        "queue": "SQS",
        "worker": "g5xlarge_spot_job",
        "provider": "aws_selfhosted",
        "model": "real-esrgan-on-g5xlarge-batch",
        "latency": "async_5min_for_20pages",
        "batchable": True,
        "user_waits": False,
        "spot_eligible": True,
        "cost_per_job": 0.0008 * 20,  # 20 pages x $0.0008/upscale
        "notes": (
            "4x upscale 1024->4096px per page. Spin up spot GPU, process all 20 pages, "
            "push hi-res to S3, trigger print order, terminate instance. "
            "User gets 'Your book is being printed!' notification, not 'please wait'."
        ),
    },
    "preview_email_gen": {
        "trigger": "new_template_published",
        "queue": "SQS_fanout",
        "worker": "lambda_batch",
        "provider": "runware",
        "model": "runware:101@1",
        "latency": "async_overnight",
        "batchable": True,
        "user_waits": False,
        "spot_eligible": True,
        "cost_per_job": 0.0026,  # 1 preview page per child per template
        "notes": (
            "For each new book template: generate 1 personalized preview page per saved character. "
            "Send email with preview image + 'Finish your book' CTA. "
            "Run overnight at batch rates. SQS fan-out: 1 message per child."
        ),
    },
}

# ---------------------------------------------------------------------------
# Table rendering functions
# ---------------------------------------------------------------------------


def image_gen_table(max_price: float | None = None, *, lora_only: bool = False) -> str:
    """
    Render IMAGE_GEN_MODELS sorted by price per image.

    Args:
        max_price:  filter to models at or below this price per image.
        lora_only:  if True, only show models that accept LoRA weights.
    """
    rows = IMAGE_GEN_MODELS
    if max_price is not None:
        rows = [r for r in rows if r.price_per_image <= max_price]
    if lora_only:
        rows = [r for r in rows if r.supports_lora]
    rows = sorted(rows, key=lambda r: r.price_per_image)

    header = (
        f"{'Provider':<16} {'Model':<40} {'$/img':>8} {'Inpaint':>8} {'LoRA':>6} {'Latency':>8}"
    )
    sep = "-" * len(header)
    lines = [f"### Image Generation — {len(rows)} models (sorted by price/image)", "", header, sep]
    for r in rows:
        inpaint = "yes" if r.supports_inpainting else "-"
        lora = "yes" if r.supports_lora else "-"
        lat = f"{r.latency_seconds:.0f}s" if r.latency_seconds else "-"
        model_short = r.model_id[:38] if len(r.model_id) > 38 else r.model_id
        lines.append(
            f"{r.provider:<16} {model_short:<40} {r.price_per_image:>8.4f} "
            f"{inpaint:>8} {lora:>6} {lat:>8}"
        )
    lines.append("")
    lines.append("Prices USD/image at standard resolution (1024x1024). Verify at pricing URLs.")
    return "\n".join(lines)


def finetune_table() -> str:
    """Render FINETUNE_MODELS sorted by typical cost per run."""
    rows = sorted(
        [r for r in FINETUNE_MODELS if r.typical_cost_usd is not None],
        key=lambda r: r.typical_cost_usd,  # type: ignore[arg-type]
    )
    header = (
        f"{'Provider':<16} {'Service':<40} {'$/run':>8} {'Method':<14} {'Min imgs':>9} {'Time':>8}"
    )
    sep = "-" * len(header)
    lines = ["### LoRA Fine-tuning Platforms (sorted by cost/run)", "", header, sep]
    for r in rows:
        cost = f"${r.typical_cost_usd:.2f}" if r.typical_cost_usd else "contact"
        method = r.method[:12]
        mins = str(r.min_images) if r.min_images else "-"
        lat = f"{r.latency_minutes:.0f}min" if r.latency_minutes else "-"
        svc = r.service_id[:38] if len(r.service_id) > 38 else r.service_id
        lines.append(f"{r.provider:<16} {svc:<40} {cost:>8} {method:<14} {mins:>9} {lat:>8}")
    lines.append("")
    lines.append("Cost is per training run at recommended settings. Verify at pricing URLs.")
    return "\n".join(lines)


def gpu_cloud_table(
    max_vram_gb: int | None = None,
    min_vram_gb: int | None = None,
    spot_only: bool = False,
) -> str:
    """
    Render GPU_CLOUD_INSTANCES sorted by effective hourly cost.

    Args:
        max_vram_gb:  filter to instances with at most this VRAM.
        min_vram_gb:  filter to instances with at least this VRAM.
        spot_only:    if True, sort by spot price and only show instances with spot pricing.
    """
    rows = GPU_CLOUD_INSTANCES
    if max_vram_gb is not None:
        rows = [r for r in rows if r.vram_gb <= max_vram_gb]
    if min_vram_gb is not None:
        rows = [r for r in rows if r.vram_gb >= min_vram_gb]
    if spot_only:
        rows = [r for r in rows if r.spot_price_per_hour is not None]
        rows = sorted(rows, key=lambda r: r.spot_price_per_hour)  # type: ignore[arg-type]
    else:
        rows = sorted(rows, key=lambda r: r.price_per_hour)

    price_label = "Spot/hr" if spot_only else "$/hr"
    header = (
        f"{'Provider':<12} {'Instance':<24} {'GPU':<22} {'VRAM':>6} "
        f"{price_label:>8} {'On-demand':>10}"
    )
    sep = "-" * len(header)
    lines = [f"### GPU Cloud Instances — {len(rows)} options", "", header, sep]
    for r in rows:
        display_price = r.spot_price_per_hour if spot_only else r.price_per_hour
        spot_str = f"${r.spot_price_per_hour:.3f}" if r.spot_price_per_hour else "-"
        od_str = f"${r.price_per_hour:.3f}"
        gpu_short = r.gpu_type[:20] if len(r.gpu_type) > 20 else r.gpu_type
        inst_short = r.instance_id[:22] if len(r.instance_id) > 22 else r.instance_id
        lines.append(
            f"{r.provider:<12} {inst_short:<24} {gpu_short:<22} {r.vram_gb:>5}GB "
            f"${display_price:>7.3f} {od_str if spot_only else spot_str:>10}"
        )
    lines.append("")
    lines.append("SDXL: ≥8GB. Flux Dev: ≥12GB. Flux full-precision: ≥24GB. Multi-model: ≥40GB.")
    return "\n".join(lines)


def startup_credits_image_gen_analysis() -> str:
    """
    Show how far startup cloud credits stretch for image generation.

    Compares API-based image gen vs self-hosted GPU inference for each
    credit program, ranked by images-per-credit-dollar.
    """
    # (program_label, credit_usd, description)
    programs = [
        ("AWS Activate (NVIDIA Inception)", 100_000, "aws_activate"),
        ("AWS Activate (Portfolio tier)", 25_000, "aws_activate"),
        ("GCP Scale AI", 350_000, "google_cloud_scale_ai"),
        ("GCP Start", 2_000, "google_cloud_start"),
        ("Azure (both entities)", 10_000, "microsoft_self_service"),
        ("Azure (one entity)", 5_000, "microsoft_self_service"),
    ]

    # (label, price_per_image, notes)
    approaches: list[tuple[str, float, str]] = [
        ("AWS: SDXL self-hosted on g5.xlarge spot", 0.0015, "~200 imgs/hr; full LoRA+inpainting"),
        ("AWS: Flux Dev self-hosted on g5.xlarge spot", 0.005, "~60 imgs/hr; better quality"),
        ("AWS: Titan Image v2 (Bedrock API)", 0.012, "no LoRA; simple API call"),
        (
            "GCP: SDXL self-hosted on g2-standard-4 spot",
            0.0011,
            "~200 imgs/hr; full LoRA+inpainting",
        ),
        ("GCP: Imagen 3 Fast (Vertex AI)", 0.02, "no LoRA; Google quality"),
        ("GCP: Imagen 3 Standard (Vertex AI)", 0.04, "inpainting; best GCP quality"),
        (
            "Azure: SDXL self-hosted on NC24ads A100 spot",
            0.0011,
            "~600 imgs/hr; fastest self-hosted",
        ),
    ]

    lines = [
        "### Startup Credits → Image Generation Capacity",
        "",
        "Self-hosted on cloud GPU is 8-36x more images-per-credit-dollar than using API.",
        "AWS g5.xlarge spot + SDXL is the recommended default: full features, lowest cost.",
        "",
    ]

    for prog_label, credits, prog_key in programs:
        lines.append(f"  {prog_label}  (${credits:,} credits)")
        relevant = [
            (lbl, ppi, note)
            for lbl, ppi, note in approaches
            if prog_key in lbl.lower()
            or (prog_key == "aws_activate" and "aws" in lbl.lower())
            or (prog_key == "google_cloud_scale_ai" and "gcp" in lbl.lower())
            or (prog_key == "google_cloud_start" and "gcp" in lbl.lower())
            or (prog_key == "microsoft_self_service" and "azure" in lbl.lower())
        ]
        if not relevant:
            relevant = [(lbl, ppi, note) for lbl, ppi, note in approaches]
        for lbl, ppi, note in relevant:
            if prog_key == "aws_activate" and "aws" not in lbl.lower():
                continue
            if (
                prog_key in ("google_cloud_start", "google_cloud_scale_ai")
                and "gcp" not in lbl.lower()
            ):
                continue
            if prog_key == "microsoft_self_service" and "azure" not in lbl.lower():
                continue
            n_images = int(credits / ppi)
            lines.append(f"    {lbl:<50}  {n_images:>12,} images  (${ppi:.4f}/img) — {note}")
        lines.append("")

    lines += [
        "  Strategy recommendation (May 2026):",
        "  1. Apply for AWS Activate via NVIDIA Inception (no equity, ~$25K-100K)",
        "  2. Self-host SDXL on g5.xlarge spot → $0.0015/image from credits",
        "  3. Use Titan Image v2 (Bedrock) for simplicity before infra is set up",
        "  4. GCP Start ($2K) → Imagen 3 Fast for quality variants, self-hosted for volume",
        "  5. Azure credits ($5K x2 entities) → A100 spot self-hosted = 9M images total",
        "  6. Reserve Runware ($0.0006/image cash) as overflow when credits run out",
    ]
    return "\n".join(lines)


def bookcreator_unit_economics(
    books_per_month: int = 500,
    pages_per_book: int = 20,
    variants_shown: int = 4,
    gen_price_per_image: float = 0.0026,  # Runware SDXL default
    lora_cost_per_child: float = 1.50,  # Replicate Flux LoRA
    lora_reuse_books: int = 10,  # LoRA amortised over 10 books per child
    refinement_rate: float = 0.30,  # 30% of users request refinement
    refinement_images: int = 4,  # images per refinement round
) -> str:
    """
    Estimate image generation cost per book for BookCreator.

    Assumptions:
      - Each page = 1 final image + (variants_shown - 1) discarded variants
      - LoRA training is amortised across lora_reuse_books per child
      - Only refinement_rate% of users trigger step 2 (inpainting refinement)
    """
    imgs_per_book = pages_per_book * variants_shown
    gen_cost = imgs_per_book * gen_price_per_image
    lora_amortised = lora_cost_per_child / lora_reuse_books
    refinement_cost = refinement_rate * refinement_images * gen_price_per_image
    total_img_cost = gen_cost + lora_amortised + refinement_cost

    monthly_gen = books_per_month * gen_cost
    monthly_lora = books_per_month * lora_amortised
    monthly_refinement = books_per_month * refinement_cost
    monthly_total = books_per_month * total_img_cost

    lines = [
        f"### BookCreator Unit Economics — {books_per_month} books/month",
        "",
        f"  Book spec:       {pages_per_book} pages x {variants_shown} variants = {imgs_per_book} images/book",
        f"  Gen model:       ${gen_price_per_image:.4f}/image ({gen_price_per_image * 1000:.2f}/1000)",
        f"  LoRA training:   ${lora_cost_per_child:.2f}/child amortised over {lora_reuse_books} books",
        f"  Refinement:      {refinement_rate * 100:.0f}% of orders, {refinement_images} extra images each",
        "",
        "  Per-book image costs:",
        f"    Generation:    ${gen_cost:.4f}  ({imgs_per_book} images)",
        f"    LoRA amort.:   ${lora_amortised:.4f}  (1/{lora_reuse_books} of ${lora_cost_per_child:.2f})",
        f"    Refinement:    ${refinement_cost:.4f}  ({refinement_rate * 100:.0f}% x {refinement_images} imgs)",
        "    ─────────────────────────────",
        f"    Total img gen: ${total_img_cost:.4f}/book",
        "",
        "  Monthly at scale:",
        f"    Generation:    ${monthly_gen:,.2f}",
        f"    LoRA training: ${monthly_lora:,.2f}",
        f"    Refinement:    ${monthly_refinement:,.2f}",
        "    ─────────────────────────────",
        f"    Total img gen: ${monthly_total:,.2f}/mo ({monthly_total / books_per_month:.4f}/book)",
        "",
        f"  At $14.99/book: image gen is {total_img_cost / 14.99 * 100:.1f}% of revenue",
        f"  Remaining for printing, shipping, LLM, infra, margin: ${14.99 - total_img_cost:.2f}/book",
    ]
    return "\n".join(lines)
