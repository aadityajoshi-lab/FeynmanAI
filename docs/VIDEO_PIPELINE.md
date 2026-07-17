# Deferred video and media pipeline

Video is deliberately outside the MVP runtime. The future pipeline must not
allow an unreviewed transcript or model-generated quote to become evidence.

```text
licensed URL or file
  → MIME, size, license, and SHA-256 validation
  → audio extraction
  → timestamped transcription
  → deterministic transcript segmentation
  → instructor approves six-to-eight evidence spans
  → immutable SourcePack version
  → published lesson asset
```

Media states:

```text
pending_upload → validating → rejected | extracting → transcribing
→ segmented → awaiting_approval → approved → published
```

Required metadata includes license/authorization, original URL or file name,
MIME type, byte size, checksum, transcript engine/version, transcript
checksum, segment timestamps, approver, approval timestamp, and source-pack
version. A future timestamp UI may link to a segment, but the model must return
approved span IDs only.

Do not add uploads, arbitrary URL ingestion, ASR, vision analysis, embeddings,
RAG, or background workers until the source-bounded Evidence Record loop has
passed its submission gates.
