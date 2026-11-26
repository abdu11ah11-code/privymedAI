"""Dataset validation and statistics (Milestone 2 quality gate).

Usage::

    uv run privymed-validate --manifest data/manifests/v1.json

Errors (non-zero exit): manifest hash mismatch, empty documents, label/shape
violations, BIO alignment failures, exact or near duplicates *across* splits.
Reported (no failure): within-split duplicates, identifier overlap between
evaluation splits and train, formats unseen in train, distribution stats.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Literal

from datasketch import MinHash, MinHashLSH

from privymed.bio import AlignmentError, bio_to_spans, spans_to_bio, tokenize
from privymed.config import find_repo_root
from privymed.data_generation.dataset import verify_manifest
from privymed.io import read_documents
from privymed.schema import Document, EntityType, Span

NEAR_DUP_THRESHOLD = 0.8
OVERLAP_WARN = 0.5  # warn if >50% of an eval split's distinct strings of a type occur in train
SHINGLE = 5
_MONTH = re.compile(r"(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b")


@dataclass(frozen=True)
class Issue:
    severity: Literal["error", "warning"]
    check: str
    doc_id: str | None
    message: str


# ============================================================================ per-document checks
def _digits(s: str) -> int:
    return sum(c.isdigit() for c in s)


def shape_violation(label: EntityType, surface: str) -> str | None:
    """Cheap sanity rule per type; returns a reason if ``surface`` cannot be a ``label``."""
    has_letter = any(c.isalpha() for c in surface)
    match label:
        case EntityType.EMAIL:
            ok = re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", surface) is not None
        case EntityType.PHONE:
            ok = 7 <= _digits(surface) <= 15 and not has_letter
        case EntityType.CNIC:
            ok = _digits(surface) == 13 and re.fullmatch(r"[\d\- ]+", surface) is not None
        case EntityType.DATE:
            ok = _digits(surface) > 0 or _MONTH.search(surface) is not None
        case EntityType.ID:
            ok = _digits(surface) > 0
        case EntityType.PATIENT | EntityType.STAFF:
            ok = has_letter and _digits(surface) == 0 and "@" not in surface
        case EntityType.HOSPITAL | EntityType.ADDRESS:
            ok = has_letter and "@" not in surface
    return None if ok else f"{label.value} surface fails shape rule"


def check_document(doc: Document) -> list[Issue]:
    issues: list[Issue] = []
    if not doc.text.strip():
        issues.append(Issue("error", "empty", doc.doc_id, "empty document"))
        return issues
    for span in doc.spans:
        reason = shape_violation(span.label, doc.span_text(span))
        if reason:
            issues.append(
                Issue("error", "shape", doc.doc_id, f"{reason} at {span.start}:{span.end}")
            )
    tokens = tokenize(doc.text)
    try:
        tags = spans_to_bio(tokens, doc.spans)
    except AlignmentError as exc:
        issues.append(Issue("error", "bio_alignment", doc.doc_id, str(exc)))
        return issues
    decoded = [s.key for s in bio_to_spans(tokens, tags)]
    if decoded != [s.key for s in doc.spans]:
        issues.append(Issue("error", "bio_roundtrip", doc.doc_id, "BIO decode != gold spans"))
    return issues


# ============================================================================ duplicates
def _shingles(text: str) -> set[str]:
    words = text.lower().split()
    if len(words) < SHINGLE:
        return {" ".join(words)}
    return {" ".join(words[i : i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


@dataclass
class DuplicateReport:
    exact_within: dict[str, int]
    exact_cross: int
    near_within: dict[str, int]
    near_cross: int
    near_cross_examples: list[tuple[str, str, float]]
    max_cross_jaccard: float


def find_duplicates(splits: Mapping[str, Sequence[Document]]) -> DuplicateReport:
    """Exact duplicates by text; near duplicates by MinHash LSH, confirmed with exact Jaccard."""
    owner: dict[str, str] = {}
    shingles: dict[str, set[str]] = {}
    minhashes: dict[str, MinHash] = {}
    lsh = MinHashLSH(threshold=NEAR_DUP_THRESHOLD, num_perm=128)
    by_text: dict[str, list[str]] = defaultdict(list)
    for split, docs in splits.items():
        for doc in docs:
            owner[doc.doc_id] = split
            by_text[doc.text].append(doc.doc_id)
            sh = _shingles(doc.text)
            shingles[doc.doc_id] = sh
            mh = MinHash(num_perm=128, seed=1)
            for s in sorted(sh):
                mh.update(s.encode("utf-8"))
            lsh.insert(doc.doc_id, mh)
            minhashes[doc.doc_id] = mh

    exact_within: Counter[str] = Counter()
    exact_cross = 0
    for ids in by_text.values():
        for a, b in combinations(ids, 2):
            if owner[a] == owner[b]:
                exact_within[owner[a]] += 1
            else:
                exact_cross += 1

    near_within: Counter[str] = Counter()
    near_cross = 0
    examples: list[tuple[str, str, float]] = []
    max_cross = 0.0
    seen: set[tuple[str, str]] = set()
    for doc_id, mh in minhashes.items():
        for other in lsh.query(mh):
            if other == doc_id:
                continue
            pair = (min(doc_id, other), max(doc_id, other))
            if pair in seen:
                continue
            seen.add(pair)
            j = _jaccard(shingles[doc_id], shingles[other])
            if j < NEAR_DUP_THRESHOLD:
                continue
            if owner[doc_id] == owner[other]:
                near_within[owner[doc_id]] += 1
            else:
                near_cross += 1
                max_cross = max(max_cross, j)
                if len(examples) < 5:
                    examples.append((pair[0], pair[1], round(j, 3)))
    return DuplicateReport(
        exact_within=dict(exact_within),
        exact_cross=exact_cross,
        near_within=dict(near_within),
        near_cross=near_cross,
        near_cross_examples=examples,
        max_cross_jaccard=round(max_cross, 3),
    )


# ============================================================================ leakage & coverage
def identifier_overlap(
    train: Sequence[Document], other: Sequence[Document]
) -> dict[str, dict[str, float | int]]:
    """Per type: share of ``other``'s distinct entity strings that also occur in train."""
    train_strings: dict[EntityType, set[str]] = defaultdict(set)
    for d in train:
        for s in d.spans:
            train_strings[s.label].add(d.span_text(s).lower())
    out: dict[str, dict[str, float | int]] = {}
    other_strings: dict[EntityType, set[str]] = defaultdict(set)
    for d in other:
        for s in d.spans:
            other_strings[s.label].add(d.span_text(s).lower())
    for label in EntityType:
        strings = other_strings.get(label, set())
        seen = len(strings & train_strings.get(label, set()))
        out[label.value] = {
            "distinct": len(strings),
            "seen_in_train": seen,
            "share": round(seen / len(strings), 3) if strings else 0.0,
        }
    return out


