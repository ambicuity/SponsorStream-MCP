"""Adapter: FastEmbed-based EmbeddingProvider."""

from __future__ import annotations

from fastembed import TextEmbedding


class FastEmbedProvider:
    """Concrete EmbeddingProvider backed by fastembed."""

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id
        self._model: TextEmbedding | None = None

    def _get_model(self) -> TextEmbedding:
        if self._model is None:
            self._model = TextEmbedding(model_name=self._model_id)
        return self._model

    def embed(self, text: str) -> list[float]:
        model = self._get_model()
        vector_iter = model.embed([text])
        return list(next(vector_iter))
