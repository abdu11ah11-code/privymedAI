"""Local LLM (Qwen via Ollama) as a PrivyMed detector (Milestone 5).

Inference is fully local: requests go to the Ollama server on 127.0.0.1 only, so no
document text leaves the machine. Decoding is greedy (temperature 0, fixed seed) with
Ollama's JSON-schema structured output; Qwen's "thinking" mode is disabled.

Every raw model response is kept (``raw_outputs``) so error analysis never needs a second
50-minute run; the evaluation runner writes them to the git-ignored ``reports/eval/raw/``
(a file, not logs — CLAUDE.md rule 4).
"""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from privymed.config import find_repo_root
from privymed.detectors.base import Detector
from privymed.io import read_documents
from privymed.llm.mapping import MappingStats, map_mentions, parse_response
from privymed.llm.prompt import (
    RESPONSE_SCHEMA,
    build_messages,
    prompt_fingerprint,
    select_examples,
)
from privymed.schema import Span

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.5:4b"
NUM_PREDICT = 2048  # output-token cap; the longest observed dev answer was ~580 tokens


def text_key(text: str) -> str:
    """Stable key linking a raw response to its document text (no text is stored)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _post(path: str, payload: dict[str, Any], timeout: float = 300.0) -> dict[str, Any]:
    req = urllib.request.Request(
        OLLAMA_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # localhost only
        result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return result


def _get(path: str, timeout: float = 30.0) -> dict[str, Any]:
    with urllib.request.urlopen(OLLAMA_URL + path, timeout=timeout) as resp:  # localhost only
        result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return result


class LLMDetector(Detector):
    """Prompted local LLM. Collects mapping statistics across calls in ``self.stats``."""

    name = "llm"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        n_examples: int = 3,
        num_ctx: int = 8192,
        seed: int = 0,
    ) -> None:
        self.model = model
        self.num_ctx = int(num_ctx)
        self.seed = int(seed)
        train = read_documents(find_repo_root() / "data/synthetic/v1/train.jsonl")
        self.examples = select_examples(train, k=int(n_examples))
        self.stats = MappingStats()
        self.raw_outputs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def reset_stats(self) -> None:
        """Called by the evaluation runner after warm-up calls."""
        with self._lock:
            self.stats = MappingStats()
            self.raw_outputs = {}

    def options(self) -> dict[str, Any]:
        return {
            "temperature": 0,
            "seed": self.seed,
            "num_ctx": self.num_ctx,
            "num_predict": NUM_PREDICT,
        }

    def _chat(self, text: str) -> tuple[str, str]:
        """Return (content, done_reason)."""
        payload = {
            "model": self.model,
            "messages": build_messages(self.examples, text),
            "format": RESPONSE_SCHEMA,
            "stream": False,
            "think": False,
            "options": self.options(),
        }
        response = _post("/api/chat", payload)
        content = str(response.get("message", {}).get("content", ""))
        return content, str(response.get("done_reason", ""))

    def _detect(self, text: str) -> list[Span]:
        try:
            raw, done_reason = self._chat(text)
        except (urllib.error.URLError, TimeoutError) as exc:
            # Abort the evaluation: a silent empty prediction would look like a miss.
            raise RuntimeError(
                f"Ollama request failed ({exc}); is `ollama serve` running?"
            ) from exc
        truncated = int(done_reason not in ("stop", ""))
        mentions = parse_response(raw)
        with self._lock:
            self.raw_outputs[text_key(text)] = {"response": raw, "done_reason": done_reason}
        if mentions is None:
            with self._lock:
                self.stats = self.stats + MappingStats(
                    documents=1, parse_failures=1, truncated=truncated
                )
            return []
        spans, stats = map_mentions(text, mentions, source=self.name)
        stats.truncated = truncated
        with self._lock:
            self.stats = self.stats + stats
        return spans

    def config(self) -> dict[str, Any]:
        info: dict[str, Any] = {}
        try:
            show = _post("/api/show", {"model": self.model}, timeout=30)
            info = {
                k: show.get("details", {}).get(k)
                for k in ("parameter_size", "quantization_level", "family")
            }
            info["digest"] = next(
                (
                    m["digest"]
                    for m in _get("/api/tags").get("models", [])
                    if m["name"] == self.model
                ),
                None,
            )
            info["ollama_version"] = _get("/api/version")["version"]
            loaded: dict[str, Any] = next(
                (m for m in _get("/api/ps").get("models", []) if m["name"] == self.model), {}
            )
            info["size_bytes"] = loaded.get("size")
            info["size_vram_bytes"] = loaded.get("size_vram")  # == size_bytes -> fully on GPU
        except (urllib.error.URLError, TimeoutError, KeyError):
            info["error"] = "ollama metadata unavailable"
        return {
            "model": self.model,
            **info,
            "options": {**self.options(), "think": False},
            "prompt": prompt_fingerprint(self.examples),
            "mapping_stats": self.stats.__dict__,
        }


def write_prompt_preview(path: Path, detector: LLMDetector) -> None:
    """Human-readable copy of the exact prompt (the note replaced by <NOTE>)."""
    msgs = build_messages(detector.examples, "<NOTE>")
    path.write_text(
        "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in msgs) + "\n",
        encoding="utf-8",
        newline="\n",
    )
