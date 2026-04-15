import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Havasu Events Frontend",
  description: "Thin frontend for havasu backend",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.className} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-zinc-50 text-zinc-900">
        <header className="border-b border-zinc-200 bg-white">
          <nav className="mx-auto flex max-w-3xl items-center gap-6 px-4 py-3 text-sm font-medium">
            <Link href="/" className="text-zinc-800 hover:text-zinc-600">
              Discover
            </Link>
            <Link href="/submit" className="text-zinc-800 hover:text-zinc-600">
              Submit
            </Link>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
