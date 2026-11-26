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
from collections.abc import Callable, Iterable, Mapping, Sequence
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
# Structural (template) similarity: entities -> <LABEL>, digits -> 0, 3-word shingles.
# Calibrated on all 29 families x 40 renders: same-family nearest neighbour p05 = 0.28,
# different-family nearest neighbour max = 0.17, so 0.25 separates them. At 0.8 / 5-word
# shingles a simulated leak of 50 test-family documents into train went undetected.
STRUCT_SHINGLE = 3
STRUCT_THRESHOLD = 0.25
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
def _shingles(text: str, k: int = SHINGLE) -> set[str]:
    words = text.lower().split()
    if len(words) < k:
        return {" ".join(words)}
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def masked_text(doc: Document) -> str:
    """Replace every gold span with ``<LABEL>``: exposes shared *template structure*.

    Raw-text near-duplicate checks cannot see family leakage, because fillers and
    entity values make same-family documents look different (measured max Jaccard
    0.10-0.45 between same-family documents; review finding M2-2).
    """
    out, pos = [], 0
    for s in doc.spans:
        out += [doc.text[pos : s.start], f"<{s.label.value}>"]
        pos = s.end
    out.append(doc.text[pos:])
    return "".join(out)


def _minhash(shingles: set[str]) -> MinHash:
    mh = MinHash(num_perm=128, seed=1)
    for s in sorted(shingles):
        mh.update(s.encode("utf-8"))
    return mh


@dataclass
class DuplicateReport:
    doc_id_collisions: int
    exact_within: dict[str, int]
    exact_cross: int
    near_within: dict[str, int]
    near_cross: int
    near_cross_examples: list[tuple[str, str, float]]
    max_cross_jaccard: float
    structural_cross: int
    structural_cross_examples: list[tuple[str, str, float]]
    max_structural_cross_jaccard: float


def structural_text(doc: Document) -> str:
    """Template skeleton: entities -> ``<LABEL>``, digit runs -> ``0``."""
    return re.sub(r"\d+", "0", masked_text(doc))


def _cross_matches(
    splits: Mapping[str, Sequence[Document]],
    to_text: Callable[[Document], str],
    k: int,
    threshold: float,
) -> tuple[int, list[tuple[str, str, float]], float]:
    """Documents with a match in an *earlier* split at Jaccard >= ``threshold``.

    Returns (matched document count, up to 5 examples, max Jaccard among LSH candidates).
    Candidate retrieval runs below the threshold so the reported max is informative.
    """
    lsh = MinHashLSH(threshold=max(0.05, 0.6 * threshold), num_perm=128)
    shingles: dict[str, set[str]] = {}
    count, max_j = 0, 0.0
    examples: list[tuple[str, str, float]] = []
    for i, split in enumerate(splits):
        if i:  # query this split against all earlier splits before inserting it
            for doc in splits[split]:
                sh = _shingles(to_text(doc), k)
                best, best_key = 0.0, ""
                for other in lsh.query(_minhash(sh)):
                    j = _jaccard(sh, shingles[other])
                    if j > best:
                        best, best_key = j, other
                max_j = max(max_j, best)
                if best >= threshold:
                    count += 1
                    if len(examples) < 5:
                        examples.append((best_key, f"{split}/{doc.doc_id}", round(best, 3)))
        for doc in splits[split]:
            key = f"{split}/{doc.doc_id}"
            shingles[key] = _shingles(to_text(doc), k)
            lsh.insert(key, _minhash(shingles[key]))
    return count, examples, round(max_j, 3)


