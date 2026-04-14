"use client";

import { useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { BillingStatus } from "@/lib/types";
import { TIERS } from "@/lib/pricing";
import { AlertModal } from "@/components/Modal";

export default function BillingPage() {
  return (
    <Suspense fallback={<div className="text-center py-20 text-text-tertiary">Loading...</div>}>
      <BillingContent />
    </Suspense>
  );
}

function BillingContent() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const searchParams = useSearchParams();

  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [showSuccess, setShowSuccess] = useState(false);
  const [selectedTier, setSelectedTier] = useState<string>("professional");
  const [alertModal, setAlertModal] = useState<{ title: string; message: string; variant?: "info" | "success" | "error" } | null>(null);

  const loadBilling = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.getBillingStatus(token);
      setBilling(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadBilling();
  }, [loadBilling]);

  // Handle success redirect from Stripe
  useEffect(() => {
    if (searchParams.get("success") === "true" && token) {
      setShowSuccess(true);
      let attempts = 0;
      const maxAttempts = 30;
      const interval = setInterval(async () => {
        attempts++;
        try {
          const data = await api.getBillingStatus(token);
          setBilling(data);
          if (data.subscription_status === "active" || attempts >= maxAttempts) {
            clearInterval(interval);
          }
        } catch {
          if (attempts >= maxAttempts) clearInterval(interval);
        }
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [searchParams, token]);

  const handleCheckout = async (tier: string) => {
    if (!token) return;
    setCheckoutLoading(tier);
    try {
      const { url } = await api.createCheckoutSession(token, tier);
      window.location.href = url;
    } catch (err: any) {
      setAlertModal({ title: "Checkout Error", message: err.message || "Failed to start checkout.", variant: "error" });
      setCheckoutLoading(null);
    }
  };

  const handlePortal = async () => {
    if (!token) return;
    try {
      const { url } = await api.createPortalSession(token);
      window.location.href = url;
    } catch (err: any) {
      setAlertModal({ title: "Error", message: err.message || "Failed to open billing portal.", variant: "error" });
    }
  };

  if (!session) {
    return (
      <div className="text-center py-20">
        <p className="text-text-secondary">Please sign in to manage billing.</p>
      </div>
    );
  }

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  const status = billing?.subscription_status || "none";
  const tier = billing?.subscription_tier;
  const periodEnd = billing?.subscription_period_end
    ? new Date(billing.subscription_period_end).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;

  // Success state after Stripe redirect
  if (showSuccess && status === "active") {
    const tierName = TIERS.find((t) => t.key === tier)?.name || tier;
    return (
      <div className="max-w-lg mx-auto py-20 text-center">
        <div className="w-16 h-16 rounded-full bg-score-high/10 flex items-center justify-center mx-auto mb-6">
          <svg className="w-8 h-8 text-score-high" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6L9 17l-5-5" />
          </svg>
        </div>
        <h1 className="font-serif text-3xl text-text-primary mb-3">Welcome to {tierName}!</h1>
        <p className="text-text-secondary mb-8">Your subscription is active. You now have full access.</p>
        <div className="flex items-center justify-center gap-4">
          <Link href="/analyze" className="px-6 py-2.5 text-sm rounded bg-accent text-white hover:bg-accent-hover transition">
            Analyze a Startup
          </Link>
          <Link href="/insights" className="px-6 py-2.5 text-sm rounded border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary transition">
            Open Analyst
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto py-10">
      <h1 className="font-serif text-3xl text-text-primary mb-8">Billing</h1>

      {/* Current plan status */}
      <div className="rounded border border-border bg-surface p-6 mb-8">
        {status === "active" && (
          <>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-text-tertiary">Current Plan</p>
                <p className="text-xl font-serif text-text-primary mt-1 capitalize">{tier}</p>
                {periodEnd && (
                  <p className="text-sm text-text-secondary mt-1">Renews on {periodEnd}</p>
                )}
              </div>
              <button
                onClick={handlePortal}
                className="px-4 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition"
              >
                Manage Subscription
              </button>
            </div>
          </>
        )}

        {status === "cancelled" && (
          <>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-full bg-score-mid" />
              <p className="text-sm font-medium text-score-mid">Cancelled</p>
            </div>
            <p className="text-text-primary capitalize">Your {tier} plan is cancelled</p>
            {periodEnd && (
              <p className="text-sm text-text-secondary mt-1">Access continues until {periodEnd}</p>
            )}
            <button
              onClick={handlePortal}
              className="mt-4 px-4 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition"
            >
              Resubscribe
            </button>
          </>
        )}

        {status === "past_due" && (
          <>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-full bg-score-low" />
              <p className="text-sm font-medium text-score-low">Payment Failed</p>
            </div>
            <p className="text-text-secondary">Your last payment failed. Please update your payment method to continue your subscription.</p>
            <button
              onClick={handlePortal}
              className="mt-4 px-4 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition"
            >
              Update Payment Method
            </button>
          </>
        )}

        {status === "none" && (
          <>
            <p className="text-text-primary font-medium">Free Plan</p>
            <p className="text-sm text-text-secondary mt-1">
              1 free startup analysis, 1 free analyst conversation, 20 messages per conversation.
            </p>
          </>
        )}
      </div>

      {/* Tier cards */}
      <h2 className="font-serif text-xl text-text-primary mb-4">
        {status === "active" ? "Your plan" : "Choose a plan"}
      </h2>
      <div className="grid md:grid-cols-3 gap-6">
        {TIERS.map((t) => {
          const isCurrent = status === "active" && tier === t.key;
          const isSelected = status === "none" && selectedTier === t.key;
          return (
            <div
              key={t.key}
              onClick={() => status === "none" && setSelectedTier(t.key)}
              className={`rounded p-6 flex flex-col transition-all ${status === "none" ? "cursor-pointer" : ""} ${
                isCurrent
                  ? "border-2 border-accent bg-background ring-1 ring-accent/10"
                  : isSelected
                  ? "border-2 border-accent bg-background ring-1 ring-accent/10"
                  : "border border-border bg-background"
              }`}
            >
              {isCurrent && (
                <span className="text-xs font-medium text-accent mb-3">Current Plan</span>
              )}
              {isSelected && t.highlighted && (
                <span className="text-xs font-medium text-accent mb-3">Recommended</span>
              )}
              <h3 className="text-sm font-medium text-text-primary">{t.name}</h3>
              <div className="mt-3 mb-5">
                <span className="text-3xl font-serif text-text-primary tabular-nums">{t.price}</span>
                <span className="text-sm text-text-tertiary">{t.period}</span>
              </div>
              <ul className="space-y-2.5 mb-6 flex-1">
                {t.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-sm text-text-secondary">
                    <svg className="w-4 h-4 text-score-high shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 6L9 17l-5-5" />
                    </svg>
                    {feature}
                  </li>
                ))}
              </ul>

              {isCurrent ? (
                <button
                  disabled
                  className="block w-full text-center py-2.5 text-sm font-medium rounded border border-accent/30 text-accent/60 cursor-not-allowed"
                >
                  Current Plan
                </button>
              ) : status === "active" ? (
                <button
                  onClick={handlePortal}
                  className="block w-full text-center py-2.5 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
                >
                  Switch Plan
                </button>
              ) : (
                <button
                  onClick={() => handleCheckout(t.key)}
                  disabled={!!checkoutLoading}
                  className={`block w-full text-center py-2.5 text-sm font-medium rounded transition disabled:opacity-50 ${
                    isSelected
                      ? "bg-accent text-white hover:bg-accent-hover"
                      : "border border-border text-text-primary hover:border-text-tertiary"
                  }`}
                >
                  {checkoutLoading === t.key ? "Redirecting..." : "Subscribe"}
                </button>
              )}
            </div>
          );
        })}
      </div>

      <AlertModal
        open={!!alertModal}
        onClose={() => setAlertModal(null)}
        title={alertModal?.title || ""}
        message={alertModal?.message || ""}
        variant={alertModal?.variant}
      />
    </div>
  );
}
