# Authoring-time source and media pipeline

The learner runtime does not ingest arbitrary files. Instructors or content stewards publish immutable, reviewed source packs.

```text
licensed PDF/image/video
→ MIME, size, license, and checksum validation
→ PDF text/page rendering, OCR/vision, or audio transcription
→ page/region/timestamp locators
→ atomic source-span candidates
→ instructor approval
→ concept and checkpoint mapping
→ whiteboard/media manifest
→ immutable SourcePack version
```

PDFs use `pypdf` or `pdfplumber` for extraction and page rendering for figures. Images keep the original asset, OCR candidates, region anchors, and accessible descriptions. Videos use a future worker or authoring script to extract audio, create a timestamped transcript, and sample keyframes. The published runtime consumes approved text, equations, captions, images, and timestamps rather than raw video interpretation.

For the first DSAP module, the source pack is small enough for direct server context. Do not introduce embeddings, LangChain, or a vector database until a pack has a demonstrated retrieval need. If retrieval is later required, implement a `Retriever` interface and evaluate OpenAI hosted File Search before selecting a third-party orchestration framework.
