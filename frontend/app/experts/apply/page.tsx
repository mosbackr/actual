"use client";

import { useSession } from "next-auth/react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Industry, ExpertApplication } from "@/lib/types";

interface Skill {
  id: string;
  name: string;
  slug: string;
}

const BENEFITS = [
  {
    title: "Shape Investment Decisions",
    description:
      "Your expert scores and written analysis directly influence how the community evaluates startups. Your reviews sit alongside AI-generated due diligence — the human perspective that machines can't replicate.",
  },
  {
    title: "Build Your Reputation",
    description:
      "Establish yourself as a recognized voice in venture due diligence. Your contributor profile showcases your expertise, industry focus, and track record of insightful reviews.",
  },
  {
    title: "Access Deal Flow",
    description:
      "Get early visibility into startups across sectors before they hit mainstream coverage. Review enriched company profiles with AI analysis, funding histories, and competitive landscapes.",
  },
  {
    title: "Join a Curated Network",
    description:
      "Contributors are vetted professionals — VCs, operators, analysts, and domain experts. You're joining a community that takes startup evaluation seriously.",
  },
];

const HOW_IT_WORKS = [
  { step: "01", title: "Apply", description: "Tell us about your background, industry expertise, and skills." },
  { step: "02", title: "Get Verified", description: "Our team reviews your application and verifies your credentials." },
  { step: "03", title: "Review Startups", description: "Score and analyze startups matched to your expertise." },
];

function HeroSection() {
  return (
    <div className="text-center max-w-3xl mx-auto mb-16">
      <p className="text-xs font-medium uppercase tracking-widest text-accent mb-4">
        Contributors Program
      </p>
      <h1 className="font-serif text-4xl md:text-5xl text-text-primary mb-5 leading-tight">
        Your expertise deserves<br className="hidden md:block" /> a bigger stage
      </h1>
      <p className="text-lg text-text-secondary max-w-2xl mx-auto leading-relaxed">
        Deep Thesis combines AI-powered due diligence with expert human review.
        We're looking for experienced professionals to provide the analysis that
        algorithms alone can't deliver.
      </p>
    </div>
  );
}

