"""ONNX encoder: shape, unit norm, determinism, missing / mismatched artifacts (plan Part C §9)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from app.config import get_settings
from app.encoder import OnnxEncoder, get_encoder, read_encoder_meta, verify_sha256
from app.errors import ArtifactMissing, ArtifactVersionMismatch


def test_dim_norm_and_determinism() -> None:
    enc = get_encoder()
    assert enc.dim == 384
    assert enc.model_id == "intfloat/multilingual-e5-small"
    v = enc.encode_array(["متى تأسست المجموعة؟", "How do I request leave?"])
    assert v.shape == (2, 384)
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-4)
    w = enc.encode_array(["متى تأسست المجموعة؟"])
    assert np.array_equal(v[0], w[0])
    assert enc.encode([]) == []


def test_get_encoder_is_cached() -> None:
    assert get_encoder() is get_encoder(get_settings().encoder_dir)


def test_sha_ok() -> None:
    verify_sha256(get_settings().encoder_dir)


def test_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(ArtifactMissing, match="copy models/e5"):
        OnnxEncoder(tmp_path / "nope")


def test_sha_mismatch(tmp_path: Path) -> None:
    src = get_settings().encoder_dir
    dst = tmp_path / "e5"
    dst.mkdir()
    meta = read_encoder_meta(src)
    shutil.copy(src / "tokenizer.json", dst / "tokenizer.json")
    (dst / "model_int8.onnx").write_bytes(b"not a model")
    (dst / "encoder_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ArtifactVersionMismatch):
        verify_sha256(dst)


def test_bad_meta(tmp_path: Path) -> None:
    (tmp_path / "encoder_meta.json").write_text("{", encoding="utf-8")
    with pytest.raises(ArtifactVersionMismatch):
        read_encoder_meta(tmp_path)
