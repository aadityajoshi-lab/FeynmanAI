# Contract steward handoff

The contract steward owns `contracts/v2/`. Frontend, backend, provider, and QA agents consume these artifacts without silently changing IDs, enums, required fields, source boundaries, or record-version behavior. Compatibility routes under `contracts/v1/` remain for the legacy photosynthesis lab and are not the dynamic product boundary.

## Frozen v2 artifacts

- `subject-pack.schema.json` - versioned subjects, modules, concepts, media, checkpoints, and exam bridges.
- `learning-mode.schema.json` - the nine selectable, evidence-backed learning strategies.
- `learner-profile.schema.json` - global preferences, subject evidence, and session-memory boundaries.
- `dsap-sampling-aliasing.json` - the first DSAP module and whiteboard/checkpoint manifest.
- `source-pack.json` - six server-owned DSAP source spans and approval metadata.
- `evaluation-cases.json` - sixteen frozen cases: supported, needs precision, misconception, and ambiguous/human-review paths.

## Acceptance checklist

- [x] Every runtime source ID is drawn from the server-owned source pack.
- [x] The DSAP source pack records license, version, checksum placeholder, locators, and approval state.
- [x] Learning modes are strategy IDs, not learning-style or ability labels.
- [x] Learner memory is separated into global preferences, subject skill evidence, and session state.
- [x] Provider responses expose provider mode, source-pack version, and record version.
- [x] Invalid IDs, stale versions, malformed output, and unapproved evidence fail closed.
- [x] API examples and tests use the frozen IDs.

The DSAP pack remains `instructor_review_required` until a domain reviewer approves the authored spans. That state is intentional: the runtime must abstain rather than promote unreviewed content to evidence.
