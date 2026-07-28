"""CWICR settings domain."""

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict


class CWICRSettings:
    """CWICR settings."""

    # ── CWICR ───────────────────────────────────────────────────────────
    match_backend: str = Field(
        default="qdrant",
        description="Matching backend for vector search (qdrant, lancedb)",
    )
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Qdrant server URL",
    )
    qdrant_api_key: str = Field(
        default="",
        description="Qdrant API key (if required)",
    )
    embedding_model_name: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="Name of the sentence transformer model for embeddings",
    )
    embedding_dimensions: int = Field(
        default=384,
        description="Dimensions of the embedding vectors",
    )
    chunk_size: int = Field(
        default=512,
        description="Text chunk size for embedding processing",
    )
    chunk_overlap: int = Field(
        default=50,
        description="Overlap between text chunks for embedding processing",
    )
    similarity_threshold: float = Field(
        default=0.7,
        description="Similarity threshold for semantic search results",
    )
    max_search_results: int = Field(
        default=10,
        description="Maximum number of results to return from semantic search",
    )
    enable_query_expansion: bool = Field(
        default=True,
        description="Whether to expand queries with synonyms for better search",
    )
    cache_embeddings: bool = Field(
        default=True,
        description="Whether to cache computed embeddings",
    )
    embedding_cache_size: int = Field(
        default=1000,
        description="Maximum number of embeddings to cache",
    )

    @field_validator("match_backend", mode="before")
    @classmethod
    def _reject_lancedb_match_backend(cls, value: object) -> object:
        """Reject pre-v3 ``MATCH_BACKEND=lancedb`` env values explicitly.

        The legacy LanceDB ranker, boost stack, and lexical matcher were
        removed in v3. An old ``.env`` carrying ``MATCH_BACKEND=lancedb``
        would silently fail to find the modules, so we surface a clear
        deprecation error at boot instead.
        """
        if isinstance(value, str) and value.strip().lower() == "lancedb":
            raise ValueError(
                "MATCH_BACKEND=lancedb is no longer supported - the legacy "
                "ranker was removed in v3. Set MATCH_BACKEND=qdrant (the new "
                "default) or remove the line from your .env."
            )
        return value

    model_config = SettingsConfigDict(env_prefix="OE_")
