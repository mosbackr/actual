export const metadata = { title: "Support — Deep Thesis" };

export default function SupportPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-serif text-3xl text-text-primary mb-2">Support</h1>
      <p className="text-text-secondary mb-10">We&apos;re here to help. Reach out anytime.</p>

      <div className="space-y-6">
        <div className="rounded border border-border bg-surface p-6">
          <h2 className="font-serif text-lg text-text-primary mb-2">Email Support</h2>
          <p className="text-sm text-text-secondary mb-3">
            For account issues, billing questions, bug reports, or general inquiries.
          </p>
          <a
            href="mailto:support@deepthesis.co"
            className="inline-flex items-center gap-2 text-sm font-medium text-accent hover:text-accent-hover transition"
          >
            support@deepthesis.co
          </a>
        </div>

        <div className="rounded border border-border bg-surface p-6">
          <h2 className="font-serif text-lg text-text-primary mb-2">Zoom Integration</h2>
          <p className="text-sm text-text-secondary mb-3">
            To connect or disconnect your Zoom account, visit your{" "}
            <a href="/profile" className="text-accent hover:text-accent-hover transition">profile page</a>.
            Cloud recordings are automatically imported into Pitch Intelligence after connecting.
          </p>
          <p className="text-sm text-text-secondary">
            If you experience issues with the Zoom integration, email us at{" "}
            <a href="mailto:support@deepthesis.co" className="text-accent hover:text-accent-hover transition">support@deepthesis.co</a>.
          </p>
        </div>

        <div className="rounded border border-border bg-surface p-6">
          <h2 className="font-serif text-lg text-text-primary mb-2">Account &amp; Billing</h2>
          <p className="text-sm text-text-secondary">
            Manage your subscription from the{" "}
            <a href="/billing" className="text-accent hover:text-accent-hover transition">billing page</a>.
            For refund requests or billing issues, contact{" "}
            <a href="mailto:support@deepthesis.co" className="text-accent hover:text-accent-hover transition">support@deepthesis.co</a>.
          </p>
        </div>
      </div>
    </div>
  );
}
