"""Explicit live Geoapify check with mocked extraction; never loads model weights."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
import os

import workflows


def main():
    # The file is consumed by python-dotenv only; never print configuration/keys.
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    key = os.environ.get("GEOAPIFY_API_KEY", "").strip()
    if not key:
        print("Geoapify smoke check: missing API key")
        return 1
    cases = [
        ("Stockholm", "Stockholm, Sweden", "Sweden", "se", None, "city"),
        ("Sveavägen", "Sveavägen, Stockholm, Sweden", "Sweden", "se", None, "street"),
        ("Paris", "France", "France", "fr", None, "country"),
        ("Europa", "Europe", None, None, "Europe", "continent"),
    ]
    places = [{"mention": name, "query": query, "roles": ["event-site"], "evidence": [name],
               "country": country, "country_code": code, "continent": continent,
               "city": "Stockholm" if code == "se" else None, "region": None, "granularity": level}
              for name, query, country, code, continent, level in cases]
    runtime = SimpleNamespace(retry_limit=1, workflow_settings=workflows.WorkflowSettings(True, False, key))
    # Exercise orchestration and the real location client without model startup.
    with patch.object(workflows, "WORKFLOWS", {}), patch.object(workflows, "generate_title", return_value="Platskontroll"), \
            patch.object(workflows, "generate_text", Mock(return_value=json.dumps({"locations": places}))):
        result = workflows.run_workflows("Händelser i Stockholm, Sveavägen, Paris och Europa.", runtime, {})
    entries = result["location"] or []
    expected = {case[0]: case[-1] for case in cases}
    passed = True
    for name, level in expected.items():
        entry = next((entry for entry in entries if name in entry["mentions"]), None)
        ok = bool(entry and entry["status"] == "resolved" and entry["granularity"] == level)
        print(f"{name}: {'PASS' if ok else 'FAIL'} ({entry['granularity'] if entry else 'no result'})")
        passed &= ok
    if result["location_error"]:
        print(f"Geoapify smoke check: nonfatal error code {result['location_error']['code']}")
        passed = False
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
