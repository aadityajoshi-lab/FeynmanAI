import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

// The Django API is the source of truth for token verification in this local
// split deployment. If a deployment also provides Clerk's server key to the
// Next runtime, enable Clerk's request middleware; otherwise keep public page
// rendering functional without duplicating the secret in the frontend env.
export default process.env.CLERK_SECRET_KEY ? clerkMiddleware() : () => NextResponse.next();

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)"],
};
