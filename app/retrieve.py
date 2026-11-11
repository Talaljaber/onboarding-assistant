"""Hybrid retrieval over the live K-rows: e5 dense + BM25 fused by RRF, the out-of-scope margin, the
offline answer bands, list-question detection and OOS auto-disable (plan Part C §4.2–§4.4).

What it does: embeds each row as `"{topic} {keyword_en}: {answer_ar}"` and each question raw, both with
the encoder's `query:` prefix; ranks every row by `1/(60+rank_dense) + 1/(60+rank_bm25)` (the BM25 term
only when the row's BM25 score is > 0); computes `margin = best row cosine − best enabled OOS cosine`
and maps it to a band (thresholds from `results/bands.json` when present, else 0.01 / 0.05).
`reindex()` runs after every KB edit (the KB calls it through `subscribe`).

What it must never do: write files, call the network, or see the user's role.
"""

from __future__ import annotations

import csv
import json
import math
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
from numpy.typing import NDArray

from app.kb import KnowledgeBase, Row
from app.logging_setup import log_event
from app.textnorm import ascii_digits, normalize, tokens

BandName = Literal["answer", "not_confirmed", "refuse"]
RRF_K = 60
DEFAULT_REFUSE = 0.01
DEFAULT_NOT_CONFIRMED = 0.05
OOS_DISABLE_ANY = 0.95
OOS_DISABLE_EDITED = 0.90
ANCHOR_KEEP_COS = 0.85  # an edited row keeps its anchors while cos(edited, official) >= this
_QCACHE_SIZE = 256


class Encoder(Protocol):
    dim: int
    model_id: str

    def encode_array(self, texts: list[str]) -> NDArray[np.float32]: ...


@dataclass(frozen=True)
class Hit:
    id: str
    topic: str
    dense: float
    bm25: float
    rrf: float
    rank: int
    named: bool = False  # the user named this row's id in the message (F6)


@dataclass(frozen=True)
class MarginResult:
    best_row_id: str
    best_row_cos: float
    best_oos_id: str | None
    best_oos_cos: float | None
    margin: float


@dataclass
class OOSExample:
    id: str
    question_ar: str
    category: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class Bands:
    """`margin <= refuse` → refuse; `<= not_confirmed` → not_confirmed; else answer."""

    refuse: float = DEFAULT_REFUSE
    not_confirmed: float = DEFAULT_NOT_CONFIRMED
    source: str = "default"

    def band(self, margin: float) -> BandName:
        if margin <= self.refuse:
            return "refuse"
        if margin <= self.not_confirmed:
            return "not_confirmed"
        return "answer"


def _pick(d: dict[str, Any], *names: str) -> float | None:
    for n in names:
        v = d.get(n)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            return float(v)
    return None


