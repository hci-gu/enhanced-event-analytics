import json
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
RESOURCES_DIR = BACKEND_DIR / "resources"


def test_risk_catalogue_has_one_document_per_category():
    categories = json.loads((BACKEND_DIR / "schemas" / "risks.json").read_text(encoding="utf-8"))
    catalogue = json.loads((RESOURCES_DIR / "risk-catalogue.json").read_text(encoding="utf-8"))
    mapping = catalogue["risks"]

    assert len(categories) == len(mapping) == 24
    assert set(mapping) == {category["ID"] for category in categories}
    assert len(set(mapping.values())) == 24

    guide = catalogue["user_guide"]
    assert type(guide["auto_include_when_risks_present"]) is bool
    assert guide["file"] not in mapping.values()

    document_paths = [RESOURCES_DIR / file for file in [*mapping.values(), guide["file"]]]
    catalogue_dir = (RESOURCES_DIR / "risk-catalogue").resolve()
    for path in document_paths:
        assert path.resolve().parent == catalogue_dir
        assert path.suffix == ".pdf"
        assert path.is_file(), f"Missing risk catalogue document: {path}"

    assert {path.resolve() for path in document_paths} == {
        path.resolve() for path in catalogue_dir.glob("*.pdf")
    }
