"use client";

import { useAuth, useClerk } from "@clerk/nextjs";
import { useEffect } from "react";
import { setAuthSignOut, setAuthTokenGetter } from "@/lib/learningOsApi";

export function ClerkAuthBridge() {
  const { getToken, isSignedIn } = useAuth();
  const { signOut } = useClerk();

  useEffect(() => {
    setAuthTokenGetter(() => getToken());
    setAuthSignOut(() => signOut());
    document.documentElement.dataset.feynmanAuth = isSignedIn ? "signed-in" : "signed-out";
    window.dispatchEvent(new CustomEvent("feynman-auth-state", { detail: { isSignedIn: Boolean(isSignedIn) } }));
    return () => {
      setAuthTokenGetter(null);
      setAuthSignOut(null);
    };
  }, [getToken, isSignedIn, signOut]);

  return null;
}
