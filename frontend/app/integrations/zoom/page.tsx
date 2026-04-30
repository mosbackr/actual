"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";

const ZOOM_CLIENT_ID = process.env.NEXT_PUBLIC_ZOOM_CLIENT_ID || "upWnGhAuQo6I5hJaEKON1Q";
const ZOOM_REDIRECT_URI = "https://www.deepthesis.co/api/zoom/oauth/callback";
const ZOOM_CONNECT_URL = `https://zoom.us/oauth/authorize?response_type=code&client_id=${ZOOM_CLIENT_ID}&redirect_uri=${encodeURIComponent(ZOOM_REDIRECT_URI)}`;

export default function ZoomIntegrationPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const [zoomConnected, setZoomConnected] = useState<boolean | null>(null);
  const [zoomEmail, setZoomEmail] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);

  useEffect(() => {
    if (!token) return;
    api.getZoomConnection(token).then((data) => {
      setZoomConnected(data.connected);
      setZoomEmail(data.zoom_email || null);
    }).catch(() => {});
  }, [token]);

  async function handleDisconnect() {
    if (!token) return;
    setDisconnecting(true);
    try {
      await api.disconnectZoom(token);
      setZoomConnected(false);
      setZoomEmail(null);
    } catch {
      // silent
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <div className="flex items-center gap-3 mb-6">
        <div className="h-12 w-12 rounded-xl bg-blue-500 flex items-center justify-center">
          <svg className="h-6 w-6 text-white" viewBox="0 0 24 24" fill="currentColor">
            <path d="M4.585 6.836a1.44 1.44 0 0 0-1.443 1.443v5.3a1.44 1.44 0 0 0 2.163 1.249l3.98-2.65v1.401a1.44 1.44 0 0 0 2.163 1.249l4.432-2.95a1.44 1.44 0 0 0 0-2.497l-4.432-2.95a1.44 1.44 0 0 0-2.163 1.249v1.401l-3.98-2.65a1.44 1.44 0 0 0-.72-.195z"/>
          </svg>
        </div>
        <div>
          <h1 className="font-serif text-3xl text-text-primary">Zoom Integration</h1>
          <p className="text-text-secondary">Import cloud recordings into Pitch Intelligence</p>
        </div>
      </div>

      {/* Connection Status */}
      <div className="rounded-lg border border-border bg-surface p-6 mb-8">
        {!session ? (
          <p className="text-text-secondary">Sign in to connect your Zoom account.</p>
        ) : zoomConnected === null ? (
          <p className="text-text-tertiary">Checking connection...</p>
        ) : zoomConnected ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-3 w-3 rounded-full bg-green-500" />
              <div>
                <p className="font-medium text-text-primary">Zoom Connected</p>
                {zoomEmail && <p className="text-sm text-text-secondary">{zoomEmail}</p>}
              </div>
            </div>
            <button
              onClick={handleDisconnect}
              disabled={disconnecting}
              className="rounded border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 transition disabled:opacity-50"
            >
              {disconnecting ? "Disconnecting..." : "Disconnect"}
            </button>
          </div>
        ) : (
          <div className="text-center py-4">
            <p className="text-text-primary font-medium mb-2">Connect your Zoom account</p>
            <p className="text-sm text-text-secondary mb-6 max-w-md mx-auto">
              Link your Zoom account to see your cloud recordings in Pitch Intelligence.
              You choose which recordings to import — we never download anything without your consent.
            </p>
            <a
              href={ZOOM_CONNECT_URL}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-6 py-3 text-sm font-medium text-white hover:bg-blue-600 transition"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M4.585 6.836a1.44 1.44 0 0 0-1.443 1.443v5.3a1.44 1.44 0 0 0 2.163 1.249l3.98-2.65v1.401a1.44 1.44 0 0 0 2.163 1.249l4.432-2.95a1.44 1.44 0 0 0 0-2.497l-4.432-2.95a1.44 1.44 0 0 0-2.163 1.249v1.401l-3.98-2.65a1.44 1.44 0 0 0-.72-.195z"/>
              </svg>
              Connect Zoom
            </a>
          </div>
        )}
      </div>

      {/* How It Works */}
      <div className="space-y-6">
        <h2 className="font-serif text-xl text-text-primary">How It Works</h2>

        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg border border-border bg-surface p-5">
            <div className="text-2xl mb-2">1</div>
            <h3 className="font-medium text-text-primary text-sm mb-1">Record to Cloud</h3>
            <p className="text-xs text-text-secondary">
              During a Zoom meeting, click Record &rarr; Record to the Cloud. Only meetings you choose to record are affected.
            </p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-5">
            <div className="text-2xl mb-2">2</div>
            <h3 className="font-medium text-text-primary text-sm mb-1">Choose What to Import</h3>
            <p className="text-xs text-text-secondary">
              Completed recordings appear in your Pitch Intelligence dashboard. Click Import on the ones you want to analyze.
            </p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-5">
            <div className="text-2xl mb-2">3</div>
            <h3 className="font-medium text-text-primary text-sm mb-1">Get AI Analysis</h3>
            <p className="text-xs text-text-secondary">
              Deep Thesis transcribes and analyzes your pitch, providing scores, fact-checks, and coaching feedback.
            </p>
          </div>
        </div>

        <div className="rounded border border-green-200 bg-green-50 px-5 py-4">
          <h3 className="font-medium text-green-800 text-sm mb-1">Your data, your choice</h3>
          <p className="text-xs text-green-700">
            We are notified when a cloud recording is ready, but we never download or process it unless you explicitly click Import.
            Recordings you don&apos;t import are never accessed or stored by Deep Thesis.
          </p>
        </div>

        <div className="rounded-lg border border-border bg-surface p-5">
          <h3 className="font-medium text-text-primary text-sm mb-2">Enable Cloud Recording in Zoom</h3>
          <ol className="list-decimal pl-5 space-y-2 text-xs text-text-secondary">
            <li>Sign in at <a href="https://zoom.us/signin" className="text-accent hover:text-accent-hover transition" target="_blank" rel="noopener noreferrer">zoom.us</a></li>
            <li>Go to <strong className="text-text-primary">Settings</strong> &rarr; <strong className="text-text-primary">Recording</strong></li>
            <li>Toggle on <strong className="text-text-primary">Cloud recording</strong></li>
          </ol>
          <p className="text-xs text-text-tertiary mt-2">Requires Zoom Pro, Business, or Enterprise plan.</p>
        </div>

        <p className="text-xs text-text-tertiary">
          Need help? <a href="mailto:support@deepthesis.co" className="text-accent hover:text-accent-hover transition">support@deepthesis.co</a>
          {" · "}
          <Link href="/docs/zoom" className="text-accent hover:text-accent-hover transition">Full documentation</Link>
          {" · "}
          <Link href="/privacy" className="text-accent hover:text-accent-hover transition">Privacy policy</Link>
        </p>
      </div>
    </div>
  );
}
