"""Run real-model article checks against an already-running backend."""

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def request_json(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=300) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")
    health = request_json(f"{base_url}/health")
    assert health["status"] == "ok" and health["model_loaded"] is True
    schema = request_json(f"{base_url}/openapi.json")
    status = schema["components"]["schemas"]["AnalyzeEventResponse"]["properties"]["status"]
    if status.get("const") != "ok":
        raise RuntimeError("Running backend has the old API. Restart it before the article check.")

    directory = Path(__file__).parent
    categories = json.loads((directory / "schemas" / "risks.json").read_text(encoding="utf-8"))
    names = {category["ID"]: category["name"] for category in categories}
    for filename in ("test-event.txt", "test-event2.txt"):
        text = (directory.parent / "data" / filename).read_text(encoding="utf-8")
        result = request_json(f"{base_url}/analyze-event", {"text": text})
        assert result["status"] == "ok"
        matches = result["results"]["risks"]
        assert isinstance(matches, list)
        assert all(match["ID"] in names and match["name"] == names[match["ID"]] for match in matches)
        assert len({match["ID"] for match in matches}) == len(matches)
        print(json.dumps({"article": filename, "result": result}, ensure_ascii=False), flush=True)
    assert request_json(f"{base_url}/health") == health
    print("Both article response contracts passed. Review category choices manually.")


if __name__ == "__main__":
    main()