def read_bands(path: Path) -> Bands:
    """Read `results/bands.json`; accepts `{"refuse": x, "not_confirmed": y}` (optionally under `"bands"`,
    or with `_max` / `_threshold` suffixes). Missing or malformed → the initial 0.01 / 0.05."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Bands()
    except (OSError, ValueError) as exc:
        log_event("bands_unreadable", error=type(exc).__name__)
        return Bands()
    if isinstance(data, dict) and isinstance(data.get("bands"), dict):
        data = data["bands"]
    if not isinstance(data, dict):
        return Bands()
    refuse = _pick(data, "refuse", "refuse_max", "refuse_threshold")
    nc = _pick(data, "not_confirmed", "not_confirmed_max", "not_confirmed_threshold")
    if refuse is None or nc is None or nc < refuse:
        log_event("bands_invalid", keys=sorted(data))
        return Bands()
    return Bands(refuse=refuse, not_confirmed=nc, source=str(path))


@lru_cache(maxsize=1)
def load_bands() -> Bands:
    """Bands from `<repo>/results/bands.json` if present, else the initial thresholds (cached)."""
    from app.config import ROOT

    return read_bands(ROOT / "results" / "bands.json")


def load_anchors(path: Path | None = None) -> list[tuple[str, str]]:
    """(row_id, question_ar) pairs from `data/ours/kb_anchors.csv`; [] when the file is absent.

    Anchors feed only the row side of the out-of-scope margin (D-W2-offline-bands), never ranking.
    """
    if path is None:
        from app.config import ROOT

        path = ROOT / "data" / "ours" / "kb_anchors.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [(r["row_id"], r["question_ar"]) for r in csv.DictReader(fh) if r.get("question_ar")]


def load_out_of_scope(path: Path) -> list[OOSExample]:
    """Read `data/ours/out_of_scope.csv` (UTF-8, `enabled` true/false)."""
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return [
            OOSExample(
                id=r["id"].strip(),
                question_ar=r["question_ar"].strip(),
                category=(r.get("category") or "").strip(),
                enabled=(r.get("enabled") or "true").strip().lower() == "true",
            )
            for r in csv.DictReader(f)
        ]


# ---------------------------------------------------------------------------------- list questions
#: List cue (normalised text). «قيم» alone is not enough when the question names exactly one value.
LIST_Q = re.compile(
    r"(?<![\w])(?:ال)?قيم(?:ها|نا|كم)?(?![\w])|(?<![\w])(?:اذكر|اذكري|عدد لي|عددلي|"
    r"values|list|brands|showrooms|العلامات|الماركات|الفروع|المعارض)(?![\w])|"
    r"(?<![\w])ما ?هي ال\w+ات(?![\w])"
)
_SINGULAR_VALUE = re.compile(r"(?<![\w])(?:ال)?قيمه(?![\w])")
#: Normalised names of the five values (Arabic as in K05–K09, plus English).
VALUE_NAMES: dict[str, tuple[str, ...]] = {
    "Integrity": ("النزاهه", "نزاهه", "integrity"),
    "One Team": ("فريق واحد", "الفريق الواحد", "one team"),
    "Perseverance": ("المثابره", "مثابره", "perseverance"),
    "Customer Centricity": ("محوريه العميل", "customer centricity"),
    "Social Responsibility": ("المسووليه الاجتماعيه", "المسوليه الاجتماعيه", "social responsibility"),
}
_VALUE_RES = {
    v: re.compile(r"(?<![\w])(?:و|ب|ل)?(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w])")
    for v, names in VALUE_NAMES.items()
}


def named_values(text: str) -> list[str]:
    """The company values (English keys) named in the text."""
    t = normalize(text)
    return [v for v, rx in _VALUE_RES.items() if rx.search(t)]


def is_list_question(text: str) -> bool:
    """A list cue (plural / «اذكر» / «ما هي ال…ات» / values / list …) and not exactly one value named."""
    t = normalize(text)
    if not LIST_Q.search(t):
        return False
    return len(named_values(text)) != 1


# ---------------------------------------------------------------------------------- K-ids in the message
#: A K-row id typed by the user («K14», «k 14», «K-14», Arabic-Indic digits after `ascii_digits`).
KID_IN_QUERY = re.compile(r"(?<![A-Za-z0-9])[Kk] ?-?(\d{1,3})(?![0-9])")


def split_named_ids(query: str, live_ids: list[str]) -> tuple[str, list[str]]:
    """(query without any K-id, the named ids that exist in `live_ids` in message order).

    Every K-id is stripped from the text that is embedded and BM25-scored, so an unknown id («K99») adds
    no noise and a known one is used only through the returned list (red team F6).
    """
    q = ascii_digits(query)
    found = KID_IN_QUERY.findall(q)
    if not found:
        return query, []
    by_num = {int(rid[1:]): rid for rid in live_ids if rid[:1] == "K" and rid[1:].isdigit()}
    named = list(dict.fromkeys(by_num[int(n)] for n in found if int(n) in by_num))
    clean = " ".join(KID_IN_QUERY.sub(" ", q).split())
    return clean, named


# ---------------------------------------------------------------------------------- BM25 and RRF
class BM25:
    """Okapi BM25 with idf `log(1 + (n - df + 0.5) / (df + 0.5))`."""

    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75) -> None:
        self.docs, self.k1, self.b = docs, k1, b
        self.avg = (sum(map(len, docs)) / len(docs)) if docs else 0.0
        n = len(docs)
        df: dict[str, int] = {}
        for d in docs:
            for w in set(d):
                df[w] = df.get(w, 0) + 1
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def scores(self, q_tokens: list[str]) -> NDArray[np.float64]:
        out = np.zeros(len(self.docs))
        if not self.avg:
            return out
        for i, d in enumerate(self.docs):
            for w in q_tokens:
                f = d.count(w)
                if f:
                    norm = f + self.k1 * (1 - self.b + self.b * len(d) / self.avg)
                    out[i] += self.idf[w] * f * (self.k1 + 1) / norm
        return out


def _ranks(scores: NDArray[Any]) -> NDArray[np.int64]:
    order = np.argsort(-scores, kind="stable")
    ranks = np.empty(len(scores), dtype=np.int64)
    ranks[order] = np.arange(len(scores))
    return ranks


def rrf(dense: NDArray[Any], bm25: NDArray[Any], k: int = RRF_K) -> NDArray[np.float64]:
    """Reciprocal-rank fusion; a row's BM25 term counts only when its BM25 score is > 0."""
    rd, rb = _ranks(np.asarray(dense)), _ranks(np.asarray(bm25))
    out = 1.0 / (k + rd)
    out = out + np.where(np.asarray(bm25) > 0, 1.0 / (k + rb), 0.0)
    return np.asarray(out, dtype=np.float64)


