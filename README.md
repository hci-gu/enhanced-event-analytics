# enhanced-event-analytics

The frontend transitions from live workflow progress to an evidence-linked summary
after successful analysis. Original event text and expandable workflow results have
linked highlights, with quotes validated as exact input substrings. See the
[frontend guide](frontend/README.md) and [backend stream contract](backend/README.md).
The [PocketBase guide](pocketbase/README.md) documents the Analysis collection;
the backend saves incremental results when its PocketBase token is configured.
Users can register and log in through the Editorial frontend. The backend verifies
their session and saves each new analysis's creator in `created_by`; per-user
search filtering remains future work. See [authentication setup](backend/README.md#login-and-registration).

## Nyheter
- https://www.svt.se/nyheter/lokalt/vast/oversvamning-efter-vattenlacka-i-uddevalla
- https://www.svt.se/nyheter/lokalt/vast/misstankt-farligt-foremal-i-frolunda-boende-inrymda
