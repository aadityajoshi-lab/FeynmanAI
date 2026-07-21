"""Smoke-test the real PDF -> source candidates -> module builder path.

This script intentionally does not contain a model response or an API key. The
backend selects the configured provider and returns a visible provider error
when the credential is missing or rejected.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "inputs" / "Chapter 7- Discrete Fourier transform.pdf",
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1")
    args = parser.parse_args()
    if not args.pdf.exists():
        print(json.dumps({"ok": False, "stage": "input", "error": f"missing PDF: {args.pdf}"}))
        return 2

    with args.pdf.open("rb") as source_file:
        upload = requests.post(
            f"{args.api_base.rstrip('/')}/study-sources/ingest",
            files={"file": (args.pdf.name, source_file, "application/pdf")},
            data={"subjectId": "dsap", "moduleId": "chapter-7"},
            timeout=60,
        )
    try:
        upload_body = upload.json()
    except ValueError:
        report = {"uploadStatus": upload.status_code, "ok": False, "stage": "upload", "error": "backend returned non-JSON upload response"}
        print(json.dumps(report, indent=2))
        return 1
    report = {
        "uploadStatus": upload.status_code,
        "sourceId": upload_body.get("sourceId"),
        "extraction": upload_body.get("extraction"),
    }
    if upload.status_code >= 400:
        report.update({"ok": False, "stage": "upload", "error": upload_body.get("error")})
        print(json.dumps(report, indent=2))
        return 1

    plan = requests.post(
        f"{args.api_base.rstrip('/')}/study-plans",
        json={
            "subjectId": "dsap",
            "subjectTitle": "Digital Signal Analysis and Processing",
            "moduleId": "chapter-7",
            "sourceIds": [upload_body["sourceId"]],
            "chapterSelection": "chapter_1",
            "provider": "openai",
        },
        timeout=180,
    )
    try:
        plan_body = plan.json()
    except ValueError:
        report.update({"planStatus": plan.status_code, "ok": False, "stage": "module", "error": "backend returned non-JSON module response"})
        print(json.dumps(report, indent=2))
        return 1
    allowed_anchors = {
        item.get("candidateId")
        for item in upload_body.get("candidates", [])
        if item.get("candidateId")
    }
    returned_anchors = {
        anchor_id
        for item in [*plan_body.get("outline", []), *plan_body.get("scenes", [])]
        for anchor_id in item.get("sourceAnchorIds", [])
    }
    report.update(
        {
            "planStatus": plan.status_code,
            "providerMode": plan_body.get("providerMode"),
            "state": plan_body.get("state"),
            "outlineCount": len(plan_body.get("outline", [])),
            "sceneCount": len(plan_body.get("scenes", [])),
            "outlineTitles": [item.get("title") for item in plan_body.get("outline", [])],
            "sceneTypes": [item.get("type") for item in plan_body.get("scenes", [])],
            "recordVersion": plan_body.get("recordVersion"),
            "unapprovedAnchorCount": len(returned_anchors - allowed_anchors),
        }
    )
    if plan.status_code >= 400:
        report.update({"ok": False, "stage": "module", "error": plan_body.get("error")})
    else:
        report["ok"] = True
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
