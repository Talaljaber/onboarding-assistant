"""ONNX e5 sentence encoder (int8 multilingual-e5-small), lifted from CampusPulse `OnnxEncoder`.

What it does: tokenises with the `tokenizers` fast tokenizer, runs the int8 ONNX graph on CPU with
batch size 1, masked mean-pools and L2-normalises in numpy. `verify_sha256` checks the files against
`encoder_meta.json`. `get_encoder()` returns one process-wide instance (loaded once; tests share it).

What it must never do: import torch, download anything, or batch texts with padding (dynamic int8
quantisation makes a padded row depend on its neighbours; batch size 1 keeps vectors stable).

Encoder directory layout (`models/e5/`):

    model_int8.onnx      inputs input_ids, attention_mask (int64, [batch, seq]); output last_hidden_state
    tokenizer.json       the model's Hugging Face fast-tokenizer file
    encoder_meta.json    model_id, revision, dim, max_tokens, query_prefix, pooling, normalize, file names,
                         pad_token_id, input/output names, quantization settings, sha256 of both files
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort  # type: ignore[import-untyped, unused-ignore]
from numpy.typing import NDArray
from tokenizers import Tokenizer

from app.errors import ArtifactMissing, ArtifactVersionMismatch

ENCODER_META = "encoder_meta.json"
META_SCHEMA_VERSION = 1
FETCH_HINT = "copy models/e5 from the release zip or the repository"
_REQUIRED_META = ("schema_version", "model_id", "revision", "dim", "max_tokens", "query_prefix", "pooling",
                  "normalize", "onnx_file", "tokenizer_file", "pad_token_id", "input_names", "output_name")
_NORM_FLOOR = 1e-12  # guards the L2 division for an all-zero vector (cannot occur for a real encoder)


def read_encoder_meta(encoder_dir: Path) -> dict[str, Any]:
    """Load and check `encoder_meta.json`.

    Raises:
        ArtifactMissing: the directory or the meta file is absent.
        ArtifactVersionMismatch: unreadable JSON, a missing key, an unknown schema version, or a pooling
            other than `mean`.
    """
    encoder_dir = Path(encoder_dir)
    path = encoder_dir / ENCODER_META
    if not encoder_dir.is_dir() or not path.is_file():
        raise ArtifactMissing(f"encoder missing: {path} not found; {FETCH_HINT}")
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactVersionMismatch(f"{path}: unreadable encoder meta: {exc}") from exc
    missing = [k for k in _REQUIRED_META if k not in meta]
    if missing:
        raise ArtifactVersionMismatch(f"{path}: missing keys {missing}")
    if meta["schema_version"] != META_SCHEMA_VERSION:
        found = meta["schema_version"]
        raise ArtifactVersionMismatch(f"{path}: schema_version {found!r} != {META_SCHEMA_VERSION}")
    if meta["pooling"] != "mean":
        raise ArtifactVersionMismatch(f"{path}: pooling {meta['pooling']!r} is not supported (mean only)")
    return dict(meta)


def verify_sha256(encoder_dir: Path) -> None:
    """Compare `encoder_meta.json["sha256"]` with the files on disk.

    Raises:
        ArtifactMissing: the meta file or a listed file is absent.
        ArtifactVersionMismatch: the meta has no sha256 map or a file's hash differs.
    """
    encoder_dir = Path(encoder_dir)
    meta = read_encoder_meta(encoder_dir)
    shas = meta.get("sha256")
    if not isinstance(shas, dict) or not shas:
        raise ArtifactVersionMismatch(f"{encoder_dir / ENCODER_META}: no sha256 map; {FETCH_HINT}")
    for name, expected in shas.items():
        path = encoder_dir / str(name)
        if not path.is_file():
            raise ArtifactMissing(f"encoder missing: {path} not found; {FETCH_HINT}")
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ArtifactVersionMismatch(f"{path}: sha256 mismatch; {FETCH_HINT}")


class OnnxEncoder:
    """Sentence encoder over the ONNX int8 export.

    `encode(texts)`: prefix each text with `query_prefix` (callers never add it), tokenize with
    truncation to `max_tokens` (special tokens included), right-pad each batch of `batch_size` to its
    longest row, run ONNX Runtime on CPU, mean-pool the last hidden state over the attention mask, then
    L2-normalize (when the export says `normalize`). Returns `len(texts)` lists of `dim` floats, in input
    order; `[]` for no texts.

    `batch_size` defaults to the export's `encoder_meta.json` value (1). Dynamic int8 quantization scales
    activations per batch tensor, padding included, so in a padded batch a text's vector depends on its
    neighbours. With batch size 1 every text always gets the same vector.

    Raises:
        ArtifactMissing: the encoder directory, `encoder_meta.json`, the ONNX file or `tokenizer.json` is
            absent (message carries the fix).
        ArtifactVersionMismatch: a malformed meta file, or an ONNX graph whose inputs differ from the meta.
    """

    def __init__(
        self,
        encoder_dir: Path,
        *,
        query_prefix: str | None = None,
        max_tokens: int | None = None,
        intra_op_threads: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        encoder_dir = Path(encoder_dir)
        meta = read_encoder_meta(encoder_dir)
        onnx_path = encoder_dir / str(meta["onnx_file"])
        tokenizer_path = encoder_dir / str(meta["tokenizer_file"])
        for path in (onnx_path, tokenizer_path):
            if not path.is_file():
                raise ArtifactMissing(f"encoder missing: {path} not found; {FETCH_HINT}")
        batch_size = int(meta.get("batch_size", 1)) if batch_size is None else batch_size
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self.model_id: str = str(meta["model_id"])
        self.revision: str = str(meta["revision"])
        self.dim: int = int(meta["dim"])
        self.query_prefix: str = str(meta["query_prefix"]) if query_prefix is None else query_prefix
        self.max_tokens: int = int(meta["max_tokens"]) if max_tokens is None else max_tokens
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        self._normalize = bool(meta["normalize"])
        self._pad_id = int(meta["pad_token_id"])
        self._batch_size = batch_size
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.no_padding()
        self._tokenizer.enable_truncation(max_length=self.max_tokens)
        options = ort.SessionOptions()
        if intra_op_threads is not None:
            options.intra_op_num_threads = intra_op_threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.log_severity_level = 3
        self._session = ort.InferenceSession(str(onnx_path), options, providers=["CPUExecutionProvider"])
        graph_inputs = [i.name for i in self._session.get_inputs()]
        if sorted(graph_inputs) != sorted(meta["input_names"]):
            raise ArtifactVersionMismatch(f"{onnx_path}: inputs {graph_inputs} != meta {meta['input_names']}")
        self._input_names = tuple(graph_inputs)
        self._output_name = str(meta["output_name"])

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts (see the class docstring). Returns unit-norm float vectors of length `dim`."""
        return self.encode_array(texts).tolist()  # type: ignore[no-any-return]

    def encode_array(self, texts: Sequence[str]) -> NDArray[np.float32]:
        """Like `encode`, as a float32 array of shape (len(texts), dim)."""
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            out[start : start + len(batch)] = self._encode_batch(batch)
        return out

    def _encode_batch(self, texts: Sequence[str]) -> NDArray[np.float32]:
        encodings = self._tokenizer.encode_batch([self.query_prefix + t for t in texts])
        width = max(len(e.ids) for e in encodings)
        ids = np.full((len(texts), width), self._pad_id, dtype=np.int64)
        mask = np.zeros((len(texts), width), dtype=np.int64)
        for row, enc in enumerate(encodings):
            ids[row, : len(enc.ids)] = enc.ids
            mask[row, : len(enc.ids)] = 1
        feeds = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
        hidden = self._session.run([self._output_name], {k: feeds[k] for k in self._input_names})[0]
        weights = mask[:, :, None].astype(np.float32)
        pooled = (np.asarray(hidden, dtype=np.float32) * weights).sum(axis=1) / weights.sum(axis=1)
        if self._normalize:
            pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), _NORM_FLOOR)
        result: NDArray[np.float32] = pooled.astype(np.float32)
        return result


@lru_cache(maxsize=4)
def _load(encoder_dir: Path) -> OnnxEncoder:
    return OnnxEncoder(encoder_dir)


def get_encoder(encoder_dir: Path | None = None) -> OnnxEncoder:
    """The process-wide encoder for `encoder_dir` (default: settings.encoder_dir), loaded once."""
    if encoder_dir is None:
        from app.config import get_settings

        encoder_dir = get_settings().encoder_dir
    return _load(Path(encoder_dir).resolve())


__all__ = ["ENCODER_META", "OnnxEncoder", "get_encoder", "read_encoder_meta", "verify_sha256"]
