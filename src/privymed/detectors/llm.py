"""Local LLM (Qwen via Ollama) as a PrivyMed detector (Milestone 5).

Inference is fully local: requests go to the Ollama server on 127.0.0.1 only, so no
document text leaves the machine. Decoding is greedy (temperature 0, fixed seed) with
Ollama's JSON-schema structured output; Qwen's "thinking" mode is disabled.
"""

from __future__ import annotations

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
from privymed.llm.prompt import RESPONSE_SCHEMA, build_messages, prompt_fingerprint, select_examples
from privymed.schema import Span

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.5:4b"


def _post(path: str, payload: dict[str, Any], timeout: float = 300.0) -> dict[str, Any]:
    req = urllib.request.Request(
        OLLAMA_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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
        self.num_ctx = num_ctx
        self.seed = seed
        train = read_documents(find_repo_root() / "data/synthetic/v1/train.jsonl")
        self.examples = select_examples(train, k=int(n_examples))
        self.stats = MappingStats()
        self._lock = threading.Lock()

    def reset_stats(self) -> None:
        """Called by the evaluation runner after warm-up calls."""
        with self._lock:
            self.stats = MappingStats()

    def _chat(self, text: str) -> str:
        payload = {
            "model": self.model,
            "messages": build_messages(self.examples, text),
            "format": RESPONSE_SCHEMA,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "seed": self.seed, "num_ctx": self.num_ctx},
        }
        response = _post("/api/chat", payload)
        return str(response.get("message", {}).get("content", ""))

    def _detect(self, text: str) -> list[Span]:
        try:
            raw = self._chat(text)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"Ollama request failed ({exc}); is `ollama serve` running?"
            ) from exc
        mentions = parse_response(raw)
        if mentions is None:
            with self._lock:
                self.stats = self.stats + MappingStats(documents=1, parse_failures=1)
            return []
        spans, stats = map_mentions(text, mentions, source=self.name)
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
            tags = json.loads(urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=30).read())
            info["digest"] = next(
                (m["digest"] for m in tags.get("models", []) if m["name"] == self.model), None
            )
            info["ollama_version"] = json.loads(
                urllib.request.urlopen(OLLAMA_URL + "/api/version", timeout=30).read()
            )["version"]
        except (urllib.error.URLError, TimeoutError, KeyError):
            info["error"] = "ollama metadata unavailable"
        return {
            "model": self.model,
            **info,
            "options": {
                "temperature": 0,
                "seed": self.seed,
                "num_ctx": self.num_ctx,
                "think": False,
            },
            "prompt": prompt_fingerprint(self.examples),
            "mapping_stats": self.stats.__dict__,
        }


def write_prompt_preview(path: Path, detector: LLMDetector) -> None:
    """Human-readable copy of the exact prompt (without the note), for the report."""
    msgs = build_messages(detector.examples, "<NOTE>")
    path.write_text(
        "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in msgs) + "\n",
        encoding="utf-8",
        newline="\n",
    )