# ---------------------------------------------------------------------------------- retriever
class Retriever:
    """Hybrid search over the live KB with the OOS margin."""

    def __init__(
        self,
        encoder: Encoder,
        kb: KnowledgeBase,
        out_of_scope: list[OOSExample] | None = None,
        *,
        bands: Bands | None = None,
        subscribe: bool = True,
        anchors_enabled: bool = True,
    ) -> None:
        self.encoder = encoder
        self.kb = kb
        self.bands = bands or load_bands()
        self.oos = list(out_of_scope or [])
        self._oos_enabled_initial = {o.id: o.enabled for o in self.oos}
        self._lock = threading.RLock()
        self._qcache: OrderedDict[str, NDArray[np.float32]] = OrderedDict()
        self._oos_mat = (
            self.encoder.encode_array([o.question_ar for o in self.oos])
            if self.oos
            else np.zeros((0, encoder.dim), dtype=np.float32)
        )
        self.last_disabled: list[str] = []
        anchors = load_anchors() if anchors_enabled else []
        self._anchor_ids = [rid for rid, _ in anchors]
        self._anchor_mat = (
            self.encoder.encode_array([q for _, q in anchors])
            if anchors
            else np.zeros((0, encoder.dim), dtype=np.float32)
        )
        self._official_vecs: dict[str, NDArray[np.float32]] = {}
        self.reindex()
        self._official_vecs = {
            r.id: self._row_mat[i] for i, r in enumerate(self._rows) if not r.edited
        }
        if anchors and len(self._official_vecs) < len({rid for rid, _ in anchors}):
            # Started from an edited live KB: embed the official texts for the anchor check.
            from app.config import ROOT
            from app.kb import load_official

            off_rows = load_official(ROOT / "data" / "official" / "knowledge_base.csv")
            vecs = self.encoder.encode_array([r.embed_text() for r in off_rows])
            for r, v in zip(off_rows, vecs, strict=True):
                self._official_vecs.setdefault(r.id, v)
        if subscribe:
            kb.subscribe(self._on_kb_change)

    # -------------------------------------------------------------- index
    def reindex(self, changed_id: str | None = None, *, reset: bool = False) -> list[str]:
        """Re-embed the rows, rebuild BM25 and recompute the OOS auto-disable set.

        Returns the OOS ids disabled by this call. `reset=True` re-enables every OOS example first.
        """
        with self._lock:
            rows = self.kb.rows()
            mat = self.encoder.encode_array([r.embed_text() for r in rows])
            bm = BM25([tokens(r.answer_ar + " " + r.keyword_en) for r in rows])
            self._rows, self._row_mat, self._bm25 = rows, mat, bm
            self._ids = [r.id for r in rows]
            if reset:
                for o in self.oos:
                    o.enabled = self._oos_enabled_initial.get(o.id, True)
            disabled: list[str] = []
            if changed_id is not None and self.oos and len(rows):
                sims = self._oos_mat @ mat.T  # (n_oos, n_rows)
                best = sims.max(axis=1)
                top = sims.argmax(axis=1)
                for i, o in enumerate(self.oos):
                    if not o.enabled:
                        continue
                    if best[i] >= OOS_DISABLE_ANY or (
                        self._ids[int(top[i])] == changed_id and best[i] >= OOS_DISABLE_EDITED
                    ):
                        o.enabled = False
                        disabled.append(o.id)
            self.last_disabled = disabled
            if disabled:
                log_event("oos_disabled", ids=disabled, row=changed_id)
            return disabled

    def _still_like_official(self, row_id: str, vec: NDArray[np.float32]) -> bool:
        """An edited row keeps its anchors while its text stays close to the official text."""
        off = self._official_vecs.get(row_id)
        return off is not None and float(off @ vec) >= ANCHOR_KEEP_COS

    def _on_kb_change(self, changed_id: str | None) -> None:
        self.reindex(changed_id, reset=changed_id is None)

    def enabled_oos(self) -> list[str]:
        return [o.id for o in self.oos if o.enabled]

    # -------------------------------------------------------------- queries
    def _qvec(self, query: str) -> NDArray[np.float32]:
        with self._lock:
            v = self._qcache.get(query)
            if v is not None:
                self._qcache.move_to_end(query)
                return v
        v = self.encoder.encode_array([query])[0]
        with self._lock:
            self._qcache[query] = v
            if len(self._qcache) > _QCACHE_SIZE:
                self._qcache.popitem(last=False)
        return v

    def search(self, query: str, *, k: int = 18) -> list[Hit]:
        """Every row (up to k) sorted by RRF, with its dense cosine and BM25 score.

        K-ids in the query are stripped before scoring; a named id that exists in the live KB is ranked
        first (`Hit.named`), unknown ids are ignored (F6).
        """
        with self._lock:
            rows, mat, bm, ids = self._rows, self._row_mat, self._bm25, self._ids
        if not rows:
            return []
        query, named = split_named_ids(query, ids)
        q = self._qvec(query)
        dense = mat @ q
        b = bm.scores(tokens(query))
        fused = rrf(dense, b)
        order = sorted(range(len(rows)), key=lambda i: (-fused[i], -dense[i]))
        if named:
            first = [ids.index(rid) for rid in named]
            order = first + [i for i in order if i not in first]
        named_set = set(named)
        return [
            Hit(
                id=rows[i].id,
                topic=rows[i].topic,
                dense=float(dense[i]),
                bm25=float(b[i]),
                rrf=float(fused[i]),
                rank=n + 1,
                named=rows[i].id in named_set,
            )
            for n, i in enumerate(order[:k])
        ]

    def margin(self, query: str) -> MarginResult:
        """Best row cosine minus the best enabled out-of-scope cosine."""
        with self._lock:
            rows, mat = self._rows, self._row_mat
            enabled = [i for i, o in enumerate(self.oos) if o.enabled]
        query, _ = split_named_ids(query, self._ids)
        q = self._qvec(query)
        dense = mat @ q
        if len(self._anchor_ids):
            # Row side = max(row-text cosine, best anchor cosine) for rows still official;
            # live-edited or added rows keep the row-text cosine only.
            dense = dense.copy()
            official = {
                r.id: i
                for i, r in enumerate(rows)
                if not r.edited or self._still_like_official(r.id, mat[i])
            }
            a_sims = self._anchor_mat @ q
            for rid, s in zip(self._anchor_ids, a_sims, strict=True):
                i = official.get(rid)
                if i is not None and s > dense[i]:
                    dense[i] = s
        bi = int(np.argmax(dense))
        best_cos = float(dense[bi])
        if not enabled:
            return MarginResult(rows[bi].id, best_cos, None, None, best_cos)
        oos_sims = self._oos_mat[enabled] @ q
        oi = int(np.argmax(oos_sims))
        oos_cos = float(oos_sims[oi])
        return MarginResult(rows[bi].id, best_cos, self.oos[enabled[oi]].id, oos_cos, best_cos - oos_cos)

    def band(self, m: MarginResult) -> BandName:
        return self.bands.band(m.margin)

    def topic_rows(self, topic: str) -> list[Row]:
        return [r for r in self.kb.rows() if r.topic == topic]

    def is_list_question(self, query: str) -> bool:
        return is_list_question(query)


__all__ = [
    "BM25",
    "KID_IN_QUERY",
    "LIST_Q",
    "VALUE_NAMES",
    "Bands",
    "Hit",
    "MarginResult",
    "OOSExample",
    "Retriever",
    "is_list_question",
    "load_bands",
    "load_out_of_scope",
    "named_values",
    "read_bands",
    "rrf",
    "split_named_ids",
]
