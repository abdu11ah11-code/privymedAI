#!/usr/bin/env bash
# Milestone 4 experiment grid: 3 models x 3 seeds, sequential on one GPU.
# Each run refuses to start from uncommitted code (privymed-train without --allow-dirty).
set -euo pipefail
export HF_HUB_DISABLE_SYMLINKS_WARNING=1
for model in distilbert roberta deberta; do
  for seed in 13 42 7; do
    echo "=== ${model} seed ${seed} ==="
    uv run privymed-train --config "configs/train/${model}.yaml" --seed "${seed}" --run-name "${model}_s${seed}" 2>&1 \
      | grep -E "privymed.training.train|best dev strict|Error|Traceback" || true
  done
done
echo "=== grid done ==="