function BenefitsSection() {
  return (
    <div className="mb-16">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {BENEFITS.map((b) => (
          <div
            key={b.title}
            className="rounded border border-border bg-surface p-6 hover:border-text-tertiary transition"
          >
            <h3 className="text-base font-medium text-text-primary mb-2">{b.title}</h3>
            <p className="text-sm text-text-secondary leading-relaxed">{b.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function HowItWorksSection() {
  return (
    <div className="mb-16">
      <h2 className="font-serif text-2xl text-text-primary mb-8 text-center">How it works</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {HOW_IT_WORKS.map((s) => (
          <div key={s.step} className="text-center">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-full border border-accent text-accent font-medium text-sm mb-3">
              {s.step}
            </div>
            <h3 className="text-base font-medium text-text-primary mb-1">{s.title}</h3>
            <p className="text-sm text-text-secondary">{s.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ExpertApplyPage() {
  const { data: session } = useSession();
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [existing, setExisting] = useState<ExpertApplication | null>(null);
  const [loading, setLoading] = useState(true);

  const [bio, setBio] = useState("");
  const [yearsExperience, setYearsExperience] = useState(0);
  const [selectedIndustries, setSelectedIndustries] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getIndustries().then(setIndustries).catch(() => {});
    fetch(
      `${process.env.NEXT_PUBLIC_API_URL || ""}/api/skills`
    )
      .then((r) => r.json())
      .then(setSkills)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!session) {
      setLoading(false);
      return;
    }
    const token = (session as any).backendToken;
    if (token) {
      api
        .getMyApplication(token)
        .then(setExisting)
        .catch(() => {})
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [session]);

  // --- Signed out: marketing page with CTA to sign in ---
  if (!session) {
    return (
      <div className="max-w-4xl mx-auto py-16 px-4">
        <HeroSection />
        <BenefitsSection />
        <HowItWorksSection />

        <div className="text-center rounded border border-border bg-surface py-10 px-6">
          <h2 className="font-serif text-2xl text-text-primary mb-3">Ready to contribute?</h2>
          <p className="text-sm text-text-secondary mb-6 max-w-md mx-auto">
            Sign in or create an account to submit your contributor application.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Link
              href="/auth/signin"
              className="rounded bg-accent px-6 py-2.5 text-sm font-medium text-white hover:bg-accent-hover transition"
            >
              Sign In
            </Link>
            <Link
              href="/auth/signup"
              className="rounded border border-border px-6 py-2.5 text-sm font-medium text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
            >
              Create Account
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  // --- Existing application: show status ---
  if (existing) {
    const statusColors: Record<string, string> = {
      pending: "text-score-mid",
      approved: "text-score-high",
      rejected: "text-score-low",
    };
    return (
      <div className="max-w-2xl mx-auto py-10">
        <h1 className="font-serif text-3xl text-text-primary mb-6">Contributor Application</h1>
        <div className="rounded border border-border bg-surface p-6">
          <p className="mb-2 text-text-primary">
            Status:{" "}
            <span
              className={`font-medium ${statusColors[existing.application_status] || ""}`}
            >
              {existing.application_status.charAt(0).toUpperCase() +
                existing.application_status.slice(1)}
            </span>
          </p>
          <p className="text-text-secondary text-sm">Bio: {existing.bio}</p>
          <p className="text-text-secondary text-sm mt-1">
            Experience: {existing.years_experience} years
          </p>
          <p className="text-text-secondary text-sm mt-1">
            Industries: {existing.industries.join(", ")}
          </p>
          <p className="text-text-secondary text-sm mt-1">
            Skills: {existing.skills.join(", ")}
          </p>
        </div>
      </div>
    );
  }

  // --- Signed in, no application: marketing + form ---
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const token = (session as any).backendToken;
      const result = await api.applyAsExpert(token, {
        bio,
        years_experience: yearsExperience,
        industry_ids: selectedIndustries,
        skill_ids: selectedSkills,
      });
      setExisting(result);
    } catch (err: any) {
      setError(err.message || "Could not submit application");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleSelection = (
    id: string,
    current: string[],
    setter: (v: string[]) => void
  ) => {
    setter(
      current.includes(id)
        ? current.filter((x) => x !== id)
        : [...current, id]
    );
  };

  const inputClasses =
    "rounded border border-border bg-surface px-4 py-2.5 text-sm text-text-primary placeholder-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

  return (
    <div className="max-w-4xl mx-auto py-16 px-4">
      <HeroSection />
      <BenefitsSection />
      <HowItWorksSection />

      {/* Application form */}
      <div className="max-w-2xl mx-auto">
        <div className="border-t border-border pt-12 mb-8">
          <h2 className="font-serif text-2xl text-text-primary mb-2 text-center">Apply Now</h2>
          <p className="text-sm text-text-secondary text-center mb-8">
            Tell us about your expertise and we'll review your application.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">
              Professional Bio
            </label>
            <textarea
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              required
              rows={4}
              placeholder="Describe your professional background, investment experience, and areas of expertise..."
              className={`w-full ${inputClasses} py-3`}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">
              Years of Experience
            </label>
            <input
              type="number"
              value={yearsExperience}
              onChange={(e) =>
                setYearsExperience(parseInt(e.target.value) || 0)
              }
              required
              min={1}
              className={`w-32 ${inputClasses}`}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">
              Industry Expertise
            </label>
            <p className="text-xs text-text-tertiary mb-3">Select all industries where you have professional experience.</p>
            <div className="flex flex-wrap gap-2">
              {industries.map((ind) => (
                <button
                  key={ind.id}
                  type="button"
                  onClick={() =>
                    toggleSelection(
                      ind.id,
                      selectedIndustries,
                      setSelectedIndustries
                    )
                  }
                  className={`rounded px-3 py-1.5 text-xs transition ${
                    selectedIndustries.includes(ind.id)
                      ? "bg-accent text-white"
                      : "border border-border text-text-secondary hover:border-text-tertiary hover:text-text-primary"
                  }`}
                >
                  {ind.name}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">Skills</label>
            <p className="text-xs text-text-tertiary mb-3">Select skills relevant to startup evaluation.</p>
            <div className="flex flex-wrap gap-2">
              {skills.map((skill) => (
                <button
                  key={skill.id}
                  type="button"
                  onClick={() =>
                    toggleSelection(
                      skill.id,
                      selectedSkills,
                      setSelectedSkills
                    )
                  }
                  className={`rounded px-3 py-1.5 text-xs transition ${
                    selectedSkills.includes(skill.id)
                      ? "bg-accent text-white"
                      : "border border-border text-text-secondary hover:border-text-tertiary hover:text-text-primary"
                  }`}
                >
                  {skill.name}
                </button>
              ))}
            </div>
          </div>

          {error && <p className="text-score-low text-sm">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded bg-accent px-4 py-3 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50 transition"
          >
            {submitting ? "Submitting..." : "Submit Application"}
          </button>
        </form>
      </div>
    </div>
  );
}
