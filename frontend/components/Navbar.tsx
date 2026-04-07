import Link from "next/link";
import { AuthButton } from "./AuthButton";

export function Navbar() {
  return (
    <nav className="border-b border-gray-800 bg-gray-950">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/" className="text-xl font-bold text-white">
              Acutal
            </Link>
            <div className="hidden md:flex items-center gap-6">
              <Link href="/" className="text-sm text-gray-400 hover:text-white transition">
                Discover
              </Link>
              <Link href="/experts/apply" className="text-sm text-gray-400 hover:text-white transition">
                Become an Expert
              </Link>
            </div>
          </div>
          <AuthButton />
        </div>
      </div>
    </nav>
  );
}
