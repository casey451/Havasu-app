"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getStoredToken } from "@/lib/authStorage";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ok, setOk] = useState(false);

  useEffect(() => {
    const t = getStoredToken();
    if (!t) {
      router.replace("/login");
      return;
    }
    setOk(true);
  }, [router]);

  if (!ok) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-12 text-center text-sm text-zinc-500">
        Checking session…
      </div>
    );
  }

  return <>{children}</>;
}
