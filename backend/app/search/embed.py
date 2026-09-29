"""Text embedders for the dense search leg (S5).

``hash``  (default) deterministic feature hashing of stemmed words, word pairs and a small
          drilling synonym map into 1024 dims. No model, no network: search works offline
          and in CI. It is lexical at heart, so it is labelled as such everywhere
          (``embedding_provider`` in every search response); it is not a semantic model.
``ollama`` the configured model (default BGE-M3, 1024-d) served by Ollama's /api/embed.

Both return L2-normalised vectors, so cosine similarity = dot product.
"""

import hashlib
import itertools
import json
import math
import re
import urllib.request
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.db.models.documents import EMBEDDING_DIM

HASH_VERSION = "v1"


class Embedder(Protocol):
    @property
    def name(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


# Words that mean the same thing in drilling reports map to one token, so "lost returns"
# and "losses" land near each other even without a learned model.
_SYNONYMS = {
    "loss": "losses",
    "lost": "losses",
    "losses": "losses",
    "returns": "losses",
    "stuck": "stuck",
    "sticking": "stuck",
    "stick": "stuck",
    "differential": "stuck",
    "packoff": "stuck",
    "kick": "kick",
    "kicked": "kick",
    "influx": "kick",
    "gain": "kick",
    "overpull": "tight",
    "tight": "tight",
    "drag": "tight",
    "cavings": "instability",
    "sloughing": "instability",
    "instability": "instability",
    "washout": "instability",
    "balling": "balling",
    "balled": "balling",
    "lcm": "lcm",
    "pill": "lcm",
    "jar": "jar",
    "jarred": "jar",
    "jars": "jar",
    "overpressure": "overpressure",
    "gas": "overpressure",
    "cement": "cement",
    "cementing": "cement",
    "squeeze": "cement",
}
_WORD = re.compile(r"[a-z][a-z0-9\-]+|\d+(?:\.\d+)?")
_STOP = frozenset(
    {"a", "an", "and", "at", "by", "for", "from", "in", "into", "is", "it", "of", "on", "or"}
    | {"the", "to", "was", "were", "with", "while", "had", "has", "after", "before", "then"}
    | {"during"}
)


def _stem(w: str) -> str:
    w = w.replace("-", "")
    for suffix in ("ing", "ed", "es", "s"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def _features(text: str) -> list[str]:
    words = [w for w in _WORD.findall(text.lower()) if w not in _STOP]
    toks = [_stem(w) for w in words if not w[0].isdigit()]
    feats = list(toks)
    feats += [f"{a}_{b}" for a, b in itertools.pairwise(toks)]
    feats += [f"syn:{_SYNONYMS[w]}" for w in words if w in _SYNONYMS]
    return feats


class HashEmbedder:
    name = f"hash:{HASH_VERSION}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    @staticmethod
    def _one(text: str) -> list[float]:
        vec = [0.0] * EMBEDDING_DIM
        counts: dict[str, int] = {}
        for f in _features(text):
            counts[f] = counts.get(f, 0) + 1
        for f, n in counts.items():
            h = hashlib.blake2b(f.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % EMBEDDING_DIM
            sign = 1.0 if h[4] & 1 else -1.0
            weight = (1 + math.log(n)) * (1.5 if f.startswith("syn:") else 1.0)
            vec[idx] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [round(v / norm, 6) for v in vec]


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str, timeout_s: float) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("embedding_base_url must be an http(s) URL")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        req = urllib.request.Request(  # noqa: S310 (scheme checked in __init__)
            f"{self.base_url}/api/embed",
            data=json.dumps({"model": self.model, "input": texts}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
            vectors: list[list[float]] = json.loads(resp.read())["embeddings"]
        for v in vectors:
            if len(v) != EMBEDDING_DIM:
                raise ValueError(
                    f"{self.model} returned {len(v)}-d vectors; the index expects {EMBEDDING_DIM}"
                )
        return [_normalise(v) for v in vectors]


def _normalise(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_provider == "ollama":
        if not s.embedding_base_url:
            raise ValueError("SMRITI_EMBEDDING_PROVIDER=ollama needs SMRITI_EMBEDDING_BASE_URL")
        return OllamaEmbedder(s.embedding_base_url, s.embedding_model, s.llm_timeout_s)
    return HashEmbedder()
