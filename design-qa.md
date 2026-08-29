# Design QA — preference journal

**Source visual truth**

- Existing journal implementation captured from `http://localhost:3000/journal-demo`: `/Users/vitaliibulyzhyn/Desktop/barca-cala-hack/qa-journal-source.png`
- User-supplied problem-state reference: `/var/folders/hj/t3jj90fx10z1gxtsv92q8qx00000gn/T/TemporaryItems/NSIRD_screencaptureui_61p3b9/Screenshot 2026-08-29 at 17.10.28.png`

**Implementation evidence**

- Preference journal captured from `http://localhost:3000/preferences?id=e67d0ccd-416f-423d-9bfb-1bf37034e494`: `/Users/vitaliibulyzhyn/Desktop/barca-cala-hack/qa-preference-book.png`
- Full comparison: `/Users/vitaliibulyzhyn/Desktop/barca-cala-hack/qa-journal-comparison.png`
- Focused page-content comparison: `/Users/vitaliibulyzhyn/Desktop/barca-cala-hack/qa-journal-focus-comparison.png`

**Normalization**

- Viewport: 1280 × 720 CSS px for source and implementation.
- Captures: 1280 × 720 px at 1× density; no resampling was required.
- State: open spread showing pages 2–3 of 6, default light theme, local development data.
- Both books measured exactly 970 × 679 CSS px at x=155 and y=20.5. Both documents measured 1280 × 720 with no horizontal or vertical overflow.

**Full-view comparison evidence**

- The preference flow now uses the same fullscreen Mantine Book surface, paper imagery, center gutter, open-spread geometry, top status, navigation placement, page-turn animation, and page numbering as the journal source.
- The activity imagery and rating controls are intentional additions required for preference learning; they fit inside the existing journal pages instead of creating a separate card layout.
- Desktop composition, book scale, outer whitespace, corner treatment, shadow, and control hierarchy match the source journal.

**Focused region comparison evidence**

- The focused comparison makes typography, image crops, page texture, page numbers, and thumb controls readable at the same scale.
- Handwritten headings retain the journal display face. Category labels and body copy use the established compact supporting typography.
- All visible activity images loaded at 1200 px natural width, use consistent framed crops, and have descriptive alt text.
- Thumb controls use one matching outlined icon family, keep visible pressed semantics, and do not interfere with page turning.

**Required fidelity surfaces**

- Fonts and typography: display headings, compact metadata, body hierarchy, wrapping, and line height are consistent with the source journal; no clipped text was observed at desktop size.
- Spacing and layout rhythm: exact book geometry is shared with the source. Photo, copy, controls, and page numbers maintain clear vertical rhythm on both faces.
- Colors and visual tokens: cream paper, dark ink, terracotta accents, muted supporting text, borders, focus treatment, and shadows follow the existing journal palette.
- Image quality and asset fidelity: backend-provided travel photos are sharp, consistently cropped, and framed as journal photographs. No placeholder, generated, CSS-drawn, or substitute imagery is used.
- Copy and content: activity category, title, description, and page numbering are coherent, destination-specific, and derived from the persisted preference entries.

**Interaction and responsive evidence**

- Previous/Next, keyboard ArrowLeft/ArrowRight, and the Mantine page-turn interaction work without a vote.
- Like/dislike persists independently and does not advance the book.
- The last face exposes an enabled `Create journal` action with zero, partial, or complete votes.
- A zero-response run completed and navigated to the generated journal; unanswered activities remained neutral.
- At 390 × 844 CSS px, the page measured exactly 390 × 844 with no overflow and all persistent controls remained visible.
- A fresh browser load reported no console errors. The only warning was Mantine Book's snapshot helper noting potential font-fallback rewrapping while preparing the rounded page curl.

**Findings**

- No actionable P0, P1, or P2 mismatches remain.
- P3: the Next.js development-tools badge appears in local development screenshots; it is development chrome and is absent from production builds.

**Comparison history**

- Earlier P1: the user-supplied problem-state rendered a large static two-column composition instead of the same interactive journal used later in the flow. Page movement and content hierarchy did not match the product's journal behavior.
- Fix: replaced the static preference layout with the shared Mantine Book sizing, page faces, controls, keyboard/page-turn behavior, and paper assets; moved voting controls onto each face and removed vote gating from navigation and completion.
- Post-fix evidence: the full and focused comparison captures show identical book bounds and shared presentation behavior. Desktop and phone-sized browser checks found no clipping or overflow, and zero-response completion succeeded end to end.

**Implementation checklist**

- [x] Same page-turning journal component and six-face model.
- [x] Page navigation is independent of rating.
- [x] Zero/partial/full response completion.
- [x] Existing backend activity images only; no image generation.
- [x] Keyboard, responsive fit, semantic controls, alt text, and browser-error checks.

final result: passed
