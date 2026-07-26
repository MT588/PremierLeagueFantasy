import type { Metadata } from "next";
import { Geist } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PL Fantasy Analytics",
  description: "FPL predictions, player ratings and optimal team picks",
};

const nav = [
  { href: "/", label: "Dashboard" },
  { href: "/players", label: "Players" },
  { href: "/team", label: "Optimal Team" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <header className="sticky top-0 z-20 border-b border-hairline bg-page/90 backdrop-blur">
          <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-8 px-4">
            <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-accent" />
              PL Fantasy
            </Link>
            <nav className="flex gap-1 text-sm">
              {nav.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  className="rounded-md px-3 py-1.5 text-ink-2 transition-colors hover:bg-surface hover:text-ink"
                >
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
        <footer className="mx-auto w-full max-w-6xl px-4 pb-8 text-xs text-ink-3">
          Data: official FPL API + vaastav/Fantasy-Premier-League · predictions are model
          estimates, not guarantees.
        </footer>
      </body>
    </html>
  );
}
