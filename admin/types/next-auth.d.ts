import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    backendToken?: string;
    role?: string;
    backendUserId?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    backendToken?: string;
    backendUserId?: string;
    backendRole?: string;
    provider?: string;
    providerId?: string;
  }
}
