import sys, json, hashlib
sys.path.insert(0, ".")
def cj(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

d = json.load(open("public/data/published_recommendations.json"))
for s in d["items"]:
    if str(s.get("issue")) == "26112":
        n = s.get("numbers") or {}
        dd = {"issue": str(s["issue"]), "primary_strategy": s.get("primary_strategy"),
              "front": n.get("front"), "back": n.get("back"), "reason": s.get("reason"),
              "final_score": s.get("final_score"), "final_breakdown": s.get("final_breakdown"),
              "model_version": s.get("model_version"), "explanation": s.get("explanation")}
        h = hashlib.sha256(cj(dd).encode("utf-8")).hexdigest()
        print("STEP7 26112 snapshot hash match:", h == s["snapshot_hash"])
        print("  computed:", h)
        print("  stored  :", s["snapshot_hash"])
        print("  numbers :", n)
