# PocketBase

The Go service serves `pb_public/` and manages the `Analysis` collection through
checked-in Go migrations. From this directory, run `go run . migrate up` to apply
pending migrations, or `go run . serve` to apply them at server startup. Dashboard
schema edits are not automatically exported; change the versioned migrations for
future schema updates. Runtime data in `pb_data/` is ignored by Git.

Verify with `go build .` and `go test ./...`. Tests use a temporary database and
check migration application, UUID uniqueness/format, status validation, retained
partial predictions, timestamps, and locked API access without loading a model.

## Analysis collection

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | PocketBase record ID | Internal identifier; separate from the backend UUID. |
| `analysis_id` | Required unique text | Existing backend UUID v4 (`X-Analysis-ID` / stream `analysis_id`). |
| `status` | Required single select | `Processing`, `Failed`, or `Complete`. |
| `embedding_status` | Required single select | `Processing`, `Failed`, or `Complete`, independently of category status. |
| `original_text` | Required text, up to 2 Mi characters | Immutable snapshot of the trimmed input actually analyzed; preserves internal whitespace. |
| `title` | Text | Generated title, including the fallback; initially empty. |
| `predictions` | JSON, up to 2 MiB | Completed workflow results keyed by workflow ID. Initially `{}` or null. |
| `error` | JSON | Failure details, or null. |
| `created`, `updated` | Automatic dates | Record creation and last update times. |
| `finished_at` | Optional date | UTC time when category analysis becomes `Complete` or `Failed`; empty while processing. |

All five record API rules are locked (superusers only). Backend persistence and
authentication are not connected yet; creating this schema does not make analysis
requests save records. PocketBase validates field types, UUID format/uniqueness,
and allowed status values, but JSON shapes and lifecycle transitions must be
validated by the future backend writer.

The writer should save `original_text` and initialize both status columns to
`Processing` before inference, save the title when ready,
and append results after each workflow completes. Preserve partial predictions
and set `Failed` immediately if any workflow fails. Set `Complete` only after every
registered category workflow succeeds. An empty match list is a successful result,
not a failure. Title fallback and an embedding failure do not fail category
analysis. Set `finished_at` when category analysis enters either terminal state;
later embedding updates must not change that time. Set `embedding_status` to
`Complete` when a valid vector is generated or `Failed` when embedding fails.
This column tracks generation, not delivery to a future vector index. If analysis
failure cancels embedding before producing a vector, the writer should mark the
embedding `Failed` too. Interrupted/crashed runs need recovery so they do not stay `Processing`
indefinitely; `updated` can identify stale records but is not a worker heartbeat.

Example partial predictions (missing keys mean the workflow has not completed):

```json
{
  "risks": [
    {"ID": "översvämningar", "name": "Översvämningar", "evidence": ["exakt citat ur texten"]}
  ],
  "reach": []
}
```

Example failure details:

```json
{"workflow_id": "service", "code": 502, "message": "Modellanalysen misslyckades eller gav ett ogiltigt resultat."}
```

## Additional fields to consider

An event relation could link repeated analyses of the same source event; the
`original_text` snapshot already lets evidence be checked against its source.
An input hash can support deduplication but should not prohibit rerunning an event.
Store model ID/revision and a prompt/category schema version to explain differences
between runs. User ownership and source URL/publication time can be added when
authentication and event ingestion are defined. These fields are not added yet.

PocketBase's JSON field can store vectors, but its built-in field types and record
API do not provide a vector similarity index/search operation. For indexed search,
keep a separate vector index keyed by `analysis_id` (or eventually an event ID).
PocketBase can remain the source of truth. Store embedding model/revision,
dimensions, task, normalization, truncation, and indexing status alongside the
reference once that integration exists. Indexing status would be separate from
`embedding_status` so generation and synchronization failures can be distinguished.
For a small dataset, storing vectors in JSON and computing exact similarity in
the backend is another option; it requires application code and scales linearly.

References: [collections](https://pocketbase.io/docs/collections/) and
[Go migrations](https://pocketbase.io/docs/go-migrations/).

The extension migration does not invent missing input text, embedding outcomes,
or finish times for legacy records. Any records created before these fields existed
must have required fields populated from their actual source before being updated.
