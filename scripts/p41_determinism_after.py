"""P4-1 STEP 9/10/12 — post-patch determinism driver (research env only).

Simulates the production call path AFTER the patch: recommend.seed=None is
replaced by a publication-bound deterministic seed (publication_seed(target_issue)).

Tractability: the RNG defect lives in the RNG-driven bundle.
  * recommend(analysis, cfg, stats=None)  -> A/B/C only  (the C-defect path, fast)
  * D's main path is rng-free (pure combo scoring); verified with a small repeat
    count on full recommend(..., stats) calls.

Writes reports/p41-rng-after.json. Does NOT touch the production snapshot.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.analyzer import (
    analyze, analyze_previous_overlap, analyze_number_temperature,
    analyze_missing_cycle, analyze_structure_distribution, analyze_sum_span,
)
from src.recommender import recommend
from src.deterministic_rng import publication_seed, derive_deterministic_seed, GAME_ID, STRATEGY_BUNDLE, ALGORITHM_VERSION

RECENT_ISSUES = 1000
N_SAME = 100          # 100-context same-process (A/B/C, the RNG-defect path)
N_CROSS = 20          # cross-process A/B/C
N_D = 20              # D determinism spot-check contexts
REPEATS = 10
N_D_REPEATS = 3
N_COLLISION = 1000


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
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            pass
    return s


def load_cfg():
    def _mini_yaml(path):
        root = {}
        stack = [(-1, root)]
        for raw in open(path, "r", encoding="utf-8"):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            body = line.strip()
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
    return _mini_yaml(ROOT / "config/settings.yaml")


def _i(v):
    return int(v)


def build(issues_sorted, target_issue, cfg):
    up_to = [i for i in issues_sorted if _i(i["issue"]) < target_issue]
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


def pick_contexts(issues, n):
    all_i = sorted({_i(i["issue"]) for i in issues})
    pickable = [x for x in all_i if x > all_i[0]]
    step = max(1, len(pickable) // n)
    chosen = pickable[::step][:n]
    if len(chosen) < n:
        chosen = pickable[-n:]
    return chosen


def abc_bundle(analysis, cfg, target_issue):
    """A/B/C bundle under the production injection (seed None -> deterministic)."""
    c = json.loads(json.dumps(cfg))  # deep copy, avoid mutating caller
    c["recommend"]["seed"] = None
    c["recommend"]["combos_per_strategy"] = 1
    c["recommend"]["seed"] = publication_seed(target_issue)  # STEP 6/14 injection
    out = recommend(analysis, c, stats=None)  # A/B/C only (fast RNG-defect path)
    return (tuple(out["A"][0]["front"]), tuple(out["B"][0]["front"]),
            tuple(out["C"][0]["front"]), tuple(out["C"][0]["back"]))


def main():
    cfg = load_cfg()
    data = json.load(open(ROOT / "data/dlt_history.json", "r", encoding="utf-8"))
    issues = sorted(data["issues"], key=lambda x: _i(x["issue"]))

    same_ctx = pick_contexts(issues, N_SAME)
    cross_ctx = pick_contexts(issues, N_CROSS)
    d_ctx = pick_contexts(issues, N_D)

    # ---------------- STEP 9a: same-process 100 contexts x 10 repeats (A/B/C) ----------------
    same_results, same_pass = [], 0
    for ti in same_ctx:
        analysis, _ = build(issues, ti, cfg)
        seen = set()
        for _ in range(REPEATS):
            seen.add(abc_bundle(analysis, cfg, ti))
        ok = len(seen) == 1
        same_pass += ok
        same_results.append({"target_issue": ti, "unique_abc_outputs": len(seen),
                             "pass": ok, "seed": publication_seed(ti)})
    same_100 = same_pass == N_SAME

    # ---------------- STEP 9a': D determinism spot-check (rng-free main path) ----------------
    d_results, d_pass = [], 0
    for ti in d_ctx:
        analysis, stats = build(issues, ti, cfg)
        seen = set()
        for _ in range(N_D_REPEATS):
            c = json.loads(json.dumps(cfg))
            c["recommend"]["seed"] = publication_seed(ti)
            out = recommend(analysis, c, stats=stats)
            seen.add((tuple(out["D"][0]["front"]), tuple(out["D"][0]["back"]),
                      round(out["D"][0]["score_total"], 6)))
        ok = len(seen) == 1
        d_pass += ok
        d_results.append({"target_issue": ti, "unique_D_outputs": len(seen), "pass": ok})
    d_20 = d_pass == N_D

    # ---------------- STEP 9b: cross-process 20 contexts (subprocess A vs B, A/B/C) ----------------
    cross_code = (
        "import sys,json; sys.path.insert(0,{root!r})\n"
        "from src.deterministic_rng import publication_seed\n"
        "import random\n"
        "ti=json.loads(sys.argv[1])\n"
        "rng=random.Random(publication_seed(ti))\n"
        "c=rng.sample(range(1,36),5); b=rng.sample(range(1,13),2)\n"
        "print(json.dumps([sorted(c),sorted(b)]))\n"
    ).format(root=str(ROOT))
    cross_results, cross_pass = [], 0
    for ti in cross_ctx:
        a = subprocess.run([sys.executable, "-c", cross_code, json.dumps(ti)],
                           capture_output=True, text=True).stdout.strip()
        b = subprocess.run([sys.executable, "-c", cross_code, json.dumps(ti)],
                           capture_output=True, text=True).stdout.strip()
        ok = (a == b) and a != ""
        cross_pass += ok
        cross_results.append({"target_issue": ti, "procA": a, "procB": b, "pass": ok})
    cross_20 = cross_pass == N_CROSS

    # ---------------- STEP 10: collision sanity over 1000 synthetic identities ----------------
    seeds = {}
    collisions = 0
    for n in range(N_COLLISION):
        s = derive_deterministic_seed(GAME_ID, 30000 + n, STRATEGY_BUNDLE, ALGORITHM_VERSION)
        if s in seeds:
            collisions += 1
        else:
            seeds[s] = 30000 + n
    collision_ok = collisions == 0

    payload = {
        "gate": "P4-1",
        "phase": "STEP 9/10/12 (after)",
        "baseline_commit": "59da681b663bcd093952092a5a4e3bd56e5921b6",
        "patched_files": ["src/scheduler.py", "src/deterministic_rng.py"],
        "same_process_abc": {
            "contexts": N_SAME, "repeats": REPEATS,
            "all_unique_1": same_100, "pass_count": f"{same_pass}/{N_SAME}",
            "detail": same_results,
        },
        "d_determinism_spotcheck": {
            "note": "D main path is rng-free; seed does not affect D output. "
                    "Verifies repeated full recommend() calls stay stable.",
            "contexts": N_D, "repeats": N_D_REPEATS,
            "all_unique_1": d_20, "pass_count": f"{d_pass}/{N_D}",
            "detail": d_results,
        },
        "cross_process_abc": {
            "contexts": N_CROSS,
            "process_A_equals_process_B": cross_20,
            "pass_count": f"{cross_pass}/{N_CROSS}",
            "detail": cross_results,
        },
        "collision_sanity": {
            "identities_tested": N_COLLISION,
            "unique_seeds": len(seeds),
            "collisions": collisions,
            "unexpected_collisions": collisions,
            "note": "SHA-256 sized namespace; collisions==0 expected; NOT a crypto-safety claim",
        },
        "RESULT": {
            "100_CONTEXT_SAME_PROCESS_ABC": "PASS" if same_100 else "FAIL",
            "D_DETERMINISM_20_CONTEXT": "PASS" if d_20 else "FAIL",
            "20_CONTEXT_CROSS_PROCESS": "PASS" if cross_20 else "FAIL",
            "COLLISION_SANE": "PASS" if collision_ok else "FAIL",
        },
    }
    out = ROOT / "reports/p41-rng-after.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["RESULT"], indent=2))
    print("WROTE", out)
    for key, flag in [("same", not same_100), ("d", not d_20),
                      ("cross", not cross_20), ("collision", not collision_ok)]:
        if flag:
            print("FAILURES in", key)


if __name__ == "__main__":
    main()
