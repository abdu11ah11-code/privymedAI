"""Window merging and the linear warmup/decay schedule (no model needed)."""

from __future__ import annotations

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


def test_fp16_stored_checkpoint_is_loaded_as_fp32_for_training() -> None:
    """Regression: deberta-v3-base is stored in fp16; Transformers 5 keeps that dtype unless
    told otherwise, and fp16 master weights made the training loss NaN."""
    import inspect

    from privymed.training import train

    source = inspect.getsource(train.train)
    assert "dtype=torch.float32" in source
    assert "FloatingPointError" in source  # non-finite loss aborts the run
