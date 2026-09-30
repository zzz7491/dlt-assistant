#!/usr/bin/env python3
"""P3-2 矩阵分块 worker（shell-level 并行；每个进程独立，无共享信号量）。

用法：
  python scripts/_p32_matrix_worker.py --chunk 0 --chunks 10 --warmup 1000
  → 计算 t_idx ∈ [warmup, N) 中 t_idx % chunks == chunk 的全部 (t, window) 候选，
    写入 .agnes/work/p32/matrix_chunk_{chunk}.json

每个 worker 串行处理自己那 1/chunks 的 targets（含昂贵的 D 枚举），
10 个 worker 并发 → 墙钟约等于 1/10。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from src.evaluation import window_study as ws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, required=True)
    ap.add_argument("--chunks", type=int, default=10)
    ap.add_argument("--warmup", type=int, default=ws.COMMON_WARMUP)
    ap.add_argument("--dataset", default="data/research/dlt-full-history.json")
    ap.add_argument("--out", default=".agnes/work/p32")
    args = ap.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    issues = ws.load_issues(str(root / args.dataset))
    cfg = ws.production_cfg()
    n = len(issues)
    t_idxs = [t for t in range(args.warmup, n) if t % args.chunks == args.chunk]

    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    chunk_file = out_dir / f"matrix_chunk_{args.chunk}.json"

    data: dict[str, dict] = {}
    for i, t in enumerate(t_idxs):
        rec: dict[str, dict] = {}
        for w in ws.WINDOWS:
            rec[w] = ws.compute_candidates(t, w, cfg)
        data[str(t)] = rec
        if (i + 1) % 200 == 0:
            print(f"  chunk {args.chunk}: {i+1}/{len(t_idxs)} targets")

    chunk_file.write_text(json.dumps(data), encoding="utf-8")
    print(f"[worker {args.chunk}/{args.chunks}] {len(t_idxs)} targets × {len(ws.WINDOWS)} windows "
          f"→ {chunk_file.name} DONE")


if __name__ == "__main__":
    main()
