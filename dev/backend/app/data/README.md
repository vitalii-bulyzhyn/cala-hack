# Activity catalog

`activities.json` is the extendable inventory behind preference learning. Adding an activity does not require an API, database, or frontend change.

Each entry requires:

- a unique `name`;
- one of `food`, `drinks_party`, `culture`, or `nature`;
- a `description` containing `{city}`, which is filled from the itinerary;
- a public HTTP(S) `image_link`;
- short lowercase `signals` that can overlap with traveler tags and liked activity language.

Keep at least two entries in every category. The local ranker uses `signals`; when OpenAI is configured, the model may reorder only the remaining known names inside their existing categories. Run `make check` after editing—the catalog contract and category coverage are validated by backend tests.
