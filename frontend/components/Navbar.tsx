import Link from "next/link";
import { AuthButton } from "./AuthButton";

export function Navbar() {
  return (
    <nav className="border-b border-border bg-surface">
      <div className="mx-auto max-w-6xl px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/" className="font-serif text-xl text-text-primary">
              Deep Thesis
            </Link>
            <div className="hidden md:flex items-center gap-6">
              <Link href="/startups" className="text-sm text-text-secondary hover:text-text-primary transition">
                Companies
              </Link>
              <Link href="/experts/apply" className="text-sm text-text-secondary hover:text-text-primary transition">
                Become a Contributor
              </Link>
            </div>
          </div>
          <AuthButton />
        </div>
      </div>
    </nav>
  );
}
