"""Request-local reference documents, selected after risk classification."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


CATALOGUE_PATH = Path(__file__).resolve().parent / "resources" / "risk-catalogue.json"


class RiskDocumentError(Exception):
    """The configured risk references could not be loaded completely."""


@dataclass(frozen=True)
class DocumentPage:
    number: int
    text: str


@dataclass(frozen=True)
class RiskDocument:
    risk_id: str | None  # None identifies the optional shared user guide.
    source: str  # Resource-relative path from the manifest.
    pages: tuple[DocumentPage, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)


@dataclass
class AnalysisContext:
    """Owned by one analysis, never stored on the shared inference runtime."""

    risk_documents: tuple[RiskDocument, ...] = ()
    risk_documents_error: str | None = None


def _read_document(root: Path, source: str, risk_id: str | None) -> RiskDocument:
    if not isinstance(source, str) or not source.strip():
        raise RiskDocumentError("Risk document path must be a nonempty string")
    path = (root / source).resolve()
    if not path.is_relative_to(root.resolve()) or path.suffix.lower() != ".pdf":
        raise RiskDocumentError(f"Invalid risk PDF path: {source}")
    try:
        with path.open("rb") as stream:
            reader = PdfReader(stream)
            if reader.is_encrypted:
                raise RiskDocumentError(f"Encrypted risk PDF is not supported: {source}")
            pages = tuple(
                DocumentPage(number, (page.extract_text() or "").strip())
                for number, page in enumerate(reader.pages, start=1)
            )
    except RiskDocumentError:
        raise
    except Exception as exc:
        raise RiskDocumentError(f"Could not extract risk PDF: {source}") from exc
    if not any(page.text for page in pages):
        raise RiskDocumentError(f"Risk PDF has no extractable text (OCR may be needed): {source}")
    return RiskDocument(risk_id, source, pages)


def load_risk_documents(
    risk_ids: Iterable[str], *, manifest_path: Path = CATALOGUE_PATH,
) -> tuple[RiskDocument, ...]:
    """Load selected PDFs once each, then the enabled guide; never translate text.

    Loading is atomic: an error returns no partial context to the caller. Blank
    pages retain their original page numbers; wholly textless PDFs are rejected.
    """
    selected = tuple(dict.fromkeys(risk_ids))
    if not selected:
        return ()
    try:
        catalogue = json.loads(manifest_path.read_text(encoding="utf-8"))
        mapping = catalogue["risks"]
        guide = catalogue["user_guide"]
        enabled = guide["auto_include_when_risks_present"]
        if not isinstance(mapping, dict) or type(enabled) is not bool:
            raise ValueError("Invalid risk mapping or guide setting")
        sources = [(risk_id, mapping[risk_id]) for risk_id in selected]
        if enabled:
            sources.append((None, guide["file"]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RiskDocumentError("Invalid risk catalogue manifest or unmapped risk ID") from exc
    if len({source for _, source in sources if isinstance(source, str)}) != len(sources):
        raise RiskDocumentError("Risk documents and guide must have distinct string paths")
    return tuple(_read_document(manifest_path.parent, source, risk_id) for risk_id, source in sources)
