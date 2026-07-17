# Source-pack provenance and license

`contracts/v1/source_pack.json` points to the immutable MVP evidence document
at `docs/source-packs/photosynthesis-v1.md`.

The eight paragraphs are project-authored instructional text created for the
Feynman AI demo. They are released under **CC BY 4.0** by the Feynman AI
project. Attribution: **“Feynman AI project, Photosynthesis source pack v1.”**

The runtime treats this document as an approved source pack, not as a live web
source. Each span has a SHA-256 checksum over its exact UTF-8 text. The source
document checksum is the SHA-256 of the complete UTF-8 Markdown file. The
`packChecksum` is the SHA-256 of the newline-joined canonical rows:

```text
spanId|exact span text|span checksum
```

Rows are ordered by span ID. If a span changes, its checksum, the pack
checksum, and the source-pack version must change together. Old sessions keep
their source-pack version and are never silently re-anchored.

This pack intentionally covers only the lesson claim boundary:

- carbon dioxide and water are matter inputs;
- light provides energy rather than plant atoms;
- minerals are essential but a small fraction of dry mass;
- photosynthesis transforms the matter inputs into sugars.

Questions outside those claims must abstain or require human review.
