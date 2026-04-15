"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { approveBusiness, getMe, listAdminSubmissions, listPendingBusinesses, rejectBusiness } from "@/lib/api";
import type { AdminSubmission, PendingBusiness } from "@/lib/types";
import { getStoredToken, getStoredUser } from "@/lib/authStorage";

export default function AdminPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [pending, setPending] = useState<PendingBusiness[]>([]);
  const [approvedSubs, setApprovedSubs] = useState<AdminSubmission[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [rowBusy, setRowBusy] = useState<number | null>(null);

  useEffect(() => {
    const t = getStoredToken();
    if (!t) {
      router.replace("/login");
      return;
    }
    setToken(t);
    const u = getStoredUser();
    if (u?.role !== "admin") {
      router.replace("/dashboard");
      return;
    }
    setIsAdmin(true);
  }, [router]);

  const loadPending = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setErr(null);
    try {
      const rows = await listPendingBusinesses(token);
      setPending(rows);
      const subs = await listAdminSubmissions("approved");
      setApprovedSubs(subs.slice(0, 12));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load pending businesses");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!token || !isAdmin) return;
    void getMe(token).catch(() => router.replace("/login"));
  }, [token, isAdmin, router]);

  useEffect(() => {
    if (!token || !isAdmin) return;
    void loadPending();
  }, [token, isAdmin, loadPending]);

  async function doApprove(id: number) {
    if (!token) return;
    setRowBusy(id);
    setErr(null);
    setMsg(null);
    try {
      await approveBusiness(token, id);
      setMsg(`Approved business #${id}.`);
      await loadPending();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setRowBusy(null);
    }
  }

  async function doReject(id: number) {
    if (!token) return;
    setRowBusy(id);
    setErr(null);
    setMsg(null);
    try {
      await rejectBusiness(token, id);
      setMsg(`Rejected business #${id}.`);
      await loadPending();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setRowBusy(null);
    }
  }

  if (!isAdmin) {
    return (
      <main className="mx-auto max-w-lg px-4 py-12 text-sm text-zinc-500">Checking…</main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <Link href="/dashboard" className="text-sm text-blue-600 hover:underline">
        ← Dashboard
      </Link>
      <h1 className="mt-4 text-2xl font-bold text-zinc-900 dark:text-zinc-50">Admin</h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        Pending business accounts. Approve to let them post events.
      </p>

      {err ? (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400">{err}</p>
      ) : null}
      {msg ? (
        <p className="mt-2 text-sm text-green-700 dark:text-green-400">{msg}</p>
      ) : null}

      <div className="mt-6">
        {loading && !pending.length ? (
          <p className="text-sm text-zinc-500">Loading…</p>
        ) : pending.length === 0 ? (
          <p className="rounded-lg border border-dashed border-zinc-300 p-6 text-center text-sm text-zinc-500 dark:border-zinc-600">
            No pending businesses.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {pending.map((b) => (
              <li key={b.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="font-medium text-zinc-900 dark:text-zinc-100">{b.name}</p>
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">{b.email}</p>
                  <p className="mt-1 text-xs text-zinc-400">ID {b.id}</p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={rowBusy === b.id}
                    onClick={() => void doApprove(b.id)}
                    className="rounded-md bg-green-700 px-4 py-2 text-sm font-medium text-white hover:bg-green-800 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={rowBusy === b.id}
                    onClick={() => void doReject(b.id)}
                    className="rounded-md bg-red-700 px-4 py-2 text-sm font-medium text-white hover:bg-red-800 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <section className="mt-10 border-t border-zinc-200 pt-8 dark:border-zinc-800">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Submission analytics</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Approved submissions with views, clicks, and CTR.
        </p>
        {approvedSubs.length === 0 ? (
          <p className="mt-4 rounded-lg border border-dashed border-zinc-300 p-4 text-sm text-zinc-500 dark:border-zinc-600">
            No approved submissions yet.
          </p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
                  <th className="py-2 pr-4">Title</th>
                  <th className="py-2 pr-4">Views</th>
                  <th className="py-2 pr-4">Clicks</th>
                  <th className="py-2 pr-4">CTR</th>
                </tr>
              </thead>
              <tbody>
                {approvedSubs.map((s) => (
                  <tr key={s.id} className="border-b border-zinc-100 dark:border-zinc-900">
                    <td className="py-2 pr-4 text-zinc-900 dark:text-zinc-100">{s.title}</td>
                    <td className="py-2 pr-4 text-zinc-700 dark:text-zinc-300">{s.view_count ?? 0}</td>
                    <td className="py-2 pr-4 text-zinc-700 dark:text-zinc-300">{s.click_count ?? 0}</td>
                    <td className="py-2 pr-4 text-zinc-700 dark:text-zinc-300">
                      {(((s.ctr ?? 0) * 100) || 0).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
