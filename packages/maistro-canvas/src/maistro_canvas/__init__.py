"""maistro-canvas: standalone book builder with AI image generation pipeline.

Standalone product that can run on a mini-PC with a P40 image gen server.
Uses canvas protocols from maistro-core for the image generation pipeline.
"""

from __future__ import annotations

from maistro_canvas.protocols import CanvasStore, CompositorService, ImageGenClient, ImageData
from maistro_canvas.types import (
    BlendMode,
    CanvasError,
    CanvasRecord,
    CanvasTier,
    GenerationJobRecord,
    JobAction,
    JobStatus,
    LayerRecord,
    LayerType,
    ModelInfo,
    TextConfig,
    validate_canvas_dimensions,
    normalise_rotation,
)

__all__ = [
    "BlendMode",
    "CanvasError",
    "CanvasRecord",
    "CanvasStore",
    "CanvasTier",
    "CompositorService",
    "GenerationJobRecord",
    "ImageData",
    "ImageGenClient",
    "JobAction",
    "JobStatus",
    "LayerRecord",
    "LayerType",
    "ModelInfo",
    "TextConfig",
    "validate_canvas_dimensions",
    "normalise_rotation",
]
