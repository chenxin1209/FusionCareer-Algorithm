"""
抽岗前对 Markdown 近重复去重。

老师要求：先把文章切成 n-gram，用 MinHash 签名，MinHashLSH 分桶，
再对桶内候选算 Jaccard；相似度高于阈值只留一篇，然后再做岗位提取。
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from job_structuring import paths

_TZ = timezone(timedelta(hours=8))
_MD_MARK = re.compile(r"[#*_`>\-\[\]()!]|https?://\S+")
_WS = re.compile(r"\s+")

_DEFAULTS = {
    "enabled": True,
    "ngram": 3,
    "num_perm": 128,
    "lsh_threshold": 0.6,
    "jaccard_threshold": 0.85,
    "index_rel": os.path.join("logs", "article_minhash.json"),
    "persist": True,
}


def _cfg(config: Optional[dict], key: str) -> Any:
    mapping = {
        "enabled": "article_dedup_enabled",
        "ngram": "article_dedup_ngram",
        "num_perm": "article_dedup_num_perm",
        "lsh_threshold": "article_dedup_lsh_threshold",
        "jaccard_threshold": "article_dedup_jaccard_threshold",
        "index_rel": "article_dedup_index",
        "persist": "article_dedup_persist",
    }
    cfg = config or {}
    raw = cfg.get(mapping[key], _DEFAULTS[key])
    if key in ("enabled", "persist"):
        return raw is not False
    if key in ("ngram", "num_perm"):
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return _DEFAULTS[key]
    if key in ("lsh_threshold", "jaccard_threshold"):
        try:
            return min(0.99, max(0.1, float(raw)))
        except (TypeError, ValueError):
            return _DEFAULTS[key]
    return str(raw or _DEFAULTS[key])


def normalize_text(text: str) -> str:
    s = _MD_MARK.sub(" ", text or "")
    s = s.lower()
    s = _WS.sub("", s)
    return s


def ngrams(text: str, n: int = 3) -> set[str]:
    """字符 n-gram 集合（中英混排招聘文比按词切更稳）。"""
    blob = normalize_text(text)
    if not blob:
        return set()
    if len(blob) <= n:
        return {blob}
    return {blob[i : i + n] for i in range(len(blob) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


_MH_P = (1 << 61) - 1
_MH_A = tuple((i * 2 + 1) * 0x9E3779B185EBCA87 % _MH_P for i in range(256))
_MH_B = tuple((i * 2 + 1) * 0xC2B2AE3D27D4EB4F % _MH_P for i in range(256))


def _hash64(data: bytes) -> int:
    import hashlib

    return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "little") % _MH_P


class _LocalMinHash:
    """datasketch 装不上时的同款签名，接口对齐 MinHash。"""

    def __init__(self, num_perm: int = 128, hashvalues: Optional[list] = None):
        self.num_perm = num_perm
        if hashvalues is not None:
            self.hashvalues = [int(v) for v in hashvalues]
        else:
            self.hashvalues = [_MH_P] * num_perm

    def update(self, data: bytes) -> None:
        x = _hash64(data)
        for i in range(self.num_perm):
            v = (_MH_A[i] * x + _MH_B[i]) % _MH_P
            if v < self.hashvalues[i]:
                self.hashvalues[i] = v

    def jaccard(self, other: "_LocalMinHash") -> float:
        if not self.hashvalues:
            return 0.0
        same = sum(a == b for a, b in zip(self.hashvalues, other.hashvalues))
        return same / len(self.hashvalues)


class _LocalMinHashLSH:
    """按 band 分桶，等价于 MinHashLSH 的候选召回。"""

    def __init__(self, threshold: float = 0.6, num_perm: int = 128):
        self.threshold = threshold
        self.num_perm = num_perm
        self.rows, self.bands = _lsh_bands(num_perm, threshold)
        self.tables: list[dict[tuple, list[str]]] = [{} for _ in range(self.bands)]
        self._keys: set[str] = set()

    def insert(self, key: str, mh: _LocalMinHash) -> None:
        if key in self._keys:
            raise ValueError(f"key exists: {key}")
        self._keys.add(key)
        vals = list(mh.hashvalues)
        for i in range(self.bands):
            band = tuple(vals[i * self.rows : (i + 1) * self.rows])
            self.tables[i].setdefault(band, []).append(key)

    def query(self, mh: _LocalMinHash) -> list[str]:
        found: set[str] = set()
        vals = list(mh.hashvalues)
        for i in range(self.bands):
            band = tuple(vals[i * self.rows : (i + 1) * self.rows])
            found.update(self.tables[i].get(band, []))
        return list(found)


def _lsh_bands(num_perm: int, threshold: float) -> tuple[int, int]:
    """选择 (rows, bands) 使 (1/bands)^(1/rows) 接近 LSH 阈值。"""
    best = (1, num_perm)
    best_diff = 9.0
    for rows in range(1, num_perm + 1):
        if num_perm % rows:
            continue
        bands = num_perm // rows
        est = (1.0 / bands) ** (1.0 / rows)
        diff = abs(est - threshold)
        if diff < best_diff:
            best_diff = diff
            best = (rows, bands)
    return best


def _minhash_cls():
    try:
        from datasketch import MinHash

        return MinHash
    except ImportError:
        return _LocalMinHash


def _lsh_cls():
    try:
        from datasketch import MinHashLSH

        return MinHashLSH
    except ImportError:
        return _LocalMinHashLSH


def _minhash(grams: Iterable[str], num_perm: int):
    mh = _minhash_cls()(num_perm=num_perm)
    for g in grams:
        if g:
            mh.update(g.encode("utf-8"))
    return mh


@dataclass
class ArticleDoc:
    path: str
    title: str
    text: str
    grams: set[str]
    minhash: Any
    size: int


@dataclass
class DroppedArticle:
    path: str
    title: str
    kept_path: str
    jaccard: float


class _UnionFind:
    def __init__(self, items: list[str]):
        self.parent = {x: x for x in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _index_path(config: Optional[dict]) -> str:
    rel = _cfg(config, "index_rel")
    return paths._resolve_under_root(rel) if not os.path.isabs(rel) else rel


def _load_history(config: Optional[dict], num_perm: int) -> list[tuple[str, Any]]:
    path = _index_path(config)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("items") if isinstance(data, dict) else data
    out = []
    if not isinstance(rows, list):
        return []
    cls = _minhash_cls()
    for row in rows[-4000:]:
        if not isinstance(row, dict):
            continue
        key = str(row.get("path") or "").strip()
        vals = row.get("hashvalues")
        if not key or not isinstance(vals, list) or len(vals) != num_perm:
            continue
        mh = cls(num_perm=num_perm, hashvalues=vals)
        out.append((f"hist:{key}", mh, key))
    return out


def _save_history(kept: list[ArticleDoc], config: Optional[dict]) -> None:
    path = _index_path(config)
    existing = []
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            existing = list(data.get("items") or []) if isinstance(data, dict) else []
        except (OSError, json.JSONDecodeError):
            existing = []
    seen = {str(x.get("path")) for x in existing if isinstance(x, dict)}
    now = datetime.now(_TZ).isoformat(timespec="seconds")
    for doc in kept:
        if doc.path in seen:
            continue
        existing.append(
            {
                "path": doc.path,
                "title": doc.title,
                "hashvalues": [int(v) for v in doc.minhash.hashvalues],
                "ts": now,
            }
        )
    existing = existing[-4000:]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"items": existing}, f, ensure_ascii=False)
    os.replace(tmp, path)


def _log_jsonl(record: dict[str, Any]) -> None:
    try:
        folder = os.path.join(paths.LOGS_DIR, "article_dedup")
        os.makedirs(folder, exist_ok=True)
        day = datetime.now(_TZ).strftime("%Y-%m-%d")
        jsonl = os.path.join(folder, f"{day}.jsonl")
        with open(jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _read_md(path: str) -> tuple[str, str]:
    with open(path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    title = ""
    for line in text.splitlines()[:12]:
        s = line.strip().lstrip("#").strip()
        if s:
            title = s[:120]
            break
    if not title:
        title = os.path.basename(path)
    return title, text


def _keep_score(doc: ArticleDoc) -> tuple:
    return (doc.size, os.path.getmtime(doc.path) if os.path.isfile(doc.path) else 0, doc.path)


def select_unique_markdowns(
    md_paths: list[str],
    config: Optional[dict] = None,
) -> tuple[list[str], list[DroppedArticle]]:
    """
    对一批 md 做 MinHash+LSH 近重复去重，返回应进入抽岗的路径。
    历史已抽过的近似文也会被丢掉，避免隔天同一篇再进模型。
    """
    if not md_paths:
        return [], []
    if not _cfg(config, "enabled"):
        return list(md_paths), []

    n = int(_cfg(config, "ngram"))
    num_perm = int(_cfg(config, "num_perm"))
    lsh_th = float(_cfg(config, "lsh_threshold"))
    jac_th = float(_cfg(config, "jaccard_threshold"))

    LSH = _lsh_cls()

    docs: list[ArticleDoc] = []
    total_in = len(md_paths)
    for i, path in enumerate(md_paths, 1):
        if not os.path.isfile(path):
            continue
        title, text = _read_md(path)
        grams = ngrams(text, n)
        if not grams:
            docs.append(
                ArticleDoc(path=path, title=title, text=text, grams=set(), minhash=_minhash(["<empty>"], num_perm), size=len(text))
            )
            continue
        docs.append(
            ArticleDoc(
                path=os.path.abspath(path),
                title=title,
                text=text,
                grams=grams,
                minhash=_minhash(grams, num_perm),
                size=len(normalize_text(text)),
            )
        )
        if total_in >= 200 and i % 500 == 0:
            print(f"  [article_dedup] 签名 {i}/{total_in}", flush=True)
    if not docs:
        return [], []

    lsh = LSH(threshold=lsh_th, num_perm=num_perm)
    history = _load_history(config, num_perm) if _cfg(config, "persist") else []
    hist_mh: dict[str, Any] = {}
    hist_key_to_path = {}
    for key, mh, raw_path in history:
        try:
            lsh.insert(key, mh)
            hist_mh[key] = mh
            hist_key_to_path[key] = raw_path
        except ValueError:
            continue
    for doc in docs:
        try:
            lsh.insert(doc.path, doc.minhash)
        except ValueError:
            continue

    uf = _UnionFind([d.path for d in docs])
    dropped: list[DroppedArticle] = []
    drop_vs_history: dict[str, DroppedArticle] = {}
    by_path = {d.path: d for d in docs}

    for doc in docs:
        candidates = [c for c in lsh.query(doc.minhash) if c != doc.path]
        best_hist = None
        best_hist_j = 0.0
        for cand in candidates:
            if cand.startswith("hist:"):
                hist_sig = hist_mh.get(cand)
                if hist_sig is None:
                    continue
                est = float(doc.minhash.jaccard(hist_sig))
                if est >= jac_th and est > best_hist_j:
                    best_hist = hist_key_to_path.get(cand) or cand[5:]
                    best_hist_j = est
                continue
            other = by_path.get(cand)
            if other is None:
                continue
            sim = jaccard(doc.grams, other.grams)
            if sim >= jac_th:
                uf.union(doc.path, other.path)
        if best_hist:
            drop_vs_history[doc.path] = DroppedArticle(
                path=doc.path,
                title=doc.title,
                kept_path=best_hist,
                jaccard=best_hist_j,
            )

    clusters: dict[str, list[ArticleDoc]] = {}
    for doc in docs:
        if doc.path in drop_vs_history:
            continue
        clusters.setdefault(uf.find(doc.path), []).append(doc)

    keep: list[ArticleDoc] = []
    for members in clusters.values():
        winner = max(members, key=_keep_score)
        keep.append(winner)
        for doc in members:
            if doc.path == winner.path:
                continue
            sim = jaccard(doc.grams, winner.grams)
            dropped.append(
                DroppedArticle(
                    path=doc.path,
                    title=doc.title,
                    kept_path=winner.path,
                    jaccard=sim,
                )
            )
    dropped.extend(drop_vs_history.values())
    keep_paths = [d.path for d in sorted(keep, key=lambda x: x.path)]
    if _cfg(config, "persist"):
        _save_history(keep, config)
    _log_jsonl(
        {
            "ts": datetime.now(_TZ).isoformat(timespec="seconds"),
            "incoming": len(md_paths),
            "kept": len(keep_paths),
            "dropped": len(dropped),
            "ngram": n,
            "num_perm": num_perm,
            "lsh_threshold": lsh_th,
            "jaccard_threshold": jac_th,
            "dropped_preview": [
                {
                    "path": os.path.basename(x.path),
                    "keep": os.path.basename(x.kept_path),
                    "jaccard": round(x.jaccard, 3),
                }
                for x in dropped[:50]
            ],
        }
    )
    return keep_paths, dropped


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="抽岗前 Markdown MinHash+LSH 去重（不调用 LLM）")
    parser.add_argument("--dir", required=True, help="递归扫描的 .md 目录")
    parser.add_argument("--jaccard", type=float, default=None, help="覆盖 Jaccard 阈值")
    args = parser.parse_args(argv)
    cfg: dict[str, Any] = {}
    if args.jaccard is not None:
        cfg["article_dedup_jaccard_threshold"] = args.jaccard
    files = []
    for root, _, names in os.walk(args.dir):
        for name in names:
            if name.lower().endswith(".md"):
                files.append(os.path.join(root, name))
    files.sort()
    kept, dropped = select_unique_markdowns(files, cfg)
    print(f"文件 {len(files)}，保留 {len(kept)}，近重复跳过 {len(dropped)}")
    for item in dropped[:30]:
        print(f"  drop {os.path.basename(item.path)}  keep {os.path.basename(item.kept_path)}  jaccard={item.jaccard:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
