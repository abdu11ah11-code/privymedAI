"""Window merging and the linear warmup/decay schedule (no model needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from privymed.training.inference import TokenPrediction, merge_windows  # noqa: E402
from privymed.training.train import linear_warmup_decay  # noqa: E402


def tp(offset: tuple[int, int], label: int, edge: int) -> TokenPrediction:
    return TokenPrediction(offset=offset, label_id=label, prob=0.9, edge_distance=edge)


def test_merge_keeps_most_centred_prediction() -> None:
    w1 = [tp((0, 2), 1, 0), tp((3, 5), 1, 1), tp((6, 8), 2, 0)]  # (6,8) at w1's edge
    w2 = [tp((3, 5), 3, 0), tp((6, 8), 4, 1), tp((9, 11), 4, 0)]  # (6,8) centred in w2
    merged = merge_windows([w1, w2])
    assert [m.offset for m in merged] == [(0, 2), (3, 5), (6, 8), (9, 11)]
    assert [m.label_id for m in merged] == [1, 1, 4, 4]


def test_merge_is_order_independent_for_unique_offsets() -> None:
    a = [tp((0, 1), 1, 0)]
    b = [tp((2, 3), 2, 0)]
    assert merge_windows([a, b]) == merge_windows([b, a])


def test_linear_warmup_then_decay() -> None:
    param = torch.nn.Parameter(torch.zeros(1))
    opt = torch.optim.SGD([param], lr=1.0)
    sched = linear_warmup_decay(opt, warmup_steps=2, total_steps=6)
    lrs = []
    for _ in range(6):
        lrs.append(opt.param_groups[0]["lr"])
        opt.step()
        sched.step()
    assert lrs == pytest.approx([0.0, 0.5, 1.0, 0.75, 0.5, 0.25])


def test_fp16_stored_checkpoint_is_loaded_as_fp32(tmp_path: Path) -> None:
    """Review M4-10 (behavioural): a checkpoint saved in fp16, like deberta-v3-base, must load
    with fp32 master weights; fp16 master weights made the training loss NaN."""
    from transformers import BertConfig, BertForTokenClassification

    from privymed.training.alignment import LABELS
    from privymed.training.train import load_token_classifier

    cfg = BertConfig(
        vocab_size=64,
        hidden_size=16,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=32,
    )
    cfg.num_labels = len(LABELS)
    BertForTokenClassification(cfg).to(torch.float16).save_pretrained(tmp_path)
    model = load_token_classifier(tmp_path)
    assert {p.dtype for p in model.parameters()} == {torch.float32}
    assert model.config.num_labels == len(LABELS)
