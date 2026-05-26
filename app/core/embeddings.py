import hashlib
import json
import math
import re
from collections import Counter


LOCAL_EMBEDDING_PROVIDER = "local"
LOCAL_EMBEDDING_MODEL = "hashing-ngrams-v1"
LOCAL_EMBEDDING_DIMENSIONS = 512


def embedding_config(settings: dict | None = None) -> tuple[str, str]:
    settings = settings or {}
    provider = str(settings.get("embedding_provider") or "openai").strip().lower()
    model = str(settings.get("embedding_model") or settings.get("local_embedding_model") or "").strip()
    if provider == "openai" and settings.get("openai_api_key"):
        return "openai", model or "text-embedding-3-small"
    return LOCAL_EMBEDDING_PROVIDER, LOCAL_EMBEDDING_MODEL


def embed_texts(texts: list[str], settings: dict | None = None) -> tuple[str, str, list[list[float]]]:
    provider, model = embedding_config(settings)
    if provider == "openai":
        try:
            vectors = _embed_openai(texts, settings or {}, model)
            return provider, model, vectors
        except Exception:
            provider, model = LOCAL_EMBEDDING_PROVIDER, LOCAL_EMBEDDING_MODEL
    return provider, model, [_local_embedding(text) for text in texts]


def dumps_vector(vector: list[float]) -> str:
    return json.dumps([round(float(value), 8) for value in vector], separators=(",", ":"))


def loads_vector(value: str) -> list[float]:
    parsed = json.loads(value or "[]")
    return [float(item) for item in parsed]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = math.sqrt(sum(value * value for value in left[:size]))
    right_norm = math.sqrt(sum(value * value for value in right[:size]))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _embed_openai(texts: list[str], settings: dict, model: str) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.get("openai_api_key", ""))
    response = client.embeddings.create(model=model, input=texts)
    ordered = sorted(response.data, key=lambda item: item.index)
    return [[float(value) for value in item.embedding] for item in ordered]


def _local_embedding(text: str, *, dimensions: int = LOCAL_EMBEDDING_DIMENSIONS) -> list[float]:
    tokens = _terms(text)
    features: Counter[int] = Counter()
    for token in tokens:
        features[_feature_index(f"w:{token}", dimensions)] += 1.0
        for gram in _char_ngrams(token):
            features[_feature_index(f"g:{gram}", dimensions)] += 0.35
    norm = math.sqrt(sum(value * value for value in features.values()))
    if not norm:
        return [0.0] * dimensions
    vector = [0.0] * dimensions
    for index, value in features.items():
        vector[index] = value / norm
    return vector


def _terms(text: str) -> list[str]:
    return [part.lower() for part in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", text or "")]


def _feature_index(value: str, dimensions: int) -> int:
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % dimensions


def _char_ngrams(token: str) -> list[str]:
    padded = f" {token} "
    if len(padded) <= 4:
        return [padded]
    return [padded[index : index + 4] for index in range(len(padded) - 3)]
