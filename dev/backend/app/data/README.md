# City journal inventories

`journal_entries/*.json` is the authoritative preference inventory. The application currently supports exactly Barcelona, Toulouse, and Valencia; there is no generic or cross-city fallback.

Each file must be named after its normalized `city` and contains:

- the city and source model identifier;
- unique entry names within that city;
- nullable Cala `entity_id` and `entity_type` grounding metadata;
- exactly one of `food`, `culture`, `outdoors`, or `neighbourhoods`;
- the traveler-facing `journal_entry` prose.

Keep at least two entries in every category. Missing media is intentional: the journal renders authoritative prose on paper rather than substituting unrelated stock images. Cala metadata stays behind the backend boundary. Run `make check` after editing; inventory naming, schema, uniqueness, supported-city coverage, and category coverage are validated by tests.
