import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { NotificationPoller } from "@/components/NotificationPoller";
import { SiteNav } from "@/components/SiteNav";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Lake Havasu Events",
  description: "Events and schedules (Phase 1)",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} min-h-screen bg-zinc-50 font-sans antialiased dark:bg-zinc-950`}
      >
        <SiteNav />
        <NotificationPoller />
        {children}
      </body>
    </html>
  );
}
