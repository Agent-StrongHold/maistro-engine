"""Canvas Studio protocols — structural interfaces for DI.

All canvas-related business logic depends only on these protocols.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from maistro_canvas.types import (
        CanvasRecord,
        CompositeResult,
        GenerationJobRecord,
        LayerRecord,
        ModelInfo,
    )


@runtime_checkable
class CanvasStore(Protocol):
    """CRUD for canvases, layers, generation jobs, and composites."""

    async def create_canvas(
        self,
        *,
        name: str,
        width: int,
        height: int,
        background_color: str = "#FFFFFF",
        org_id: str = "",
    ) -> CanvasRecord: ...

    async def get_canvas(self, canvas_id: str) -> CanvasRecord | None: ...

    async def list_canvases(
        self,
        org_id: str,
        *,
        include_archived: bool = False,
    ) -> list[CanvasRecord]: ...

    async def update_canvas(self, canvas: CanvasRecord) -> CanvasRecord: ...

    async def add_layer(
        self,
        canvas_id: str,
        *,
        name: str,
        layer_type: str,
        z_index: int | None = None,
        **kwargs: Any,
    ) -> LayerRecord: ...

    async def get_layer(self, layer_id: str) -> LayerRecord | None: ...

    async def list_layers(self, canvas_id: str) -> list[LayerRecord]: ...

    async def update_layer(self, layer: LayerRecord) -> LayerRecord: ...

    async def remove_layer(self, layer_id: str) -> None: ...

    async def reorder_layers(
        self,
        canvas_id: str,
        assignments: list[dict[str, Any]],
    ) -> list[LayerRecord]: ...

    async def create_job(self, job: GenerationJobRecord) -> GenerationJobRecord: ...

    async def get_job(self, job_id: str) -> GenerationJobRecord | None: ...

    async def update_job(self, job: GenerationJobRecord) -> GenerationJobRecord: ...

    async def active_job_for_layer(self, layer_id: str) -> GenerationJobRecord | None: ...

    async def list_jobs_for_layer(self, layer_id: str) -> list[GenerationJobRecord]: ...

    async def save_composite(self, result: CompositeResult) -> CompositeResult: ...

    async def latest_composite(self, canvas_id: str) -> CompositeResult | None: ...


@runtime_checkable
class ImageGenClient(Protocol):
    """Calls an image-generation backend (LiteLLM proxy or local P40 server)."""

    async def generate(
        self,
        *,
        model_id: str,
        prompt: str,
        width: int,
        height: int,
        count: int = 1,
        seed: int | None = None,
        negative_prompt: str = "",
    ) -> list[ImageData]: ...

    async def refine(
        self,
        *,
        model_id: str,
        source_url: str,
        prompt: str,
        region: str = "full",
        strength: float = 0.6,
    ) -> ImageData: ...

    async def list_image_models(self) -> list[ModelInfo]: ...


@runtime_checkable
class CompositorService(Protocol):
    """Assembles layer images into a single composited image."""

    async def composite(
        self,
        canvas: CanvasRecord,
        layers: list[LayerRecord],
    ) -> CompositeResult: ...


class ImageData:
    """Raw image data returned by the generation backend."""

    __slots__ = ("width", "height", "url", "bytes_")

    def __init__(
        self,
        *,
        width: int,
        height: int,
        url: str = "",
        bytes_: bytes = b"",
    ) -> None:
        self.width = width
        self.height = height
        self.url = url
        self.bytes_ = bytes_
