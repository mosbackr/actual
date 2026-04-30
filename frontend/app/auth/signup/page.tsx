"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { LogoIcon } from "@/components/LogoIcon";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

const ECOSYSTEM_ROLES = [
  "Venture Capitalist / GP",
  "Limited Partner (LP)",
  "Angel Investor",
  "Founder / CEO",
  "Startup Employee",
  "Investment Analyst",
  "Fund of Funds",
  "Corporate Venture",
  "Accelerator / Incubator",
  "Journalist / Media",
  "Advisor / Consultant",
  "Academic / Researcher",
  "General Public",
  "Other",
];

const REGIONS = [
  "San Francisco / Bay Area",
  "New York City",
  "Boston",
  "Los Angeles",
  "Austin",
  "Seattle",
  "Chicago",
  "Miami",
  "Denver / Boulder",
  "Ohio",
  "Washington DC",
  "Other US",
  "United Kingdom",
  "Germany",
  "France",
  "Israel",
  "India",
  "China",
  "Japan",
  "Southeast Asia",
  "Latin America",
  "Canada",
  "Australia / New Zealand",
  "Africa",
  "Other International",
];

export default function SignUpPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [ecosystemRole, setEcosystemRole] = useState("");
  const [region, setRegion] = useState("");
  const [promoCode, setPromoCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    if (!ecosystemRole) {
      setError("Please select your role");
      return;
    }

    if (!region) {
      setError("Please select your region");
      return;
    }

    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/credentials/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
          name,
          ecosystem_role: ecosystemRole,
          region,
          promo_code: promoCode || undefined,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "Registration failed");
        setLoading(false);
        return;
      }

      router.push("/auth/signin?registered=1");
    } catch {
      setError("Something went wrong. Please try again.");
      setLoading(false);
    }
  }

  const inputClasses =
    "w-full rounded border border-border bg-surface px-4 py-2.5 text-sm text-text-primary placeholder-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

  const selectClasses =
    "w-full rounded border border-border bg-surface px-4 py-2.5 text-sm text-text-primary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="w-full max-w-sm">
        <div className="text-center mb-10">
          <div className="flex justify-center mb-4">
            <LogoIcon size={48} />
          </div>
          <h1 className="font-serif text-3xl text-text-primary">Deep Thesis</h1>
          <p className="text-text-secondary mt-2 text-sm">
            Create your account
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
              placeholder="Your name"
              className={inputClasses}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.com"
              className={inputClasses}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">
              Role in Ecosystem
            </label>
            <select
              value={ecosystemRole}
              onChange={(e) => setEcosystemRole(e.target.value)}
              required
              className={selectClasses}
            >
              <option value="">Select your role...</option>
              {ECOSYSTEM_ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">
              Region
            </label>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              required
              className={selectClasses}
            >
              <option value="">Select your region...</option>
              {REGIONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="At least 8 characters"
              className={inputClasses}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">
              Confirm Password
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              placeholder="Confirm your password"
              className={inputClasses}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">
              Promo Code <span className="text-text-tertiary font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={promoCode}
              onChange={(e) => setPromoCode(e.target.value)}
              placeholder="Enter promo code"
              className={inputClasses}
            />
          </div>

          {error && (
            <p className="text-score-low text-sm">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded bg-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50 transition"
          >
            {loading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <p className="text-center text-sm text-text-secondary mt-6">
          Already have an account?{" "}
          <Link href="/auth/signin" className="text-accent hover:text-accent-hover transition">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
