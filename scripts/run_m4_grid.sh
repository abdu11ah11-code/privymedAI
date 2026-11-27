#!/usr/bin/env bash
# Milestone 4 experiment grid: models x seeds 13, 42, 7, sequential on one GPU.
# Usage: bash scripts/run_m4_grid.sh [model ...]   (default: distilbert roberta deberta)
# Each run refuses to start from uncommitted code (privymed-train without --allow-dirty).
set -euo pipefail
export HF_HUB_DISABLE_SYMLINKS_WARNING=1
models=("$@")
[ ${#models[@]} -eq 0 ] && models=(distilbert roberta deberta)
for model in "${models[@]}"; do
  for seed in 13 42 7; do
    echo "=== ${model} seed ${seed} ==="
    uv run privymed-train --config "configs/train/${model}.yaml" --seed "${seed}" --run-name "${model}_s${seed}" 2>&1 \
      | grep -E "privymed.training.train|best dev strict|Error|Traceback" || true
  done
done
echo "=== grid done ==="
