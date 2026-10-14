"""Local, application-owned storage for EmbeddingGemma2 document vectors."""

import logging
import math
import os
import re
from numbers import Real
from pathlib import Path
from threading import Lock
from uuid import UUID

import lancedb
import pyarrow as pa


logger = logging.getLogger("uvicorn.error.vector_storage")
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
TABLE_NAME = "analysis_embeddings"
DIMENSIONS = 768
SCHEMA = pa.schema([
    pa.field("vector", pa.list_(pa.float32(), DIMENSIONS), nullable=False),
    pa.field("created_by", pa.string(), nullable=False),
    pa.field("analysis_id", pa.string(), nullable=False),
])


def storage_path() -> Path:
    value = os.environ.get("LANCEDB_STORAGE_PATH", "").strip() or "./data/vectordb/"
    # Windows drive letters are paths; every other URI scheme is disallowed.
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value) and not re.match(r"^[a-zA-Z]:[\\/]", value):
        raise ValueError("LANCEDB_STORAGE_PATH must be a local filesystem path")
    if value.startswith(("//", "\\\\")):
        raise ValueError("LANCEDB_STORAGE_PATH must not be a network share")
    path = Path(value)
    return (path if path.is_absolute() else REPOSITORY_ROOT / path).resolve()


def validate_owner(created_by: str) -> None:
    if not isinstance(created_by, str) or not re.fullmatch(r"[a-zA-Z0-9]{15}", created_by):
        raise ValueError("created_by must be a verified PocketBase user ID")


def validate_vector(vector: list[float]) -> list[float]:
    if len(vector) != DIMENSIONS:
        raise ValueError("vector must contain 768 finite float32 values")
    if any(isinstance(value, bool) or not isinstance(value, Real)
           or not math.isfinite(value) or abs(value) > 3.4028234663852886e38 for value in vector):
        raise ValueError("vector must contain 768 finite float32 values")
    values = pa.array(vector, type=pa.float32()).to_pylist()
    if not any(values):
        raise ValueError("vector must have nonzero magnitude for cosine search")
    return values


class VectorStorage:
    def __init__(self, path: Path):
        self.lock = Lock()
        self.connection = None
        self.table = None
        try:
            path.mkdir(parents=True, exist_ok=True)
            self.connection = lancedb.connect(str(path))
            self.table = self.connection.create_table(TABLE_NAME, schema=SCHEMA, exist_ok=True)
            if not self.table.schema.equals(SCHEMA):
                raise ValueError("Incompatible analysis_embeddings schema")
        except Exception as exc:
            self.close()
            logger.error("LanceDB initialization failed (error_type=%s)", type(exc).__name__)
            raise RuntimeError("LanceDB initialization failed; check local path, permissions and table schema") from exc
        logger.info("LanceDB initialized (table=%s)", TABLE_NAME)

    def close(self) -> None:
        with self.lock:
            # The synchronous SDK releases its native handles when references are
            # dropped; unlike AsyncConnection/AsyncTable it has no public close().
            self.table = None
            self.connection = None

    def _require_table(self):
        if self.table is None:
            raise RuntimeError("LanceDB storage is closed")
        return self.table

    def upsert(self, vector: list[float], created_by: str, analysis_id: str) -> None:
        validate_owner(created_by)
        parsed = UUID(analysis_id)
        if parsed.version != 4 or str(parsed) != analysis_id:
            raise ValueError("analysis_id must be a canonical UUID v4")
        values = validate_vector(vector)
        with self.lock:
            table = self._require_table()
            # Identifiers are strictly validated before constructing predicates.
            other_owner = table.search().where(
                f"analysis_id = '{analysis_id}' AND created_by != '{created_by}'",
            ).select(["analysis_id"]).limit(1).to_arrow()
            if other_owner.num_rows:
                raise ValueError("Cannot change the owner of an existing analysis embedding")
            data = pa.Table.from_pylist([
                {"vector": values, "created_by": created_by, "analysis_id": analysis_id},
            ], schema=SCHEMA)
            table.merge_insert("analysis_id").when_matched_update_all().when_not_matched_insert_all().execute(data)
        logger.info("LanceDB vector saved (analysis_id=%s)", analysis_id)

    def search_owned(self, vector: list[float], created_by: str, limit: int) -> list[dict]:
        validate_owner(created_by)
        values = validate_vector(vector)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self.lock:
            results = (self._require_table().search(values, vector_column_name="vector")
                       .distance_type("cosine").bypass_vector_index()
                       .where(f"created_by = '{created_by}'", prefilter=True)
                       .select(["analysis_id"]).limit(limit).to_arrow().to_pylist())
        return [{"analysis_id": row["analysis_id"], "distance": row["_distance"]} for row in results]


def create_vector_storage() -> VectorStorage:
    return VectorStorage(storage_path())
