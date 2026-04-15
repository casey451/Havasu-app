"use client";

import { useEffect, useState } from "react";

import { approveSubmission, getAdminPending } from "@/lib/api";

type PendingItem = {
  id: string;
  title: string;
  start_date?: string;
  location?: string;
};

export default function AdminPage() {
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function loadPending() {
    setLoading(true);
    setError(null);
    try {
      const rows = await getAdminPending();
      setPending(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load pending submissions");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPending();
  }, []);

  async function handleApprove(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await approveSubmission(id);
      setPending((old) => old.filter((row) => row.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approve failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-semibold">Admin</h1>
      <p className="mt-1 text-sm text-zinc-600">
        Pending submissions. Set <code>NEXT_PUBLIC_ADMIN_TOKEN</code> in your env to use this page.
      </p>

      {loading ? <p className="mt-4 text-sm text-zinc-500">Loading...</p> : null}
      {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}

      <ul className="mt-6 space-y-3">
        {pending.map((row) => (
          <li key={row.id} className="rounded-md border border-zinc-200 bg-white p-4">
            <p className="font-medium">{row.title}</p>
            <p className="text-sm text-zinc-600">
              {row.start_date || "-"} | {row.location || "-"}
            </p>
            <button
              type="button"
              onClick={() => void handleApprove(row.id)}
              disabled={busyId === row.id}
              className="mt-3 rounded bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              {busyId === row.id ? "Approving..." : "Approve"}
            </button>
          </li>
        ))}
      </ul>
    </main>
  );
}
