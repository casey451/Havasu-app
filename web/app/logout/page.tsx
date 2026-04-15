"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { clearSession } from "@/lib/authStorage";

export default function LogoutPage() {
  const router = useRouter();

  useEffect(() => {
    clearSession();
    router.replace("/");
    router.refresh();
  }, [router]);

  return (
    <main className="mx-auto max-w-md px-4 py-12 text-center text-sm text-zinc-500">
      Signing out…
    </main>
  );
}
