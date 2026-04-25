"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { InvestorFAQ } from "@/lib/types";
import InvestorFaqView from "@/components/InvestorFaqView";

export default function PitchFaqPage() {
  return (
    <Suspense fallback={<div className="p-8 text-text-secondary">Loading...</div>}>
      <PitchFaqContent />
    </Suspense>
  );
}

function PitchFaqContent() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const params = useParams();
  const sessionId = params.id as string;

  const [faq, setFaq] = useState<InvestorFAQ | null>(null);
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);

  const loadFaq = useCallback(async () => {
    if (!token || !sessionId) return;
    try {
      const data = await api.getPitchFaq(token, sessionId);
      setFaq(data);
    } catch {
      setFaq(null);
    }
    setLoading(false);
  }, [token, sessionId]);

  useEffect(() => {
    loadFaq();
  }, [loadFaq]);

  useEffect(() => {
    if (!token || !sessionId) return;
    api.getPitchSession(token, sessionId).then((s) => setTitle(s.title || "Untitled Pitch")).catch(() => {});
  }, [token, sessionId]);

  async function handleRegenerate() {
    if (!token || !sessionId) return;
    setRegenerating(true);
    try {
      const data = await api.generatePitchFaq(token, sessionId);
      setFaq(data);
    } catch {
      // ignore
    }
    setRegenerating(false);
  }

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  if (!faq) {
    return (
      <div className="max-w-3xl mx-auto text-center py-20">
        <p className="text-text-tertiary mb-4">No FAQ generated yet.</p>
        <Link href={`/pitch-intelligence/${sessionId}`} className="text-accent hover:text-accent-hover text-sm">
          Back to Session
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <Link href={`/pitch-intelligence/${sessionId}`} className="text-xs text-text-tertiary hover:text-text-secondary">
          &larr; Back to Session
        </Link>
        <h1 className="font-serif text-2xl text-text-primary mt-2">
          Investor FAQ &mdash; {title}
        </h1>
      </div>

      <InvestorFaqView faq={faq} onRegenerate={handleRegenerate} regenerating={regenerating} />
    </div>
  );
}
