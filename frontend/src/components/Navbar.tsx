"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Navbar() {
  const pathname = usePathname();

  const linkClasses = (href: string) => {
    const isActive = href === "/" ? pathname === "/" : pathname.startsWith(href);
    return `text-xs font-mono uppercase tracking-widest transition-colors ${
      isActive
        ? "text-[var(--color-war-text)] border-b border-[var(--color-war-text)]"
        : "text-[var(--color-war-muted)] hover:text-[var(--color-war-text)]"
    }`;
  };

  return (
    <nav className="border-b border-[var(--color-war-border)] bg-[var(--color-war-bg)] sticky top-0 z-50">
      <div className="w-full px-6 h-12 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3">
          <div className="h-4 w-4 bg-[var(--color-war-text)]"></div>
          <span className="text-lg font-serif font-black tracking-tight text-[var(--color-war-text)]">
            FINSIGHT<span className="font-light mx-2 text-[var(--color-war-muted)]">|</span>WAR ROOM
          </span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-8 h-full">
          <Link href="/" className={linkClasses("/") + " h-full flex items-center"}>
            Terminal
          </Link>
          <Link href="/history" className={linkClasses("/history") + " h-full flex items-center"}>
            Archive
          </Link>
        </div>
      </div>
    </nav>
  );
}
