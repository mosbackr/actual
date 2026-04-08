import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import LinkedInProvider from "next-auth/providers/linkedin";
import GitHubProvider from "next-auth/providers/github";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID || "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || "",
    }),
    LinkedInProvider({
      clientId: process.env.LINKEDIN_CLIENT_ID || "",
      clientSecret: process.env.LINKEDIN_CLIENT_SECRET || "",
    }),
    GitHubProvider({
      clientId: process.env.GITHUB_CLIENT_ID || "",
      clientSecret: process.env.GITHUB_CLIENT_SECRET || "",
    }),
  ],
  callbacks: {
    async jwt({ token, account, profile }) {
      if (account && profile) {
        token.provider = account.provider;
        token.providerId = account.providerAccountId;

        // Exchange OAuth credentials for a backend JWT
        try {
          const res = await fetch(`${API_URL}/api/auth/token`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: token.email || profile.email,
              name: token.name || profile.name || "",
              provider: account.provider,
              provider_id: account.providerAccountId,
            }),
          });
          if (res.ok) {
            const data = await res.json();
            token.backendToken = data.token;
            token.backendUserId = data.user.id;
            token.backendRole = data.user.role;
          }
        } catch {
          // Backend unavailable — token will lack backend fields
        }
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.backendToken = token.backendToken;
        session.role = token.backendRole;
        session.backendUserId = token.backendUserId;
      }
      return session;
    },
  },
  secret: process.env.NEXTAUTH_SECRET,
};
