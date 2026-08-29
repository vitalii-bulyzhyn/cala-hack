# Product experience

Status: City/tag input, visual preference learning, generation polling, safe failure, and the image-plus-linked-places result are **Current**. Further brand refinement and automated browser coverage remain **Open**.

## Experience model

The primary task is: choose a city and tags, react to visual activity options in a journal-like sequence, wait through generation, then explore one journal image and its real places.

## Current user flow

### 1. City and tags

- Use a clearly labeled city field and grouped tag-selection controls with one primary action.
- Require the tag array in transport while allowing it to be empty; backend validation retains the 20-tag and 50-character-per-tag limits.
- Preserve city and tags after client/API validation failure and identify the error in place.

### 2. Preference learning

- Use the itinerary ID to call `GET .../preference-pages/next`.
- Render `layout: pair` as two activity cards and `layout: single` as one centered activity card.
- Every card/opening uses the returned image link, name, category, description, and nullable saved decision. Do not infer identity from array position; send the entry UUID with the response.
- Record each choice with `PUT .../preference-items/{item_id}/response` and `decision: like|dislike`.
- Keep the current page until every entry has a response. A repeated GET must be safe after reload.
- The first sequence is three pairs/six responses: choosing one card records it as liked and the alternative as disliked. One adaptive single/pair page follows; a `204` means the algorithm is finished.
- The frontend calls completion after `204`; generation begins from its `202` response.
- Initial suggestions work without provider keys. Adaptive OpenAI reranking falls back deterministically when unavailable.

### 3. Generation

Poll the returned `status_url`. Public `status` remains `pending`; the stable `stage` field supplies one of:

| Stage | User-facing meaning |
| --- | --- |
| `learning_preferences` | Learning what kind of day fits you |
| `queued` | Preparing your journal |
| `researching` | Finding grounded places |
| `planning` | Arranging the day |
| `illustrating` | Drawing the journal |

The frontend shows stage copy without fake percentages or provider names, honors `Retry-After`, and preserves work across reloads through the itinerary ID.

### 4. Done result

Render the result in this reading order:

1. Destination, planned date, title, and summary.
2. The 4:3 journal image with backend-provided alt text and a generated-image label.
3. Ordered places with local time windows, name, category, description, reason, location, and typed links.
4. A clear action to choose another city/tag combination.

The image is the visual artifact, not the sole itinerary representation. Do not scrape or depend on text inside it. On narrow screens, size it responsively and keep the structured place list as a normal single-column reading order.

### 5. Fail result

Retain the original city/tags and show the safe backend message. Use `retryable` to decide whether retry language is appropriate, and retain the request ID for support. In local development, `PROVIDER_CONFIGURATION_MISSING` should direct contributors to `.env` without revealing values.

## Interface states

| API condition | Required behavior |
| --- | --- |
| Before submit | Explain the one-day promise and focus the city field. |
| Client validation error | Identify the problem without clearing city or tags. |
| Preference page | Render one/two entries according to layout and persist each response by item ID. |
| No next page (`204`) | Complete learning and enter generation polling. |
| `pending` | Announce the current stage and continue polling. `result` and `error` are null. |
| `done` | Stop polling; render the complete image and places. `stage` and `error` are null. |
| `fail` | Stop polling; render safe failure/retry guidance. `stage` and `result` are null. |
| Transport interruption | Preserve resource ID, retry GET with backoff, and do not silently submit another job. |

There is no public partial state. If any required result field or the hero image is missing, the resource is `fail`.

## Visual direction

- Let the generated 4:3 journal image carry watercolor, ink, tactile paper, taped sketches, and playful route marks.
- Keep surrounding controls and place details restrained, readable, and visually compatible with the artifact.
- Use short place labels in the generated image; schedules, descriptions, and links belong in HTML.
- Reserve the image aspect ratio to avoid layout shift.
- Label official/source links distinctly from the app-created map-search link.

## Accessibility baseline

- Use real labels, instructions, and error associations for the city and tag controls.
- Give each preference entry an accessible name/description and explicit like/dislike controls; external activity images need appropriate alt treatment.
- Announce stage changes with a polite live region; do not announce every poll.
- Use semantic headings and an ordered list for places.
- Render typed links as keyboard-operable anchors with descriptive labels.
- Use the returned hero `alt_text`; do not duplicate all place text in the alt attribute.
- Maintain contrast independently of textures and imagery, expose focus, and respect reduced motion.
- Do not communicate status or link kind by color alone.

## Trust and content rules

- Label the journal image as generated and illustrative, not an exact depiction.
- Explain that map links are search links, while `official`/`source` URLs are verified against Cala research.
- Do not present hours, prices, availability, route time, or accessibility as live facts.
- Display `planned_date` and the destination timezone context clearly enough to avoid date ambiguity.
- Keep provider names out of primary consumer copy unless transparency requires them.
- Encourage users to verify time-sensitive details before travel.

Product boundaries are in [Scope](scope.md); transport behavior is in the [API contract](../architecture/api-contract.md).
