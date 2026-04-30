export const metadata = { title: "Zoom Integration Guide — Deep Thesis" };

export default function ZoomDocsPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-serif text-3xl text-text-primary mb-2">Zoom Integration Guide</h1>
      <p className="text-text-secondary mb-10">
        Connect your Zoom account to automatically import cloud recordings into Pitch Intelligence.
      </p>

      <div className="space-y-8 text-sm text-text-secondary leading-relaxed">
        <section>
          <h2 className="font-serif text-lg text-text-primary mb-3">How to Connect</h2>
          <ol className="list-decimal pl-5 space-y-3">
            <li>Sign in to your Deep Thesis account at <a href="https://www.deepthesis.co" className="text-accent hover:text-accent-hover transition">www.deepthesis.co</a>.</li>
            <li>Click the <strong className="text-text-primary">Connect Zoom</strong> button in the navigation bar, or go to your <a href="/profile" className="text-accent hover:text-accent-hover transition">Profile</a> page.</li>
            <li>You will be redirected to Zoom to authorize Deep Thesis. Click <strong className="text-text-primary">Allow</strong> to grant access.</li>
            <li>You will be redirected back to Deep Thesis. A confirmation message will appear when the connection is successful.</li>
          </ol>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-3">What We Access</h2>
          <p className="mb-3">When you connect your Zoom account, Deep Thesis accesses:</p>
          <ul className="list-disc pl-5 space-y-2">
            <li><strong className="text-text-primary">Cloud recordings:</strong> We import completed cloud recordings so you can analyze them in Pitch Intelligence.</li>
            <li><strong className="text-text-primary">Basic profile info:</strong> Your Zoom email address, used to identify your connection.</li>
          </ul>
          <p className="mt-3">We do <strong className="text-text-primary">not</strong> access your Zoom meetings, calendar, contacts, or chat messages.</p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-3">How to Enable Cloud Recording in Zoom</h2>
          <p className="mb-3">Deep Thesis only works with Zoom <strong className="text-text-primary">cloud recordings</strong> (not local recordings saved to your computer). To enable cloud recording:</p>
          <ol className="list-decimal pl-5 space-y-3">
            <li>Sign in at <a href="https://zoom.us/signin" className="text-accent hover:text-accent-hover transition" target="_blank" rel="noopener noreferrer">zoom.us</a>.</li>
            <li>Go to <strong className="text-text-primary">Settings</strong> &rarr; <strong className="text-text-primary">Recording</strong>.</li>
            <li>Toggle on <strong className="text-text-primary">Cloud recording</strong>.</li>
            <li>During a meeting, click <strong className="text-text-primary">Record</strong> &rarr; <strong className="text-text-primary">Record to the Cloud</strong>.</li>
          </ol>
          <p className="mt-3 text-xs text-text-tertiary">Note: Cloud recording requires a Zoom Pro, Business, or Enterprise plan.</p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-3">How It Works</h2>
          <ol className="list-decimal pl-5 space-y-3">
            <li>You record a Zoom meeting to the cloud (you control which meetings to record).</li>
            <li>When the recording is ready, it appears in your <a href="/pitch-intelligence" className="text-accent hover:text-accent-hover transition">Pitch Intelligence</a> dashboard under <strong className="text-text-primary">Zoom Recordings</strong>.</li>
            <li>You choose which recordings to import by clicking <strong className="text-text-primary">Import &amp; Analyze</strong>.</li>
            <li>Deep Thesis downloads and analyzes the recording, providing AI-powered feedback.</li>
          </ol>
          <div className="mt-4 rounded border border-green-200 bg-green-50 px-4 py-3">
            <p className="text-sm text-green-800">
              <strong>Your data, your choice.</strong> We never download or process a recording unless you explicitly click Import. Recordings you don&apos;t import are never accessed or stored by Deep Thesis.
            </p>
          </div>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-3">How to Disconnect</h2>
          <ol className="list-decimal pl-5 space-y-3">
            <li>Go to your <a href="/profile" className="text-accent hover:text-accent-hover transition">Profile</a> page.</li>
            <li>Under <strong className="text-text-primary">Connected Apps</strong>, click <strong className="text-text-primary">Disconnect</strong> next to Zoom.</li>
            <li>Your Zoom account will be unlinked and no further recordings will be imported.</li>
          </ol>
          <p className="mt-3">
            You can also remove the app from your Zoom account at{" "}
            <a href="https://marketplace.zoom.us/user/installed" className="text-accent hover:text-accent-hover transition" target="_blank" rel="noopener noreferrer">marketplace.zoom.us/user/installed</a>.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-3">Troubleshooting</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li><strong className="text-text-primary">Connection failed:</strong> Make sure you are logged into the correct Zoom account when authorizing.</li>
            <li><strong className="text-text-primary">Recordings not appearing:</strong> Only cloud recordings are imported. Local recordings stored on your computer are not accessible to Deep Thesis. Ensure cloud recording is enabled in your Zoom settings.</li>
            <li><strong className="text-text-primary">Need help?</strong> Contact <a href="mailto:support@deepthesis.co" className="text-accent hover:text-accent-hover transition">support@deepthesis.co</a>.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