def _base_fmt(span: Span) -> str:
    return (span.fmt or "none").removesuffix("+typo")


def unseen_formats(train: Sequence[Document], other: Sequence[Document]) -> dict[str, list[str]]:
    train_fmts = {(s.label, _base_fmt(s)) for d in train for s in d.spans}
    missing: dict[str, set[str]] = defaultdict(set)
    for d in other:
        for s in d.spans:
            if (s.label, _base_fmt(s)) not in train_fmts:
                missing[s.label.value].add(_base_fmt(s))
    return {k: sorted(v) for k, v in sorted(missing.items())}


# ============================================================================ statistics
def _dist(values: Sequence[int]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "mean": round(statistics.fmean(ordered), 1),
        "median": float(ordered[len(ordered) // 2]),
        "p90": float(ordered[int(0.9 * (len(ordered) - 1))]),
        "min": float(ordered[0]),
        "max": float(ordered[-1]),
    }


def split_stats(docs: Sequence[Document]) -> dict[str, object]:
    labels = Counter(s.label.value for d in docs for s in d.spans)
    total = sum(labels.values())
    return {
        "documents": len(docs),
        "characters": sum(len(d.text) for d in docs),
        "word_tokens": sum(len(tokenize(d.text)) for d in docs),
        "length_words": _dist([len(d.text.split()) for d in docs]),
        "length_tokens": _dist([len(tokenize(d.text)) for d in docs]),
        "spans": total,
        "spans_per_doc": round(total / len(docs), 2) if docs else 0.0,
        "spans_by_type": {k: labels.get(k, 0) for k in (t.value for t in EntityType)},
        "share_by_type": {
            t.value: round(labels.get(t.value, 0) / total, 4) if total else 0.0 for t in EntityType
        },
        "entity_free_share": round(sum(not d.spans for d in docs) / len(docs), 4),
        "bundle_share": round(
            sum(d.metadata.get("doc_type") == "bundle" for d in docs) / len(docs), 4
        ),
        "noise": dict(Counter(str(d.metadata.get("noise")) for d in docs)),
        "typo_spans": sum(1 for d in docs for s in d.spans if (s.fmt or "").endswith("+typo")),
        "doc_types": dict(Counter(str(d.metadata.get("doc_type")) for d in docs)),
        "formats_by_type": {
            t.value: len({_base_fmt(s) for d in docs for s in d.spans if s.label is t})
            for t in EntityType
        },
    }


# ============================================================================ runner
def validate(splits: Mapping[str, Sequence[Document]]) -> dict[str, object]:
    issues: list[Issue] = []
    for docs in splits.values():
        for doc in docs:
            issues += check_document(doc)
    dups = find_duplicates(splits)
    if dups.exact_cross:
        issues.append(Issue("error", "exact_dup_cross", None, f"{dups.exact_cross} pair(s)"))
    if dups.near_cross:
        issues.append(
            Issue(
                "error",
                "near_dup_cross",
                None,
                f"{dups.near_cross} pair(s) >= {NEAR_DUP_THRESHOLD}",
            )
        )
    for split, n in dups.exact_within.items():
        issues.append(Issue("warning", "exact_dup_within", None, f"{split}: {n} pair(s)"))
    for split, n in dups.near_within.items():
        issues.append(Issue("warning", "near_dup_within", None, f"{split}: {n} pair(s)"))

    train = splits.get("train", [])
    evals = {k: v for k, v in splits.items() if k != "train"}
    overlap = {k: identifier_overlap(train, v) for k, v in evals.items()}
    for split, per_type in overlap.items():
        for label, o in per_type.items():
            if float(o["share"]) > OVERLAP_WARN:
                issues.append(
                    Issue(
                        "warning",
                        "identifier_overlap",
                        None,
                        f"{split}/{label}: {o['share']:.0%} of strings seen in train",
                    )
                )
    return {
        "errors": sum(i.severity == "error" for i in issues),
        "warnings": sum(i.severity == "warning" for i in issues),
        "issues_by_check": dict(Counter(f"{i.severity}:{i.check}" for i in issues)),
        "issue_examples": [asdict(i) for i in issues[:25]],
        "duplicates": asdict(dups),
        "identifier_overlap_with_train": overlap,
        "formats_unseen_in_train": {k: unseen_formats(train, v) for k, v in evals.items()},
        "stats": {k: split_stats(v) for k, v in splits.items()},
    }


def _markdown(version: str, report: Mapping[str, object]) -> str:
    stats = report["stats"]
    overlap = report["identifier_overlap_with_train"]
    assert isinstance(stats, dict) and isinstance(overlap, dict)
    lines = [
        f"# Dataset report: {version}",
        "",
        "_Generated by `privymed-validate`. Do not edit by hand._",
        "",
        f"**Errors:** {report['errors']}  ·  **Warnings:** {report['warnings']}",
        "",
        "## Splits",
        "",
        "| Split | Docs | Spans | Spans/doc | Words mean (p90) | Entity-free | Bundles |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for split, s in stats.items():
        lw = s["length_words"]
        lines.append(
            f"| {split} | {s['documents']} | {s['spans']} | {s['spans_per_doc']} | "
            f"{lw.get('mean')} ({lw.get('p90')}) | "
            f"{s['entity_free_share']:.1%} | {s['bundle_share']:.1%} |"
        )
    lines += ["", "## Entity counts", "", "| Type | " + " | ".join(stats) + " |"]
    lines.append("|---|" + "---:|" * len(stats))
    for t in EntityType:
        row = " | ".join(
            f"{s['spans_by_type'][t.value]} ({s['share_by_type'][t.value]:.1%})"
            for s in stats.values()
        )
        lines.append(f"| {t.value} | {row} |")
    lines += [
        "",
        "## Identifier overlap with train",
        "",
        "Share of distinct entity strings in each evaluation split that also appear in train "
        "(memorisation risk; not an error).",
        "",
        "| Type | " + " | ".join(overlap) + " |",
        "|---|" + "---:|" * len(overlap),
    ]
    for t in EntityType:
        row = " | ".join(f"{o[t.value]['share']:.1%}" for o in overlap.values())
        lines.append(f"| {t.value} | {row} |")
    lines += ["", "## Issues by check", ""]
    issues = report["issues_by_check"]
    assert isinstance(issues, dict)
    lines += [f"- `{k}`: {v}" for k, v in sorted(issues.items())] or ["- none"]
    return "\n".join(lines) + "\n"


def load_splits(manifest_path: Path, root: Path) -> tuple[str, dict[str, list[Document]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    splits = {s: read_documents(root / info["path"]) for s, info in manifest["files"].items()}
    return str(manifest["version"]), splits


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate a generated PrivyMed dataset.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=Path("reports/data"))
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = find_repo_root()
    verify_manifest(args.manifest, root=root)
    version, splits = load_splits(args.manifest, root)
    report = validate(splits)
    out = root / args.report_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{version}_validation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (out / f"{version}_report.md").write_text(_markdown(version, report), encoding="utf-8")
    print(f"{version}: {report['errors']} error(s), {report['warnings']} warning(s)")
    print(json.dumps(report["issues_by_check"], indent=2))
    sys.exit(1 if report["errors"] else 0)


if __name__ == "__main__":
    main()
