# PocketBase

The Go service serves `pb_public/` and manages the `Analysis` collection through
checked-in Go migrations. From this directory, run `go run . migrate up` to apply
pending migrations, or `go run . serve` to apply them at server startup. Dashboard
schema edits are not automatically exported; change the versioned migrations for
future schema updates. Runtime data in `pb_data/` is ignored by Git.

The user migration reuses PocketBase's default `users` auth collection, preserving
existing accounts and token secrets. It requires unique email, enables password
login with a minimum of eight characters, and sets seven-day auth tokens.
The follow-up authorization migration allows anonymous user creation and
attributed analysis creation/updates. FastAPI handles registration without a
superuser token and writes results using the verified user's refreshed token.
Other user record API operations stay locked. Verification is not required, and auth alert emails are
disabled so this first version needs no mail service. Restart a running PocketBase
after applying migrations to refresh its collection cache.

Verify with `go build .` and `go test ./...`. Tests use a temporary database and
check migration application, UUID uniqueness/format, status validation, retained
partial predictions, timestamps, and user-authorized API access without loading a model.
The API tests exercise actual PocketBase handlers with a temporary database,
covering registration, login, refresh, own-record updates, cross-user denial and
immutable creator/source identifiers without starting a network listener.

PocketBase stays private behind Python. `go run . serve` defaults to
`127.0.0.1:8090`; the service also rejects non-loopback IP listeners and direct
HTTPS mode. A custom port is allowed on a loopback IP (`--http=127.0.0.1:9090`
or `--http=[::1]:8090`). Serve the frontend/Python publicly via the same-origin
reverse proxy, never proxy PocketBase or its API to browsers. The dashboard can
still be opened on the same machine at `http://127.0.0.1:8090/_/`.

Successful Analysis record creates and updates emit `Analysis record saved` at
INFO level through PocketBase's logger, with operation, record ID, backend UUID,
category status, and embedding status. Input text, titles, predictions, and vectors
are not included. Success hooks log committed writes, including writes through
the record API; they do not log collection migrations or failed record writes.

## Analysis collection

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | PocketBase record ID | Internal identifier; separate from the backend UUID. |
| `analysis_id` | Required unique text | Existing backend UUID v4 (`X-Analysis-ID` / stream `analysis_id`). |
| `created_by` | Optional single relation to `users` | Backend-verified creator; empty for legacy records. Indexed with `created`. |
| `status` | Required single select | `Processing`, `Failed`, or `Complete`. |
| `embedding_status` | Required single select | `Processing`, `Failed`, or `Complete`, independently of category status. |
| `original_text` | Required text, up to 2 Mi characters | Immutable snapshot of the trimmed input actually analyzed; preserves internal whitespace. |
| `title` | Text | Generated title, including the fallback; initially empty. |
| `predictions` | JSON, up to 2 MiB | Completed workflow results keyed by workflow ID. Initially `{}` or null. |
| `dates` | Optional JSON, up to 64 KiB | Original publication, primary event interval, rough duration hint, and exact source quotes. Null before extraction or on extraction failure. |
| `dates_error` | Optional JSON, up to 16 KiB | Nonfatal date extraction error containing `code` and `message`; null on success. |
| `error` | JSON | Failure details, or null. |
| `created`, `updated` | Automatic dates | Record creation and last update times. |
| `finished_at` | Optional date | UTC time when category analysis becomes `Complete` or `Failed`; empty while processing. |

The create rule requires an authenticated users identity matching `created_by`.
The update rule requires ownership and disallows changing `created_by`,
`analysis_id`, or `original_text`. Listing, viewing and deletion stay locked.
FastAPI writes through the HTTP record API using the refreshed user session token;
there is no server superuser credential. The default `POCKETBASE_URL` is
`http://127.0.0.1:8090`. See
[backend persistence setup](../backend/README.md#pocketbase-persistence).
PocketBase validates field types, UUID format/uniqueness, and allowed status values;
the backend writer manages lifecycle transitions and accumulated workflow results.

The writer saves `original_text` and initializes both status columns to
`Processing` before inference, save the title when ready,
and append results after each workflow completes. Preserve partial predictions
and set `Failed` immediately if any workflow fails. Set `Complete` only after every
registered category workflow succeeds and the final date extraction attempt finishes.
Date extraction errors are stored separately in `dates_error` and do not fail the
analysis. The additive date migration leaves existing records without dates;
no backfill is required. An empty match list is a successful result,
not a failure. Title fallback and an embedding failure do not fail category
analysis. Set `finished_at` when category analysis enters either terminal state;
later embedding updates must not change that time. Set `embedding_status` to
`Complete` when a valid vector is generated or `Failed` when embedding fails.
This column tracks generation, not delivery to a future vector index. If analysis
failure cancels embedding before producing a vector, the writer should mark the
embedding `Failed` too. Interrupted/crashed runs need recovery so they do not stay `Processing`
indefinitely; `updated` can identify stale records but is not a worker heartbeat.
Authentication is required before inference; PocketBase verification failure
returns 503. After authentication, persistence is best effort and write failures
do not stop inference. Creator IDs come from verified sessions, never client input.
Legacy creator fields remain empty; deleting a user does not cascade-delete analyses.
No user-facing analysis retrieval or search endpoint is added yet. The owner-write
rules protect attribution but do not distinguish Python from a local process
holding the same user token; database network isolation remains essential.
Stream disconnects mark unfinished analysis Failed, but there is no recovery queue
for process crashes or failed final writes.

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
between runs. Source URL/publication time can be added when event ingestion is
defined. These fields are not added yet; creator attribution is implemented.

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
