import { timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { generateRemediationLesson, normalizeRemediationVideoRequest } from "@/lib/remediationVideo";

export const maxDuration = 900;

function authorized(request: NextRequest): boolean {
  const expected = process.env.FEYNMAN_VIDEO_INTERNAL_KEY?.trim() || "feynman-local-video";
  const received = request.headers.get("x-feynman-video-key")?.trim() || "";
  const expectedBytes = Buffer.from(expected);
  const receivedBytes = Buffer.from(received);
  return expectedBytes.length === receivedBytes.length && timingSafeEqual(expectedBytes, receivedBytes);
}

export async function POST(request: NextRequest) {
  if (!authorized(request)) return NextResponse.json({ success: false, error: "Video integration authentication failed" }, { status: 401 });
  try {
    const parsed = normalizeRemediationVideoRequest(await request.json());
    if (!parsed.request) return NextResponse.json({ success: false, error: parsed.error || "Invalid request" }, { status: 400 });
    const remediationVideo = await generateRemediationLesson(parsed.request);
    return NextResponse.json({ success: true, remediationVideo });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json({ success: false, error: message }, { status: 502 });
  }
}
