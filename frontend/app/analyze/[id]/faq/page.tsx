"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { InvestorFAQ } from "@/lib/types";
import InvestorFaqView from "@/components/InvestorFaqView";

export default function AnalysisFaqPage() {
  return (
    <Suspense fallback={<div className="p-8 text-text-secondary">Loading...</div>}>
      <AnalysisFaqContent />
    </Suspense>
  );
}

function AnalysisFaqContent() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const params = useParams();
  const id = params.id as string;

  const [faq, setFaq] = useState<InvestorFAQ | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);

  const loadFaq = useCallback(async () => {
    if (!token || !id) return;
    try {
      const data = await api.getAnalysisFaq(token, id);
      setFaq(data);
    } catch {
      setFaq(null);
    }
    setLoading(false);
  }, [token, id]);

  useEffect(() => {
    loadFaq();
  }, [loadFaq]);

  useEffect(() => {
    if (!token || !id) return;
    api.getAnalysis(token, id).then((a) => setCompanyName(a.company_name)).catch(() => {});
  }, [token, id]);

  async function handleRegenerate() {
    if (!token || !id) return;
    setRegenerating(true);
    try {
      const data = await api.generateAnalysisFaq(token, id);
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
        <Link href={`/analyze/${id}`} className="text-accent hover:text-accent-hover text-sm">
          Back to Analysis
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <Link href={`/analyze/${id}`} className="text-xs text-text-tertiary hover:text-text-secondary">
          &larr; Back to Analysis
        </Link>
        <h1 className="font-serif text-2xl text-text-primary mt-2">
          Investor FAQ &mdash; {companyName || "Analysis"}
        </h1>
      </div>

      <InvestorFaqView faq={faq} onRegenerate={handleRegenerate} regenerating={regenerating} />
    </div>
  );
}
