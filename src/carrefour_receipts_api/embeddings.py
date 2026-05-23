"""Lightweight text-embedding encoder backed by fastembed (ONNX, no torch).

Replaces the ``sentence-transformers`` / ``torch`` dependency. fastembed runs on
the ONNX Runtime, so it installs and runs on macOS x86_64 (Intel) where recent
``torch`` ships no wheels — which is exactly what broke ``uv sync`` here.

``Encoder`` is a thin adapter exposing a ``.encode()`` method compatible with the
``sentence-transformers`` API (single string -> 1-D vector, iterable -> 2-D array),
consumed by :func:`carrefour_receipts_api.categorization.categorize_labels_semantic`.

Embeddings are the *optional* semantic path for product categorization. The default
production path is rapidfuzz keyword matching (:mod:`carrefour_receipts_api.categorization`);
this module enables the higher-quality semantic variant when the ``ml`` extra is present.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

# Small, fast, ONNX-quantized default. Pass ``model_name`` to ``load_encoder`` for
# a multilingual model (e.g. "intfloat/multilingual-e5-small") on French labels.
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class Encoder:
    """fastembed-backed encoder with a sentence-transformers-like ``encode`` API."""

    def __init__(self, model_name: str = DEFAULT_MODEL, **kwargs):
        # Lazy import: fastembed lives in the optional ``ml`` extra.
        from fastembed import TextEmbedding

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name, **kwargs)

    def encode(
        self,
        texts: str | Iterable[str],
        batch_size: int = 32,
        show_progress_bar: bool = False,
        **_ignored,
    ) -> np.ndarray:
        """Embed ``texts``.

        Mirrors ``SentenceTransformer.encode``: a single ``str`` returns a 1-D
        vector, an iterable returns a 2-D array. fastembed already returns L2-
        normalized vectors, so sentence-transformers-only kwargs (``normalize_embeddings``,
        ``return_dense``, ``convert_to_tensor`` ...) are accepted and ignored.
        """
        if isinstance(texts, str):
            items, single = [texts], True
        else:
            items, single = list(texts), False
        vectors = np.asarray(list(self._model.embed(items, batch_size=batch_size)))
        return vectors[0] if single else vectors


def load_encoder(model_name: str = DEFAULT_MODEL, **kwargs) -> Encoder:
    """Return an :class:`Encoder` (fastembed downloads the ONNX model on first use)."""
    return Encoder(model_name, **kwargs)