def find_duplicates(splits: Mapping[str, Sequence[Document]]) -> DuplicateReport:
    """Exact / near / structural duplicates. Near = MinHash LSH confirmed by exact Jaccard."""
    ids = Counter(doc.doc_id for docs in splits.values() for doc in docs)
    owner_by_text: dict[str, list[str]] = defaultdict(list)
    for split, docs in splits.items():
        for doc in docs:
            owner_by_text[doc.text].append(split)
    exact_within: Counter[str] = Counter()
    exact_cross = 0
    for owners in owner_by_text.values():
        for a, b in combinations(owners, 2):
            if a == b:
                exact_within[a] += 1
            else:
                exact_cross += 1

    near_within: Counter[str] = Counter()
    for split, docs in splits.items():
        lsh = MinHashLSH(threshold=NEAR_DUP_THRESHOLD, num_perm=128)
        sh = {d.doc_id: _shingles(d.text) for d in docs}
        for doc_id, s in sh.items():
            for other in lsh.query(_minhash(s)):
                if _jaccard(s, sh[other]) >= NEAR_DUP_THRESHOLD:
                    near_within[split] += 1
            if doc_id not in lsh:
                lsh.insert(doc_id, _minhash(s))

    near_cross, near_examples, near_max = _cross_matches(
        splits, lambda d: d.text, SHINGLE, NEAR_DUP_THRESHOLD
    )
    struct_cross, struct_examples, struct_max = _cross_matches(
        splits, structural_text, STRUCT_SHINGLE, STRUCT_THRESHOLD
    )
    return DuplicateReport(
        doc_id_collisions=sum(n - 1 for n in ids.values() if n > 1),
        exact_within=dict(exact_within),
        exact_cross=exact_cross,
        near_within=dict(near_within),
        near_cross=near_cross,
        near_cross_examples=near_examples,
        max_cross_jaccard=near_max,
        structural_cross=struct_cross,
        structural_cross_examples=struct_examples,
        max_structural_cross_jaccard=struct_max,
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
        # Token level: whole strings understate memorisation (a new full name can be made
        # of a first name and a surname that were both seen in train; review finding M2-3).
        train_tokens = {t for s in train_strings.get(label, set()) for t in s.split()}
        tokens = {t for s in strings for t in s.split()}
        out[label.value] = {
            "distinct": len(strings),
            "seen_in_train": seen,
            "share": round(seen / len(strings), 3) if strings else 0.0,
            "token_share": round(len(tokens & train_tokens) / len(tokens), 3) if tokens else 0.0,
        }
    return out


def title_stats(docs: Sequence[Document]) -> dict[str, float]:
    """Share of PATIENT / STAFF spans directly preceded by a 'Dr' title (shortcut check)."""
    counts: dict[str, list[int]] = {"PATIENT": [0, 0], "STAFF": [0, 0]}
    for d in docs:
        for s in d.spans:
            if s.label.value in counts:
                before = d.text[max(0, s.start - 4) : s.start]
                counts[s.label.value][0] += bool(re.search(r"(?i)\bdr\.? $", before))
                counts[s.label.value][1] += 1
    return {f"{k}_after_dr": round(a / n, 3) if n else 0.0 for k, (a, n) in counts.items()}


def _base_fmt(span: Span) -> str:
    return (span.fmt or "none").split("+")[0]  # strip noise tags (+typo, +case)


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
def family_leaks(
    splits: Mapping[str, Sequence[Document]], assignment: Mapping[str, str]
) -> list[Issue]:
    """Every family a document was built from must belong to that document's split."""
    issues: list[Issue] = []
    for split, docs in splits.items():
        for doc in docs:
            for fid in str(doc.metadata.get("family", "")).split("+"):
                owner = assignment.get(fid)
                if owner != split:
                    issues.append(
                        Issue(
                            "error", "family_leak", doc.doc_id, f"family {fid!r} belongs to {owner}"
                        )
                    )
    return issues


def validate(
    splits: Mapping[str, Sequence[Document]], assignment: Mapping[str, str] | None = None
) -> dict[str, object]:
    issues: list[Issue] = []
    for docs in splits.values():
        for doc in docs:
            issues += check_document(doc)
    if assignment is not None:
        issues += family_leaks(splits, assignment)
    dups = find_duplicates(splits)
    if dups.doc_id_collisions:
        issues.append(
            Issue("error", "doc_id_collision", None, f"{dups.doc_id_collisions} repeated id(s)")
        )
    if dups.structural_cross:
        issues.append(
            Issue(
                "error",
                "structural_dup_cross",
                None,
                f"{dups.structural_cross} doc(s) share a template with an earlier split "
                f"(structural Jaccard >= {STRUCT_THRESHOLD})",
            )
        )
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
        "title_stats": {k: title_stats(v) for k, v in splits.items()},
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
        "(memorisation risk; not an error). Cells: whole-string share / token share.",
        "",
        "| Type | " + " | ".join(overlap) + " |",
        "|---|" + "---:|" * len(overlap),
    ]
    for t in EntityType:
        row = " | ".join(
            f"{o[t.value]['share']:.1%} / {o[t.value]['token_share']:.1%}" for o in overlap.values()
        )
        lines.append(f"| {t.value} | {row} |")
    dups = report["duplicates"]
    titles = report["title_stats"]
    assert isinstance(dups, dict) and isinstance(titles, dict)
    lines += [
        "",
        "## Leakage and shortcut checks",
        "",
        f"- Max raw-text Jaccard, eval doc vs earlier split: {dups['max_cross_jaccard']}",
        "- Max structural Jaccard, eval doc vs earlier split: "
        f"{dups['max_structural_cross_jaccard']}",
        "- Eval documents with a near-duplicate in an earlier split "
        f"(raw >= {NEAR_DUP_THRESHOLD}): {dups['near_cross']}",
        f"- Eval documents sharing a template with an earlier split (structural >= "
        f"{STRUCT_THRESHOLD}): {dups['structural_cross']}",
        "",
        "| Split | PATIENT after 'Dr' | STAFF after 'Dr' |",
        "|---|---:|---:|",
    ]
    for split, t in titles.items():
        lines.append(f"| {split} | {t['PATIENT_after_dr']:.1%} | {t['STAFF_after_dr']:.1%} |")
    lines += ["", "## Issues by check", ""]
    issues = report["issues_by_check"]
    assert isinstance(issues, dict)
    lines += [f"- `{k}`: {v}" for k, v in sorted(issues.items())] or ["- none"]
    return "\n".join(lines) + "\n"


def load_splits(
    manifest_path: Path, root: Path
) -> tuple[str, dict[str, list[Document]], dict[str, str]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    splits = {s: read_documents(root / info["path"]) for s, info in manifest["files"].items()}
    return str(manifest["version"]), splits, dict(manifest.get("split_assignment", {}))


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate a generated PrivyMed dataset.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=Path("reports/data"))
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = find_repo_root()
    verify_manifest(args.manifest, root=root)
    version, splits, assignment = load_splits(args.manifest, root)
    report = validate(splits, assignment)
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
