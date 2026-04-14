import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PROTECTED_PATHS = ["/startups", "/insights", "/analyze", "/billing"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public shared conversation links
  if (pathname.startsWith("/insights/shared/")) return NextResponse.next();

  const isProtected = PROTECTED_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );

  if (!isProtected) return NextResponse.next();

  // NextAuth stores session token in this cookie
  const token =
    request.cookies.get("next-auth.session-token")?.value ||
    request.cookies.get("__Secure-next-auth.session-token")?.value;

  if (token) return NextResponse.next();

  const signInUrl = new URL("/auth/signin", request.url);
  signInUrl.searchParams.set("callbackUrl", pathname);
  return NextResponse.redirect(signInUrl);
}

export const config = {
  matcher: ["/startups/:path*", "/insights/:path*", "/analyze/:path*", "/billing/:path*"],
};
