# Historical research validator.
# Not part of canonical runtime regression suite.
# Targets legacy recommendation output schema.
"""Validate recommendation_new.json format"""
import json
import sys
from pathlib import Path

def validate_json():
    """Validate JSON file format and completeness"""
    json_path = Path(__file__).parent / "public" / "data" / "recommendation_new.json"
    
    if not json_path.exists():
        print("[FAIL] File not found:", json_path)
        return False
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    errors = []
    
    # Check required fields
    required_fields = ["generated_at", "issue", "main", "backup", "stats", "notice"]
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    # Check main recommendation structure
    main = data.get("main", {})
    if "front" not in main or "back" not in main:
        errors.append("Main recommendation missing front or back field")
    else:
        front = main["front"]
        back = main["back"]
        
        # Validate number counts
        if len(front) != 5:
            errors.append(f"Front should have 5 numbers, got {len(front)}")
        if len(back) != 2:
            errors.append(f"Back should have 2 numbers, got {len(back)}")
        
        # Validate number ranges
        if not all(1 <= n <= 35 for n in front):
            errors.append("Front numbers out of range [1,35]")
        if not all(1 <= n <= 12 for n in back):
            errors.append("Back numbers out of range [1,12]")
        
        # Validate no duplicates
        if len(set(front)) != 5:
            errors.append("Duplicate numbers in front")
        if len(set(back)) != 2:
            errors.append("Duplicate numbers in back")
    
    # Check backup options
    backup = data.get("backup", [])
    if len(backup) < 2:
        errors.append(f"Need at least 2 backup options, got {len(backup)}")
    
    # Check reasons
    reasons = main.get("reasons", [])
    if len(reasons) == 0:
        errors.append("No reasons provided")
    
    # Output results
    print("=" * 60)
    print("JSON Validation Result")
    print("=" * 60)
    
    if errors:
        print(f"\n[FAIL] Validation FAILED with {len(errors)} error(s):\n")
        for err in errors:
            print(f"   - {err}")
        return False
    else:
        print("\n[PASS] Validation PASSED\n")
        print(f"Main Recommendation:")
        print(f"   Front: {main['front']}")
        print(f"   Back: {main['back']}")
        print(f"   Score: {main.get('score', 'N/A')}")
        print(f"   Reasons: {len(reasons)} items")
        print(f"\nBackup Options: {len(backup)}")
        print(f"\nGenerated at: {data.get('generated_at')}")
        print(f"\nNotice: {data.get('notice', 'N/A')}")
        return True


if __name__ == "__main__":
    success = validate_json()
    sys.exit(0 if success else 1)
