#!/usr/bin/env python3
"""P3-3 消融矩阵分块 worker（shell-level 并行；每个进程独立，无共享信号量）。

用法：
  python3 scripts/_p33_ablation_worker.py --chunk 0 --chunks 10 --warmup 1000
  → 计算 t_idx ∈ [warmup, N) 中 t_idx % chunks == chunk 的 target 的
    D-ablation 候选（FULL + 9 个 one-feature-at-a-time），
    写入 .agnes/work/p33/ablation_chunk_{chunk}.json

每个 worker 串行处理自己那 1/chunks 的 targets（含昂贵的 D 枚举 ×10），
10 个 worker 并发 → 墙钟约等于 1/10。结果与直接 recommend() 一致
（equivalence 由 test 校验）。"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from src.evaluation import window_study as ws
from src.evaluation.feature_ablation import ablation_candidates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, required=True)
    ap.add_argument("--chunks", type=int, default=10)
    ap.add_argument("--warmup", type=int, default=ws.COMMON_WARMUP)
    ap.add_argument("--dataset", default="data/research/dlt-full-history.json")
    ap.add_argument("--out", default=".agnes/work/p33")
    args = ap.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    issues = ws.load_issues(str(root / args.dataset))
    cfg = ws.production_cfg()
    n = len(issues)
    t_idxs = [t for t in range(args.warmup, n) if t % args.chunks == args.chunk]

    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    chunk_file = out_dir / f"ablation_chunk_{args.chunk}.json"

    data: dict[str, dict] = {}
    for i, t in enumerate(t_idxs):
        data[str(t)] = ablation_candidates(t, issues, cfg)
        if (i + 1) % 200 == 0:
            print(f"  ablation chunk {args.chunk}: {i + 1}/{len(t_idxs)}")
    chunk_file.write_text(json.dumps(data), encoding="utf-8")
    print(f"[ablation worker {args.chunk}/{args.chunks}] {len(t_idxs)} targets "
          f"→ {chunk_file.name} DONE")


if __name__ == "__main__":
    main()
