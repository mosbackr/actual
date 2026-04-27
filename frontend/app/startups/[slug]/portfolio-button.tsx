"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";
import { AddCompanyModal } from "@/app/score/[id]/add-company-modal";

export function PortfolioButton({
  startupId,
  startupName,
}: {
  startupId: string;
  startupName: string;
}) {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const role = (session as any)?.role;
  const [investorId, setInvestorId] = useState<string | null>(null);
  const [inPortfolio, setInPortfolio] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!token || role !== "investor") return;

    // Get investor profile for this user
    fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/investors/me/ranking`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Not an investor");
        return res.json();
      })
      .then((data) => {
        setInvestorId(data.investor_id);
        // Check if startup is already in portfolio
        return api.getPortfolio(token, data.investor_id);
      })
      .then((portfolio) => {
        const found = portfolio.items.some(
          (item) => item.startup_id === startupId
        );
        setInPortfolio(found);
        setReady(true);
      })
      .catch(() => setReady(true));
  }, [token, role, startupId]);

  if (!token || role !== "investor" || !ready || !investorId) return null;

  if (inPortfolio) {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded border border-score-high/30 text-xs font-medium text-score-high bg-score-high/5">
        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6L9 17l-5-5" />
        </svg>
        In Portfolio
      </span>
    );
  }

  return (
    <>
      <button
        onClick={() => setShowModal(true)}
        className="inline-flex items-center gap-1.5 px-3 py-1 rounded border border-border text-xs font-medium text-text-secondary hover:border-accent/50 hover:text-accent transition"
      >
        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
        Add to Portfolio
      </button>
      <AddCompanyModal
        open={showModal}
        onClose={() => setShowModal(false)}
        token={token}
        investorId={investorId}
        onAdded={() => setInPortfolio(true)}
        prefill={{ startup_id: startupId, company_name: startupName }}
      />
    </>
  );
}
