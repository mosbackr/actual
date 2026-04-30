"use client";

import { useSession } from "next-auth/react";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ExpertApplication } from "@/lib/types";

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

export default function ProfilePage() {
  const { data: session, update: updateSession } = useSession();
  const [application, setApplication] = useState<ExpertApplication | null>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [ecosystemRole, setEcosystemRole] = useState("");
  const [region, setRegion] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [zoomConnected, setZoomConnected] = useState(false);
  const [zoomEmail, setZoomEmail] = useState<string | null>(null);
  const [disconnectingZoom, setDisconnectingZoom] = useState(false);

  const backendToken = (session as any)?.backendToken;

  useEffect(() => {
    if (!session) return;
    if (backendToken) {
      api.getMyApplication(backendToken).then(setApplication).catch(() => {});
      api.getMe(backendToken).then((data) => {
        setName(data.name);
        setAvatarUrl(data.avatar_url || null);
        setEcosystemRole(data.ecosystem_role || "");
        setRegion(data.region || "");
      }).catch(() => {});
      api.getZoomConnection(backendToken).then((data) => {
        setZoomConnected(data.connected);
        setZoomEmail(data.zoom_email || null);
      }).catch(() => {});
    }
  }, [session, backendToken]);

  if (!session) {
    return (
      <div className="text-center py-20">
        <p className="text-text-secondary">Please sign in to view your profile.</p>
      </div>
    );
  }

  async function handleSave() {
    if (!backendToken) return;
    setSaving(true);
    setMessage("");

    try {
      const res = await fetch(`${API_URL}/api/me/profile`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${backendToken}`,
        },
        body: JSON.stringify({
          name,
          avatar_url: avatarUrl,
          ecosystem_role: ecosystemRole,
          region,
        }),
      });

      if (!res.ok) throw new Error("Failed to update profile");

      const data = await res.json();
      setName(data.name);
      setAvatarUrl(data.avatar_url);
      setEcosystemRole(data.ecosystem_role || "");
      setRegion(data.region || "");
      setEditing(false);
      setMessage("Profile updated");

      await updateSession({ name: data.name, image: data.avatar_url });
    } catch {
      setMessage("Failed to update profile");
    } finally {
      setSaving(false);
    }
  }

  function handleAvatarClick() {
    fileInputRef.current?.click();
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 2 * 1024 * 1024) {
      setMessage("Image must be under 2MB");
      return;
    }

    setUploading(true);
    setMessage("");

    const reader = new FileReader();
    reader.onload = async () => {
      const dataUrl = reader.result as string;
      setAvatarUrl(dataUrl);
      setUploading(false);
    };
    reader.readAsDataURL(file);
  }

  async function handleDisconnectZoom() {
    if (!backendToken) return;
    setDisconnectingZoom(true);
    try {
      await api.disconnectZoom(backendToken);
      setZoomConnected(false);
      setZoomEmail(null);
    } catch {
      setMessage("Failed to disconnect Zoom");
    } finally {
      setDisconnectingZoom(false);
    }
  }

  const zoomRedirectUri = "https://www.deepthesis.co/api/zoom/oauth/callback";
  const zoomClientId = process.env.NEXT_PUBLIC_ZOOM_CLIENT_ID || "upWnGhAuQo6I5hJaEKON1Q";
  const zoomConnectUrl = `https://zoom.us/oauth/authorize?response_type=code&client_id=${zoomClientId}&redirect_uri=${encodeURIComponent(zoomRedirectUri)}`;

  const initials = (name || session.user?.name || "?")
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  const statusColors: Record<string, string> = {
    approved: "text-score-high",
    rejected: "text-score-low",
    pending: "text-score-mid",
  };

  const inputClasses =
    "w-full rounded border border-border bg-surface px-4 py-2.5 text-sm text-text-primary placeholder-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

  const selectClasses =
    "w-full rounded border border-border bg-surface px-4 py-2.5 text-sm text-text-primary focus:border-accent focus:ring-1 focus:ring-accent outline-none";

  return (
    <div className="max-w-2xl mx-auto py-10">
      <h1 className="font-serif text-3xl text-text-primary mb-6">Profile</h1>

      <div className="rounded border border-border bg-surface p-6 mb-8">
        <div className="flex items-start gap-5">
          <button
            onClick={editing ? handleAvatarClick : undefined}
            className={`relative flex-shrink-0 h-20 w-20 rounded-full overflow-hidden ${editing ? "cursor-pointer group" : ""}`}
            type="button"
            disabled={!editing}
          >
            {avatarUrl || session.user?.image ? (
              <img
                src={avatarUrl || session.user?.image || ""}
                alt=""
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="h-full w-full bg-accent/10 flex items-center justify-center text-accent font-medium text-lg">
                {initials}
              </div>
            )}
            {editing && (
              <div className="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                <span className="text-white text-xs font-medium">Change</span>
              </div>
            )}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileChange}
          />

          <div className="flex-1 min-w-0">
            {editing ? (
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-text-primary mb-1">Name</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className={inputClasses}
                  />
                </div>
                <p className="text-sm text-text-tertiary">{session.user?.email}</p>
                <div>
                  <label className="block text-sm font-medium text-text-primary mb-1">Role in Ecosystem</label>
                  <select value={ecosystemRole} onChange={(e) => setEcosystemRole(e.target.value)} className={selectClasses}>
                    <option value="">Select your role...</option>
                    {ECOSYSTEM_ROLES.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-text-primary mb-1">Region</label>
                  <select value={region} onChange={(e) => setRegion(e.target.value)} className={selectClasses}>
                    <option value="">Select your region...</option>
                    {REGIONS.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </div>
                <div className="flex gap-2 pt-1">
                  <button
                    onClick={handleSave}
                    disabled={saving || uploading}
                    className="rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50 transition"
                  >
                    {saving ? "Saving..." : "Save"}
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="rounded border border-border px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <h2 className="font-serif text-lg text-text-primary">{name || session.user?.name}</h2>
                <p className="text-sm text-text-secondary">{session.user?.email}</p>
                {ecosystemRole && (
                  <p className="text-sm text-text-secondary mt-1">{ecosystemRole}</p>
                )}
                {region && (
                  <p className="text-sm text-text-tertiary">{region}</p>
                )}
                <button
                  onClick={() => setEditing(true)}
                  className="mt-3 text-sm text-accent hover:text-accent-hover transition"
                >
                  Edit Profile
                </button>
              </>
            )}
          </div>
        </div>

        {message && (
          <p className={`text-sm mt-4 ${message.includes("Failed") ? "text-score-low" : "text-score-high"}`}>
            {message}
          </p>
        )}
      </div>

      {/* Connected Apps */}
      <div className="rounded border border-border bg-surface p-6 mb-8">
        <h3 className="font-medium text-text-primary mb-4">Connected Apps</h3>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-blue-500 flex items-center justify-center">
              <svg className="h-5 w-5 text-white" viewBox="0 0 24 24" fill="currentColor">
                <path d="M4.585 6.836a1.44 1.44 0 0 0-1.443 1.443v5.3a1.44 1.44 0 0 0 2.163 1.249l3.98-2.65v1.401a1.44 1.44 0 0 0 2.163 1.249l4.432-2.95a1.44 1.44 0 0 0 0-2.497l-4.432-2.95a1.44 1.44 0 0 0-2.163 1.249v1.401l-3.98-2.65a1.44 1.44 0 0 0-.72-.195z"/>
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-text-primary">Zoom</p>
              {zoomConnected ? (
                <p className="text-xs text-text-secondary">{zoomEmail || "Connected"}</p>
              ) : (
                <p className="text-xs text-text-tertiary">Auto-import cloud recordings</p>
              )}
            </div>
          </div>
          {zoomConnected ? (
            <button
              onClick={handleDisconnectZoom}
              disabled={disconnectingZoom}
              className="rounded border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 transition disabled:opacity-50"
            >
              {disconnectingZoom ? "Disconnecting..." : "Disconnect"}
            </button>
          ) : (
            <a
              href={zoomConnectUrl}
              className="rounded bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 transition"
            >
              Connect Zoom
            </a>
          )}
        </div>
      </div>

      {application && (
        <div className="rounded border border-border bg-surface p-6">
          <h3 className="font-medium text-text-primary mb-3">Contributor Application</h3>
          <p className="text-sm text-text-secondary">
            Status:{" "}
            <span className={statusColors[application.application_status] || "text-text-secondary"}>
              {application.application_status}
            </span>
          </p>
          <p className="text-sm text-text-secondary mt-1">
            Industries: {application.industries.join(", ")}
          </p>
          <p className="text-sm text-text-secondary mt-1">
            Skills: {application.skills.join(", ")}
          </p>
        </div>
      )}
    </div>
  );
}
