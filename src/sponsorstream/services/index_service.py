"""IndexService for campaign and creative ingestion."""

from __future__ import annotations

from ..config.runtime import RuntimeSettings
from ..domain.sponsorship import Campaign, Creative
from ..ports.embedding import EmbeddingProvider
from ..ports.vector_store import VectorStorePort


class IndexService:
    """Manage the campaigns collection and creative lifecycle."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStorePort,
        settings: RuntimeSettings,
    ) -> None:
        self._embed = embedding_provider
        self._store = vector_store
        self._settings = settings

    def ensure_collection(
        self,
        dimension: int | None = None,
        embedding_model_id: str | None = None,
        schema_version: str | None = None,
    ) -> dict:
        if dimension is None:
            dimension = self._settings.embedding_dimension
        return self._store.ensure_collection(
            dimension,
            embedding_model_id=embedding_model_id,
            schema_version=schema_version,
        )

    def delete_collection(self) -> None:
        self._store.delete_collection()

    def collection_info(self) -> dict:
        return self._store.collection_info()

    def upsert_campaigns(self, items: list[Campaign | Creative]) -> int:
        creatives: list[Creative] = []
        for item in items:
            if isinstance(item, Campaign):
                creatives.extend(item.to_creatives())
            else:
                creatives.append(item)
        return self.upsert_creatives(creatives)

    def upsert_creatives(self, creatives: list[Creative]) -> int:
        batch_size = self._settings.max_batch_size
        total = 0
        for i in range(0, len(creatives), batch_size):
            batch = creatives[i : i + batch_size]
            creatives_with_embeddings = [
                (creative, self._embed.embed(creative.embedding_text)) for creative in batch
            ]
            total += self._store.upsert_batch(creatives_with_embeddings)
        return total

    def delete_creative(self, creative_id: str) -> None:
        self._store.delete_creative(creative_id)

    def get_creative(self, creative_id: str) -> dict | None:
        return self._store.get_creative(creative_id)

    def bulk_disable(self, filter_spec: dict) -> int:
        """Set enabled=False for all creatives matching filter_spec. Returns count updated."""
        return self._store.bulk_disable(filter_spec)
