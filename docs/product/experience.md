# Product experience

Status: City/tag input, visual preference learning, generation polling, safe failure, and the image-plus-linked-places result are **Current**. Further brand refinement and automated browser coverage remain **Open**.

## Experience model

The primary task is: choose a city and tags, react to visual activity options in a journal-like sequence, wait through generation, then explore one journal image and its real places.

## Current user flow

### 1. City and tags

- Use a clearly labeled selector for Barcelona, Toulouse, or Valencia and grouped tag-selection controls with one primary action.
- Require the tag array in transport while allowing it to be empty; backend validation retains the 20-tag and 50-character-per-tag limits.
- Preserve city and tags after client/API validation failure and identify the error in place.

### 2. Preference learning

- Use the itinerary ID to call `GET .../preference-pages/next` once to issue the three initial pairs, then `GET .../preference-pages` to load every persisted page.
- Present the six initial activities as six faces in the same flipping journal used for the result. A returned `pair` supplies the left/right faces of one opening; a returned `single` occupies one centered face.
- Every card/opening uses the returned name, category, full journal prose, optional image link, and nullable saved decision. Journal prose must remain fully visible; when space is constrained, shrink the associated image as far as necessary before compromising the writing. Text-only entries render as journal writing on paper; never invent replacement imagery. Do not infer identity from array position.
- Submit the full opening with `PUT .../preference-pages/{page_id}/feedback`. Each issued item maps to `like`, `dislike`, or `null`; omitted/null items are neutral.
- Keep like and dislike controls on every activity face, restore their pressed state from `decision`, and allow page turns whether or not the current face has a response. Repeating a selected control returns that item to neutral.
- After a newly explicit like or dislike is saved, advance to the next journal opening when one remains. Returning a selected item to neutral stays on the current opening.
- The integrated flow shows the three initial pairs as six faces and lets the traveler create the journal from the final face whether they answered all, some, or none. Unanswered activities are neutral.
- Immediately after the six initial items are issued, the integrated UI automatically requests the optional adaptive page. Thompson Sampling uses prior arms when no decisions exist, and already-issued activities are excluded. A `204` means there is no further page. If that automatic request fails, “Refine my preferences” remains available to retry; refinement is never required for completion.
- The frontend calls completion when the traveler finishes the preference book; generation begins from its `202` response using only recorded likes/dislikes.
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

Retain the original city/tags and show the safe backend message. Use `retryable` to decide whether retry language is appropriate, and retain the request ID for support. `PROVIDER_CONFIGURATION_MISSING` is possible only when offline demo mode is disabled.

## Interface states

| API condition | Required behavior |
| --- | --- |
| Before submit | Explain the one-day promise and focus the city field. |
| Client validation error | Identify the problem without clearing city or tags. |
| Preference pages | Render every issued entry as a journal face, permit page turns before voting, and persist the full page state atomically. |
| End of preference book | Allow completion with zero or more responses and enter generation polling. |
| No next page (`204`) | Complete learning if the client used optional adaptive progression. |
| `pending` | Announce the current stage and continue polling. `result` and `error` are null. |
| `done` | Stop polling; render the complete image and places. `stage` and `error` are null. |
| `fail` | Stop polling; render safe failure/retry guidance. `stage` and `result` are null. |
| Transport interruption | Preserve resource ID, retry GET with backoff, and do not silently submit another job. |

There is no public partial state. If any required result field or the hero image is missing, the resource is `fail`.

## Visual direction

- Use the bundled inward-rounded paper image for every left journal page and the outward-rounded supplied paper image for every right journal page, including the active result spread.
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
