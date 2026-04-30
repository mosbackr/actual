export const metadata = { title: "Privacy Policy — Deep Thesis" };

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-serif text-3xl text-text-primary mb-2">Privacy Policy</h1>
      <p className="text-sm text-text-tertiary mb-10">Last updated: April 26, 2026</p>

      <div className="space-y-8 text-sm text-text-secondary leading-relaxed">
        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">1. Introduction</h2>
          <p>
            Deep Thesis (&quot;we,&quot; &quot;our,&quot; or &quot;us&quot;) operates the website www.deepthesis.co and related services
            (collectively, the &quot;Service&quot;). This Privacy Policy explains how we collect, use, disclose, and
            safeguard your information when you use our Service.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">2. Information We Collect</h2>
          <p className="mb-3"><strong className="text-text-primary">Account Information:</strong> When you create an account, we collect your name, email address, and password. If you sign in via Google, we receive your name, email, and profile image from Google.</p>
          <p className="mb-3"><strong className="text-text-primary">Profile Information:</strong> You may optionally provide your ecosystem role, region, and avatar image.</p>
          <p className="mb-3"><strong className="text-text-primary">Usage Data:</strong> We collect information about how you interact with the Service, including pages visited, analyses run, and features used.</p>
          <p className="mb-3"><strong className="text-text-primary">Uploaded Content:</strong> When you use our analysis or pitch intelligence features, we process documents, recordings, and other content you submit.</p>
          <p><strong className="text-text-primary">Third-Party Integrations:</strong> If you connect your Zoom account, we receive your Zoom email, account ID, and access tokens. When a cloud recording completes, we are notified of its availability — but we do not download or process the recording unless you explicitly choose to import it. We do not access your Zoom meetings, contacts, or chat messages.</p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">3. How We Use Your Information</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>To provide, maintain, and improve the Service</li>
            <li>To process and analyze content you submit (startup analyses, pitch recordings)</li>
            <li>To send transactional emails (analysis complete, account updates)</li>
            <li>To manage your account and subscriptions</li>
            <li>To import Zoom cloud recordings you have authorized</li>
            <li>To generate AI-powered analysis and feedback</li>
          </ul>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">4. Data Sharing</h2>
          <p className="mb-3">We do not sell your personal information. We may share data with:</p>
          <ul className="list-disc pl-5 space-y-2">
            <li><strong className="text-text-primary">Service providers:</strong> Cloud hosting (AWS), email delivery (Resend), payment processing (Stripe), and AI analysis (Anthropic) providers that help us operate the Service.</li>
            <li><strong className="text-text-primary">Legal requirements:</strong> When required by law, subpoena, or to protect our rights.</li>
          </ul>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">5. Data Security</h2>
          <p>
            We use industry-standard security measures including encryption in transit (TLS), secure password hashing (bcrypt), and access controls. However, no method of transmission over the Internet is 100% secure.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">6. Data Retention</h2>
          <p>
            We retain your account data for as long as your account is active. Uploaded content and analysis results are retained until you delete them or close your account. You may request deletion of your data at any time by contacting us.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">7. Your Rights</h2>
          <p className="mb-3">You have the right to:</p>
          <ul className="list-disc pl-5 space-y-2">
            <li>Access the personal data we hold about you</li>
            <li>Request correction of inaccurate data</li>
            <li>Request deletion of your data</li>
            <li>Disconnect third-party integrations (e.g., Zoom) at any time from your profile</li>
            <li>Unsubscribe from marketing emails</li>
          </ul>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">8. Cookies</h2>
          <p>
            We use essential cookies for authentication and session management. We do not use advertising or tracking cookies.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">9. Changes to This Policy</h2>
          <p>
            We may update this Privacy Policy from time to time. We will notify you of significant changes by posting the new policy on this page and updating the &quot;Last updated&quot; date.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">10. Contact</h2>
          <p>
            If you have questions about this Privacy Policy, contact us at{" "}
            <a href="mailto:support@deepthesis.co" className="text-accent hover:text-accent-hover transition">support@deepthesis.co</a>.
          </p>
        </section>
      </div>
    </div>
  );
}
