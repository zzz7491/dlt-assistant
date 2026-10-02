"""P4-1 STEP 3 — reproduce the C RNG reproducibility defect (research env only).

For >=10 historical publication contexts (each pinned to a target_issue), build the
SAME deterministic analysis+stats, then call production recommend() with
cfg["recommend"]["seed"] = None repeatedly and count how many UNIQUE C candidates
appear. If a context yields >1 unique C candidate, the defect is confirmed.

This script:
  - does NOT modify the production snapshot (reads data/dlt_history.json read-only),
  - does NOT select samples or seeds by hit-rate (contexts chosen by fixed issue
    stride; seed is always None),
  - writes reports/p41-rng-before.json.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.analyzer import (
    analyze, analyze_previous_overlap, analyze_number_temperature,
    analyze_missing_cycle, analyze_structure_distribution, analyze_sum_span,
)
from src.recommender import recommend

RECENT_ISSUES = 1000
COMBOS_PER_STRATEGY = 1
REPEATS = 20
N_CONTEXTS = 12


def _mini_yaml_scalar(s):
    s = s.strip()
    if s == "" or s == "~" or s.lower() == "null":
        return None
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _mini_yaml(path):
    """Minimal indentation-based YAML subset parser.

    settings.yaml is a nested dict of scalars only (no lists / anchors / multi-line).
    This avoids a hard dependency on PyYAML in the offline repro/test environment.
    """
    root = {}
    stack = [(-1, root)]  # (indent, dict)
    for raw in open(path, "r", encoding="utf-8"):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()
        # strip trailing comment
        if " #" in body:
            body = body[:body.index(" #")].rstrip()
        if ":" not in body:
            continue
        key, _, val = body.partition(":")
        key = key.strip()
        val = val.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if val == "":
            child = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _mini_yaml_scalar(val)
    return root


def load_cfg():
    return _mini_yaml(ROOT / "config/settings.yaml")


def build_context(issues_sorted, target_issue, cfg):
    """Deterministic analysis+stats for the publication context of target_issue.

    The publication context is 'everything known before target_issue draws'.
    We use the data slice up to (but excluding) target_issue, truncated to the
    most recent RECENT_ISSUES issues (matches production recent_issues=1000).
    """
    up_to = [i for i in issues_sorted if i["issue"] < target_issue]
    window = up_to[-RECENT_ISSUES:]
    analysis = analyze(window, cfg)
    stats = {
        "overlap": analyze_previous_overlap(window),
        "temperature": analyze_number_temperature(window),
        "missing_cycle": analyze_missing_cycle(window),
        "structure": analyze_structure_distribution(window),
        "sum_span": analyze_sum_span(window),
        "prev_issue": window[-1] if window else None,
    }
    return analysis, stats


def main():
    cfg = load_cfg()
    cfg["recommend"]["seed"] = None  # production default
    cfg["recommend"]["combos_per_strategy"] = COMBOS_PER_STRATEGY

    data = json.load(open(ROOT / "data/dlt_history.json", "r", encoding="utf-8"))
    issues = sorted(data["issues"], key=lambda x: x["issue"])
    all_issues = [i["issue"] for i in issues]

    # Choose >=10 contexts by fixed stride across available target issues (no
    # hit-rate based selection). target_issue must have data before it.
    pickable = [x for x in all_issues if x > all_issues[0]]
    step = max(1, len(pickable) // N_CONTEXTS)
    chosen = pickable[::step][:N_CONTEXTS]
    if len(chosen) < 10:
        chosen = pickable[-10:]

    results = []
    defect_confirmed = False
    for ti in chosen:
        analysis, stats = build_context(issues, ti, cfg)
        c_set, a_set, b_set = set(), set(), set()
        for _ in range(REPEATS):
            out = recommend(analysis, cfg, stats=stats)
            c0 = out["C"][0]
            a0 = out["A"][0]
            b0 = out["B"][0]
            c_set.add((tuple(c0["front"]), tuple(c0["back"])))
            a_set.add((tuple(a0["front"]), tuple(a0["back"])))
            b_set.add((tuple(b0["front"]), tuple(b0["back"])))
        n_c = len(c_set)
        results.append({
            "target_issue": ti,
            "repeats": REPEATS,
            "seed": None,
            "unique_C_candidates": n_c,
            "unique_A_candidates": len(a_set),
            "unique_B_candidates": len(b_set),
            "C_front_differs": len({s[0] for s in c_set}) > 1,
            "C_back_differs": len({s[1] for s in c_set}) > 1,
            "reproducible_C": n_c == 1,
        })
        if n_c > 1:
            defect_confirmed = True

    payload = {
        "gate": "P4-1",
        "phase": "STEP 3 (before)",
        "baseline_commit": "59da681b663bcd093952092a5a4e3bd56e5921b6",
        "selection_method": "fixed stride by target_issue; seed=None; no hit-rate selection",
        "repeats_per_context": REPEATS,
        "seed_used": None,
        "contexts": results,
        "n_contexts": len(results),
        "REPRODUCIBILITY_DEFECT_CONFIRMED": bool(defect_confirmed),
        "note": "seed=None -> random.Random(None) uses OS entropy; C/A/B differ across identical inputs.",
    }
    out_path = ROOT / "reports/p41-rng-before.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("\nWROTE", out_path, "defect_confirmed=", defect_confirmed)


if __name__ == "__main__":
    main()
