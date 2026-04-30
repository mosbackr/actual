export const metadata = { title: "Terms of Service — Deep Thesis" };

export default function TermsPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-serif text-3xl text-text-primary mb-2">Terms of Service</h1>
      <p className="text-sm text-text-tertiary mb-10">Last updated: April 26, 2026</p>

      <div className="space-y-8 text-sm text-text-secondary leading-relaxed">
        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">1. Acceptance of Terms</h2>
          <p>
            By accessing or using Deep Thesis (&quot;the Service&quot;), operated by Deep Thesis Inc. (&quot;we,&quot; &quot;our,&quot; or &quot;us&quot;),
            you agree to be bound by these Terms of Service. If you do not agree, do not use the Service.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">2. Description of Service</h2>
          <p>
            Deep Thesis provides AI-powered startup investment intelligence, including company analysis, pitch
            recording analysis, investor rankings, and related tools. The Service is available at www.deepthesis.co
            and through connected integrations.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">3. Accounts</h2>
          <p>
            You must create an account to use most features of the Service. You are responsible for maintaining
            the confidentiality of your account credentials and for all activity under your account. You must
            provide accurate and complete information when creating your account.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">4. Subscriptions and Payment</h2>
          <p className="mb-3">
            Some features require a paid subscription. Subscriptions are billed monthly through Stripe.
            You may cancel your subscription at any time from your account settings. Cancellation takes
            effect at the end of the current billing period.
          </p>
          <p>
            We reserve the right to change pricing with 30 days&apos; notice. Price changes do not affect
            your current billing period.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">5. User Content</h2>
          <p className="mb-3">
            You retain ownership of all content you upload to the Service, including documents, recordings,
            and other materials. By uploading content, you grant us a limited license to process, analyze,
            and store it solely for the purpose of providing the Service to you.
          </p>
          <p>
            You represent that you have the right to upload any content you submit and that your content
            does not violate any third party&apos;s rights.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">6. Third-Party Integrations</h2>
          <p>
            The Service may integrate with third-party services such as Zoom. When you connect a third-party
            account, you authorize us to access the data described during the authorization process (e.g., Zoom
            cloud recordings). You may disconnect integrations at any time from your profile page. We are not
            responsible for the availability or practices of third-party services.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">7. Acceptable Use</h2>
          <p className="mb-3">You agree not to:</p>
          <ul className="list-disc pl-5 space-y-2">
            <li>Use the Service for any unlawful purpose</li>
            <li>Attempt to gain unauthorized access to the Service or its systems</li>
            <li>Scrape, crawl, or otherwise extract data from the Service by automated means</li>
            <li>Interfere with or disrupt the Service or its infrastructure</li>
            <li>Resell or redistribute the Service or its analysis outputs without permission</li>
          </ul>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">8. AI-Generated Content</h2>
          <p>
            The Service uses artificial intelligence to generate analyses, scores, and recommendations.
            AI-generated content is provided for informational purposes only and should not be considered
            financial, investment, or legal advice. We do not guarantee the accuracy, completeness, or
            reliability of AI-generated outputs. You are solely responsible for any decisions made based
            on information from the Service.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">9. Limitation of Liability</h2>
          <p>
            To the maximum extent permitted by law, Deep Thesis shall not be liable for any indirect,
            incidental, special, consequential, or punitive damages, or any loss of profits or revenue,
            whether incurred directly or indirectly. Our total liability for any claim arising from the
            Service shall not exceed the amount you paid us in the 12 months preceding the claim.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">10. Disclaimer of Warranties</h2>
          <p>
            The Service is provided &quot;as is&quot; and &quot;as available&quot; without warranties of any kind, either
            express or implied, including but not limited to implied warranties of merchantability,
            fitness for a particular purpose, and non-infringement.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">11. Termination</h2>
          <p>
            We may suspend or terminate your access to the Service at any time for violation of these
            Terms or for any other reason with reasonable notice. Upon termination, your right to use
            the Service ceases immediately. You may request export of your data before account closure.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">12. Changes to Terms</h2>
          <p>
            We may modify these Terms at any time. We will notify you of material changes by posting
            the updated Terms on this page. Your continued use of the Service after changes constitutes
            acceptance of the new Terms.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-lg text-text-primary mb-2">13. Contact</h2>
          <p>
            Questions about these Terms? Contact us at{" "}
            <a href="mailto:support@deepthesis.co" className="text-accent hover:text-accent-hover transition">support@deepthesis.co</a>.
          </p>
        </section>
      </div>
    </div>
  );
}
