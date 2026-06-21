"""Docling tokenizer backed by the backend embedding endpoint."""

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from pydantic import ConfigDict, PrivateAttr

from services.api_client import ApiClient


class ApiEmbeddingTokenizer(BaseTokenizer):
    """Tokenizer wrapper that delegates token counting to backend embedding API."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: ApiClient
    task_id: str
    task_secret: str
    max_tokens: int = 8192

    _cache: dict[str, int] = PrivateAttr(default_factory=dict)

    def count_tokens(self, text: str) -> int:
        """Get number of tokens for given text via backend API."""
        cached = self._cache.get(text)
        if cached is not None:
            return cached

        counts = self.client.get_token_counts(
            [text],
            task_id=self.task_id,
            task_secret=self.task_secret,
        )
        if not counts:
            raise RuntimeError("Backend token counting returned no values.")
        count = int(counts[0])

        self._cache[text] = count
        return count

    def get_max_tokens(self) -> int:
        """Get maximum number of tokens allowed."""
        return self.max_tokens

    def get_tokenizer(self) -> str:
        """Return symbolic tokenizer identifier."""
        return "api-embedding-tokenizer"
