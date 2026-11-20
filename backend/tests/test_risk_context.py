import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pypdf import PdfWriter

import risk_context
from risk_context import CATALOGUE_PATH, RiskDocumentError, load_risk_documents


@pytest.fixture
def manifest(tmp_path):
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps({
        "risks": {"stormar": "storm.pdf", "översvämningar": "flood.pdf"},
        "user_guide": {"file": "guide.pdf", "auto_include_when_risks_present": False},
    }), encoding="utf-8")
    return path


def enable_guide(manifest):
    catalogue = json.loads(manifest.read_text(encoding="utf-8"))
    catalogue["user_guide"]["auto_include_when_risks_present"] = True
    manifest.write_text(json.dumps(catalogue), encoding="utf-8")


def test_empty_risks_do_not_read_manifest_or_pdfs(tmp_path):
    assert load_risk_documents([], manifest_path=tmp_path / "missing.json") == ()


@pytest.mark.parametrize("include_guide", [False, True])
def test_selection_deduplicates_risks_and_includes_guide_once(manifest, monkeypatch, include_guide):
    if include_guide:
        enable_guide(manifest)
    read = Mock(side_effect=lambda root, source, risk_id: (risk_id, source))
    monkeypatch.setattr(risk_context, "_read_document", read)
    documents = load_risk_documents(["stormar", "översvämningar", "stormar"], manifest_path=manifest)
    expected = [("stormar", "storm.pdf"), ("översvämningar", "flood.pdf")]
    if include_guide:
        expected.append((None, "guide.pdf"))
    assert documents == tuple(expected)
    assert read.call_count == len(expected)
    assert load_risk_documents([], manifest_path=manifest) == ()


def test_page_numbers_and_swedish_unicode_are_preserved(tmp_path, monkeypatch):
    path = tmp_path / "swedish.pdf"
    path.touch()
    pages = [SimpleNamespace(extract_text=Mock(return_value=text)) for text in
             ["  Åska, översvämningar och värmeböljor.  ", None, "Nästa sida."]]
    monkeypatch.setattr(risk_context, "PdfReader", Mock(return_value=SimpleNamespace(
        is_encrypted=False, pages=pages,
    )))
    document = risk_context._read_document(tmp_path, path.name, "åska_och_blixtnedslag")
    assert [page.number for page in document.pages] == [1, 2, 3]
    assert document.pages[1].text == ""
    assert document.text == "Åska, översvämningar och värmeböljor.\n\n\n\nNästa sida."
    assert document.risk_id == "åska_och_blixtnedslag"
    assert document.source == path.name


@pytest.mark.parametrize("source", ["missing.pdf", "../outside.pdf", "storm.txt"])
def test_missing_or_invalid_paths_fail(manifest, source):
    catalogue = json.loads(manifest.read_text(encoding="utf-8"))
    catalogue["risks"]["stormar"] = source
    manifest.write_text(json.dumps(catalogue), encoding="utf-8")
    with pytest.raises(RiskDocumentError):
        load_risk_documents(["stormar"], manifest_path=manifest)


def test_unknown_risk_fails_before_reading_pdfs(manifest, monkeypatch):
    read = Mock()
    monkeypatch.setattr(risk_context, "_read_document", read)
    with pytest.raises(RiskDocumentError, match="unmapped risk ID"):
        load_risk_documents(["unknown"], manifest_path=manifest)
    read.assert_not_called()


@pytest.mark.parametrize("content", ["not JSON", "[]", '{"risks": {}, "user_guide": null}'])
def test_invalid_manifest_is_reported(manifest, content):
    manifest.write_text(content, encoding="utf-8")
    with pytest.raises(RiskDocumentError, match="manifest"):
        load_risk_documents(["stormar"], manifest_path=manifest)


def test_guide_setting_requires_boolean(manifest):
    catalogue = json.loads(manifest.read_text(encoding="utf-8"))
    catalogue["user_guide"]["auto_include_when_risks_present"] = "false"
    manifest.write_text(json.dumps(catalogue), encoding="utf-8")
    with pytest.raises(RiskDocumentError, match="manifest"):
        load_risk_documents(["stormar"], manifest_path=manifest)


@pytest.mark.parametrize("kind", ["corrupt", "blank", "encrypted"])
def test_unreadable_pdfs_fail_explicitly(tmp_path, kind):
    path = tmp_path / "bad.pdf"
    if kind == "corrupt":
        path.write_bytes(b"not a PDF")
    else:
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        if kind == "encrypted":
            writer.encrypt("password")
        writer.write(path)
    with pytest.raises(RiskDocumentError):
        risk_context._read_document(tmp_path, path.name, "stormar")


def test_all_catalogue_pdfs_have_swedish_text():
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    documents = load_risk_documents(catalogue["risks"])
    guide = risk_context._read_document(CATALOGUE_PATH.parent, catalogue["user_guide"]["file"], None)
    assert len(documents) == 24
    for document in (*documents, guide):
        assert document.pages
        assert len(document.text) > 100
        assert any(character in document.text for character in "åäöÅÄÖ")
        assert all(page.number == index for index, page in enumerate(document.pages, start=1))
