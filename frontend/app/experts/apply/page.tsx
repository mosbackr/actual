"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Industry, ExpertApplication } from "@/lib/types";

interface Skill {
  id: string;
  name: string;
  slug: string;
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
      `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/skills`
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
    const token = (session as any).accessToken;
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

  if (!session) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <h1 className="font-serif text-3xl text-text-primary mb-4">Become a Contributor</h1>
        <p className="text-text-secondary">
          Please sign in to apply as a contributor.
        </p>
      </div>
    );
  }

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const token = (session as any).accessToken;
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
    <div className="max-w-2xl mx-auto py-10">
      <h1 className="font-serif text-3xl text-text-primary mb-2">Become a Contributor</h1>
      <p className="text-text-secondary mb-8">
        Apply to become a verified contributor. Your industry experience and
        skills will be verified by our team.
      </p>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-text-primary mb-2">Bio</label>
          <textarea
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            required
            rows={4}
            placeholder="Describe your professional background and expertise..."
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
          <label className="block text-sm font-medium text-text-primary mb-2">Industries</label>
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
                className={`rounded px-3 py-1 text-xs transition ${
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
                className={`rounded px-3 py-1 text-xs transition ${
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
  );
}
