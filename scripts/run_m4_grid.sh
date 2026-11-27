#!/usr/bin/env bash
# Milestone 4 experiment grid: models x seeds, sequential on one GPU.
# Usage: bash scripts/run_m4_grid.sh [model ...]            (default: distilbert roberta deberta)
#        SEEDS="13 42" bash scripts/run_m4_grid.sh roberta   (subset of seeds; default 13 42 7)
# Each run refuses to start from uncommitted code (privymed-train without --allow-dirty).
# A failed run stops the grid (review M4-6: "|| true" used to hide crashes such as the NaN run).
set -uo pipefail
export HF_HUB_DISABLE_SYMLINKS_WARNING=1
models=("$@")
[ ${#models[@]} -eq 0 ] && models=(distilbert roberta deberta)
for model in "${models[@]}"; do
  for seed in ${SEEDS:-13 42 7}; do
    echo "=== ${model} seed ${seed} ==="
    uv run privymed-train --config "configs/train/${model}.yaml" --seed "${seed}" \
      --run-name "${model}_s${seed}" 2>&1 \
      | grep --line-buffered -E "privymed.training.train|best dev strict|Error|Traceback"
    status=${PIPESTATUS[0]}
    if [ "${status}" -ne 0 ]; then
      echo "=== ${model} seed ${seed} FAILED (exit ${status}) ==="
      exit "${status}"
    fi
  done
done
echo "=== grid done ==="
