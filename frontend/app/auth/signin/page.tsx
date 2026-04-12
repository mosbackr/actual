"use client";

import { Suspense } from "react";
import { getProviders, signIn } from "next-auth/react";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

const PROVIDER_NAMES: Record<string, string> = {
  google: "Google",
  linkedin: "LinkedIn",
  github: "GitHub",
};

function SignInContent() {
  const [providers, setProviders] = useState<Record<string, { id: string; name: string }>>({});
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") || "/";
  const error = searchParams.get("error");

  useEffect(() => {
    getProviders().then((p) => {
      if (p) setProviders(p);
    });
  }, []);

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="w-full max-w-sm">
        <div className="text-center mb-10">
          <h1 className="font-serif text-3xl text-text-primary">Deep Thesis</h1>
          <p className="text-text-secondary mt-2 text-sm">
            Startup investment intelligence
          </p>
        </div>

        {error && (
          <p className="text-score-low text-sm text-center mb-6">
            {error === "OAuthSignin" ? "Could not start sign in. Try again." :
             error === "OAuthCallback" ? "Sign in was not completed." :
             "An error occurred during sign in."}
          </p>
        )}

        <div className="space-y-3">
          {Object.values(providers).map((provider) => (
            <button
              key={provider.id}
              onClick={() => signIn(provider.id, { callbackUrl })}
              className="w-full flex items-center justify-center gap-3 rounded border border-border bg-surface px-4 py-3 text-sm text-text-primary hover:border-text-tertiary hover:bg-hover-row transition"
            >
              Continue with {PROVIDER_NAMES[provider.id] || provider.name}
            </button>
          ))}
        </div>

        {Object.keys(providers).length === 0 && (
          <p className="text-text-tertiary text-sm text-center">
            No sign-in providers configured.
          </p>
        )}
      </div>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense>
      <SignInContent />
    </Suspense>
  );
}
