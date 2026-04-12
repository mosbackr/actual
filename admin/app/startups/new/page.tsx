"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { adminApi } from "@/lib/api";

const STAGES = [
  { value: "pre_seed", label: "Pre-Seed" },
  { value: "seed", label: "Seed" },
  { value: "series_a", label: "Series A" },
  { value: "series_b", label: "Series B" },
  { value: "series_c", label: "Series C" },
  { value: "growth", label: "Growth" },
];

const inputClasses =
  "w-full bg-surface border border-border rounded px-3 py-2 text-text-primary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

export default function NewStartupPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [industries, setIndustries] = useState<{ id: string; name: string; slug: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const [fetchingLogo, setFetchingLogo] = useState(false);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    name: "",
    description: "",
    website_url: "",
    stage: "seed",
    status: "approved",
    location_city: "",
    location_state: "",
    location_country: "US",
    industry_ids: [] as string[],
  });

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getIndustries(session.backendToken).then(setIndustries);
    }
  }, [session?.backendToken]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  function update(field: string, value: string | string[]) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function toggleIndustry(id: string) {
    setForm((prev) => ({
      ...prev,
      industry_ids: prev.industry_ids.includes(id)
        ? prev.industry_ids.filter((i) => i !== id)
        : [...prev.industry_ids, id],
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim() || !form.description.trim()) {
      setError("Name and description are required.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const result = await adminApi.createStartup(session!.backendToken!, {
        name: form.name,
        description: form.description,
        website_url: form.website_url || undefined,
        stage: form.stage,
        status: form.status,
        location_city: form.location_city || undefined,
        location_state: form.location_state || undefined,
        location_country: form.location_country,
        industry_ids: form.industry_ids,
      });

      // Try to fetch logo if there's a website URL
      if (form.website_url) {
        try {
          await adminApi.fetchLogo(session!.backendToken!, result.id);
        } catch {
          // Logo fetch is best-effort, don't block creation
        }
      }

      router.push(`/startups/${result.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create startup");
    } finally {
      setSaving(false);
    }
  }

  async function previewLogo() {
    if (!form.website_url) return;
    setFetchingLogo(true);
    try {
      const domain = new URL(
        form.website_url.includes("://") ? form.website_url : `https://${form.website_url}`
      ).hostname.replace(/^www\./, "");
      // Use Logo.dev public preview (no token needed for preview)
      setLogoPreview(`https://img.logo.dev/${domain}?token=pk_a8z3MkxTRBagOcgMIb4sGA&format=png&size=128`);
    } catch {
      setLogoPreview(null);
    } finally {
      setFetchingLogo(false);
    }
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <div className="max-w-2xl">
          <h2 className="font-serif text-xl text-text-primary mb-6">New Startup</h2>

          {error && (
            <div className="mb-4 p-3 bg-score-low/10 border border-score-low/20 rounded text-score-low text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm text-text-secondary mb-1">Name *</label>
              <input
                value={form.name}
                onChange={(e) => update("name", e.target.value)}
                placeholder="e.g. OpenAI"
                className={inputClasses}
              />
            </div>

            <div>
              <label className="block text-sm text-text-secondary mb-1">Description *</label>
              <textarea
                value={form.description}
                onChange={(e) => update("description", e.target.value)}
                rows={4}
                placeholder="What does the company do?"
                className={inputClasses}
              />
            </div>

            <div>
              <label className="block text-sm text-text-secondary mb-1">Website URL</label>
              <div className="flex gap-2">
                <input
                  value={form.website_url}
                  onChange={(e) => {
                    update("website_url", e.target.value);
                    setLogoPreview(null);
                  }}
                  placeholder="e.g. https://openai.com"
                  className={inputClasses}
                />
                <button
                  type="button"
                  onClick={previewLogo}
                  disabled={!form.website_url || fetchingLogo}
                  className="shrink-0 px-3 py-2 border border-border rounded text-sm text-text-secondary hover:text-text-primary hover:border-accent disabled:opacity-40 transition"
                >
                  {fetchingLogo ? "..." : "Preview Logo"}
                </button>
              </div>
              {logoPreview && (
                <div className="mt-2 flex items-center gap-3">
                  <img
                    src={logoPreview}
                    alt="Logo preview"
                    className="w-10 h-10 rounded border border-border object-contain bg-white"
                    onError={() => setLogoPreview(null)}
                  />
                  <span className="text-xs text-text-tertiary">Logo will be fetched on save</span>
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-text-secondary mb-1">Stage</label>
                <select
                  value={form.stage}
                  onChange={(e) => update("stage", e.target.value)}
                  className={inputClasses}
                >
                  {STAGES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-text-secondary mb-1">Status</label>
                <select
                  value={form.status}
                  onChange={(e) => update("status", e.target.value)}
                  className={inputClasses}
                >
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="featured">Featured</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-text-secondary mb-1">City</label>
                <input
                  value={form.location_city}
                  onChange={(e) => update("location_city", e.target.value)}
                  placeholder="San Francisco"
                  className={inputClasses}
                />
              </div>
              <div>
                <label className="block text-sm text-text-secondary mb-1">State</label>
                <input
                  value={form.location_state}
                  onChange={(e) => update("location_state", e.target.value)}
                  placeholder="CA"
                  className={inputClasses}
                />
              </div>
              <div>
                <label className="block text-sm text-text-secondary mb-1">Country</label>
                <input
                  value={form.location_country}
                  onChange={(e) => update("location_country", e.target.value)}
                  className={inputClasses}
                />
              </div>
            </div>

            {industries.length > 0 && (
              <div>
                <label className="block text-sm text-text-secondary mb-2">Industries</label>
                <div className="flex flex-wrap gap-2">
                  {industries.map((ind) => {
                    const selected = form.industry_ids.includes(ind.id);
                    return (
                      <button
                        key={ind.id}
                        type="button"
                        onClick={() => toggleIndustry(ind.id)}
                        className={`px-3 py-1 rounded-full text-sm border transition ${
                          selected
                            ? "bg-accent text-white border-accent"
                            : "bg-surface text-text-secondary border-border hover:border-accent hover:text-accent"
                        }`}
                      >
                        {ind.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button
                type="submit"
                disabled={saving}
                className="px-5 py-2 bg-accent text-white rounded hover:bg-accent-hover disabled:opacity-50 transition"
              >
                {saving ? "Creating..." : "Create Startup"}
              </button>
              <button
                type="button"
                onClick={() => router.push("/startups")}
                className="px-5 py-2 border border-border text-text-secondary rounded hover:text-text-primary transition"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}
