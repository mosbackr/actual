"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { DataroomListItem } from "@/lib/api";

const STATUS_BADGE: Record<string, { label: string; classes: string }> = {
  pending: { label: "Pending", classes: "bg-yellow-100 text-yellow-800" },
  uploading: { label: "Uploading", classes: "bg-blue-100 text-blue-800" },
  submitted: { label: "Submitted", classes: "bg-purple-100 text-purple-800" },
  analyzing: { label: "Analyzing", classes: "bg-orange-100 text-orange-800" },
  complete: { label: "Complete", classes: "bg-green-100 text-green-800" },
  expired: { label: "Expired", classes: "bg-gray-100 text-gray-600" },
};

export default function DataroomsPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const router = useRouter();

  const [datarooms, setDatarooms] = useState<DataroomListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form fields
  const [founderEmail, setFounderEmail] = useState("");
  const [founderName, setFounderName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [personalMessage, setPersonalMessage] = useState("");
  const [customCriteria, setCustomCriteria] = useState<string[]>([]);

  const loadDatarooms = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.listDatarooms(token);
      setDatarooms(data.items);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadDatarooms();
  }, [loadDatarooms]);

  const resetForm = () => {
    setFounderEmail("");
    setFounderName("");
    setCompanyName("");
    setPersonalMessage("");
    setCustomCriteria([]);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !founderEmail.trim()) return;

    setSubmitting(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("founder_email", founderEmail.trim());
      if (founderName.trim()) formData.append("founder_name", founderName.trim());
      if (companyName.trim()) formData.append("company_name", companyName.trim());
      if (personalMessage.trim()) formData.append("personal_message", personalMessage.trim());

      const validCriteria = customCriteria.filter((c) => c.trim());
      if (validCriteria.length > 0) {
        formData.append(
          "custom_criteria",
          JSON.stringify(validCriteria.map((c) => ({ description: c.trim() })))
        );
      }

      await api.createDataroomRequest(token, formData);
      setShowModal(false);
      resetForm();
      await loadDatarooms();
    } catch (err: any) {
      setError(err.message || "Failed to create request");
    } finally {
      setSubmitting(false);
    }
  };

  const addCriterion = () => {
    setCustomCriteria((prev) => [...prev, ""]);
  };

  const updateCriterion = (index: number, value: string) => {
    setCustomCriteria((prev) => prev.map((c, i) => (i === index ? value : c)));
  };

  const removeCriterion = (index: number) => {
    setCustomCriteria((prev) => prev.filter((_, i) => i !== index));
  };

  if (!session) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-16 text-center">
        <p className="text-text-secondary">Sign in to access Datarooms.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-serif text-text-primary mb-2">Datarooms</h1>
          <p className="text-text-secondary">
            Request and review document packages from founders for due diligence.
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 transition"
        >
          Request Dataroom
        </button>
      </div>

      {/* List */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-lg border border-border bg-surface p-5 animate-pulse">
              <div className="flex items-center justify-between">
                <div className="space-y-2">
                  <div className="h-4 w-48 bg-border rounded" />
                  <div className="h-3 w-32 bg-border rounded" />
                </div>
                <div className="h-6 w-20 bg-border rounded-full" />
              </div>
            </div>
          ))}
        </div>
      ) : datarooms.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface p-12 text-center">
          <p className="text-text-secondary mb-2">No dataroom requests yet.</p>
          <p className="text-text-tertiary text-sm">
            Click "Request Dataroom" to send a document request to a founder.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {datarooms.map((dr) => {
            const badge = STATUS_BADGE[dr.status] || {
              label: dr.status,
              classes: "bg-gray-100 text-gray-600",
            };
            return (
              <button
                key={dr.id}
                onClick={() => router.push(`/datarooms/${dr.id}`)}
                className="w-full text-left rounded-lg border border-border bg-surface p-5 hover:border-accent/50 transition"
              >
                <div className="flex items-center justify-between">
                  <div className="min-w-0">
                    <p className="font-medium text-text-primary truncate">
                      {dr.company_name || dr.founder_email}
                    </p>
                    <p className="text-sm text-text-tertiary mt-0.5">
                      {dr.founder_name
                        ? `${dr.founder_name} (${dr.founder_email})`
                        : dr.founder_email}
                    </p>
                    <div className="flex items-center gap-3 mt-1.5 text-xs text-text-tertiary">
                      <span>
                        {dr.document_count} {dr.document_count === 1 ? "document" : "documents"}
                      </span>
                      <span>
                        {new Date(dr.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.classes}`}
                  >
                    {badge.label}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg mx-4 rounded-xl border border-border bg-surface shadow-xl max-h-[90vh] overflow-y-auto">
            <form onSubmit={handleSubmit}>
              <div className="px-6 pt-6 pb-4 border-b border-border">
                <h2 className="text-lg font-medium text-text-primary">Request Dataroom</h2>
                <p className="text-sm text-text-tertiary mt-1">
                  Send a document request to a founder for due diligence review.
                </p>
              </div>

              <div className="px-6 py-5 space-y-4">
                {/* Founder Email */}
                <div>
                  <label className="block text-sm font-medium text-text-primary mb-1.5">
                    Founder Email <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="email"
                    required
                    value={founderEmail}
                    onChange={(e) => setFounderEmail(e.target.value)}
                    placeholder="founder@company.com"
                    className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none"
                  />
                </div>

                {/* Founder Name */}
                <div>
                  <label className="block text-sm font-medium text-text-primary mb-1.5">
                    Founder Name
                  </label>
                  <input
                    type="text"
                    value={founderName}
                    onChange={(e) => setFounderName(e.target.value)}
                    placeholder="Jane Smith"
                    className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none"
                  />
                </div>

                {/* Company Name */}
                <div>
                  <label className="block text-sm font-medium text-text-primary mb-1.5">
                    Company Name
                  </label>
                  <input
                    type="text"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="Acme Corp"
                    className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none"
                  />
                </div>

                {/* Personal Message */}
                <div>
                  <label className="block text-sm font-medium text-text-primary mb-1.5">
                    Personal Message
                  </label>
                  <textarea
                    value={personalMessage}
                    onChange={(e) => setPersonalMessage(e.target.value)}
                    placeholder="Hi, we enjoyed our recent conversation and would love to review your key documents..."
                    rows={3}
                    className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none resize-y"
                  />
                </div>

                {/* Custom Evaluation Criteria */}
                <div>
                  <label className="block text-sm font-medium text-text-primary mb-1.5">
                    Custom Evaluation Criteria
                  </label>
                  {customCriteria.length > 0 && (
                    <div className="space-y-2 mb-2">
                      {customCriteria.map((criterion, index) => (
                        <div key={index} className="flex items-center gap-2">
                          <input
                            type="text"
                            value={criterion}
                            onChange={(e) => updateCriterion(index, e.target.value)}
                            placeholder="e.g. Unit economics breakdown"
                            className="flex-1 rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none"
                          />
                          <button
                            type="button"
                            onClick={() => removeCriterion(index)}
                            className="text-text-tertiary hover:text-red-500 text-sm transition"
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={addCriterion}
                    className="text-sm text-accent hover:text-accent/80 transition"
                  >
                    + Add criterion
                  </button>
                </div>

                {error && (
                  <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                    {error}
                  </div>
                )}
              </div>

              <div className="px-6 py-4 border-t border-border flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    resetForm();
                  }}
                  className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !founderEmail.trim()}
                  className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 transition disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {submitting ? "Sending..." : "Send Request"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
