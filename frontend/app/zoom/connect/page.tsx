"use client";

import { useSession, signIn } from "next-auth/react";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function ZoomConnectPage() {
  return (
    <Suspense fallback={<div className="p-8 text-text-secondary">Loading...</div>}>
      <ZoomConnectContent />
    </Suspense>
  );
}

function ZoomConnectContent() {
  const { data: session, status: authStatus } = useSession();
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = (session as any)?.backendToken;
  const tempCode = searchParams.get("code");

  const [linking, setLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [zoomEmail, setZoomEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!tempCode) {
      setError("Missing authorization code. Please try connecting Zoom again from your profile.");
      return;
    }

    if (authStatus === "loading") return;

    if (!token) {
      // Not logged in — redirect to sign in, then back here
      signIn(undefined, { callbackUrl: `/zoom/connect?code=${tempCode}` });
      return;
    }

    // Auto-link once we have both the token and temp code
    if (token && tempCode && !linking && !success && !error) {
      setLinking(true);
      api
        .linkZoom(token, tempCode)
        .then((result) => {
          setSuccess(true);
          setZoomEmail(result.zoom_email);
        })
        .catch((err) => {
          setError(err.message || "Failed to link Zoom account.");
        })
        .finally(() => setLinking(false));
    }
  }, [token, tempCode, authStatus, linking, success, error]);

  return (
    <div className="mx-auto max-w-md px-6 py-20">
      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <h1 className="text-xl font-serif text-text-primary mb-4">Connect Zoom</h1>

        {linking && (
          <div>
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent mb-4" />
            <p className="text-text-secondary">Linking your Zoom account...</p>
          </div>
        )}

        {success && (
          <div>
            <div className="mx-auto h-12 w-12 rounded-full bg-green-100 flex items-center justify-center mb-4">
              <svg className="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-text-primary font-medium mb-1">Zoom connected successfully!</p>
            {zoomEmail && (
              <p className="text-sm text-text-secondary mb-4">{zoomEmail}</p>
            )}
            <p className="text-sm text-text-tertiary mb-6">
              Your Zoom cloud recordings will now automatically appear in Pitch Intelligence.
            </p>
            <button
              onClick={() => router.push("/profile")}
              className="rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white hover:bg-accent/90 transition"
            >
              Go to Profile
            </button>
          </div>
        )}

        {error && (
          <div>
            <div className="mx-auto h-12 w-12 rounded-full bg-red-100 flex items-center justify-center mb-4">
              <svg className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <p className="text-text-primary font-medium mb-1">Connection failed</p>
            <p className="text-sm text-red-600 mb-4">{error}</p>
            <button
              onClick={() => router.push("/profile")}
              className="rounded-lg border border-border px-5 py-2 text-sm text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
            >
              Back to Profile
            </button>
          </div>
        )}

        {!linking && !success && !error && authStatus === "loading" && (
          <p className="text-text-secondary">Checking authentication...</p>
        )}
      </div>
    </div>
  );
}
