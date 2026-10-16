"""Run real-model article checks against an already-running backend."""

import argparse
import json
import os
from getpass import getpass
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


def request_json(url: str, payload: dict | None = None, *, opener=None, origin: str | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if payload is not None and origin:
        headers["Origin"] = origin
    request = Request(url, data=data, headers=headers)
    with (opener.open if opener else urlopen)(request, timeout=300) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default=os.environ.get("ANALYTICS_EMAIL"), help="Existing user email (or ANALYTICS_EMAIL)")
    parser.add_argument("--origin", default="http://localhost:8000", help="An AUTH_ALLOWED_ORIGINS entry")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")
    if not args.email:
        parser.error("--email or ANALYTICS_EMAIL is required for authenticated analysis")
    password = os.environ.get("ANALYTICS_PASSWORD") or getpass("User password: ")
    opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def call(url: str, payload: dict | None = None) -> dict:
        return request_json(url, payload, opener=opener, origin=args.origin)

    call(f"{base_url}/auth/login", {"email": args.email, "password": password})
    health = call(f"{base_url}/health")
    assert health["status"] == "ok" and health["model_loaded"] is True
    schema = call(f"{base_url}/openapi.json")
    status = schema["components"]["schemas"]["AnalyzeEventResponse"]["properties"]["status"]
    if status.get("const") != "ok":
        raise RuntimeError("Running backend has the old API. Restart it before the article check.")

    directory = Path(__file__).resolve().parents[1]
    names_by_workflow = {}
    for name in ("risks", "reach", "service", "properties", "protection"):
        categories = json.loads((directory / "schemas" / f"{name}.json").read_text(encoding="utf-8"))
        names_by_workflow[name] = {category["ID"]: category["name"] for category in categories}
    for filename in ("test-event.txt", "test-event2.txt"):
        text = (directory.parent / "data" / "events" / filename).read_text(encoding="utf-8")
        result = call(f"{base_url}/analyze-event", {"text": text})
        assert result["status"] == "ok"
        assert set(result["results"]) == set(names_by_workflow), "Restart backend to load all workflows"
        for name, names in names_by_workflow.items():
            matches = result["results"][name]
            assert isinstance(matches, list)
            assert all(match["ID"] in names and match["name"] == names[match["ID"]] for match in matches)
            assert len({match["ID"] for match in matches}) == len(matches)
        print(json.dumps({"article": filename, "result": result}, ensure_ascii=False), flush=True)
    assert call(f"{base_url}/health") == health
    print("Both article response contracts passed. Review category choices manually.")


if __name__ == "__main__":
    main()
