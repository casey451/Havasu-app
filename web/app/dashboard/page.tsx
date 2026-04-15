"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { deleteBusinessEvent, getMe, listBusinessEvents } from "@/lib/api";
import { getStoredToken, getStoredUser } from "@/lib/authStorage";
import type { BusinessEvent } from "@/lib/types";

export default function DashboardPage() {
  const token = getStoredToken()!;
  const [user, setUser] = useState(getStoredUser());
  const [events, setEvents] = useState<BusinessEvent[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setErr(null);
    try {
      const me = await getMe(token);
      setUser(me);
      const list = await listBusinessEvents(token);
      setEvents(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const pending =
    user?.role === "business" && user?.status !== "approved" ? true : false;

  async function onDelete(id: number) {
    if (!confirm("Delete this event?")) return;
    try {
      await deleteBusinessEvent(token, id);
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8 text-sm text-zinc-500">Loading…</main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">My events</h1>
        <div className="flex flex-wrap gap-2">
          {!pending && user?.role === "business" ? (
            <Link
              href="/dashboard/profile"
              className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              Business profile
            </Link>
          ) : null}
        <Link
          href={pending ? "#" : "/dashboard/event/new"}
          className={`rounded-md px-4 py-2 text-sm font-medium ${
            pending
              ? "cursor-not-allowed bg-zinc-200 text-zinc-500 dark:bg-zinc-800"
              : "bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900"
          }`}
          onClick={(e) => pending && e.preventDefault()}
        >
          Create event
        </Link>
        </div>
      </div>

      {user ? (
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          Signed in as {user.email} ({user.role})
        </p>
      ) : null}

      {pending ? (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
          <strong>Waiting for approval.</strong> An admin must approve your business before you can
          create or manage events.
        </div>
      ) : null}

      {err ? (
        <p className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          {err}
        </p>
      ) : null}

      <ul className="mt-8 space-y-3">
        {events.length === 0 ? (
          <li className="rounded-lg border border-dashed border-zinc-300 p-6 text-center text-sm text-zinc-500 dark:border-zinc-600">
            No events yet.
          </li>
        ) : (
          events.map((ev) => (
            <li
              key={ev.id}
              className="flex flex-col gap-2 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <p className="font-medium text-zinc-900 dark:text-zinc-50">{ev.title}</p>
                <p className="text-sm text-zinc-600 dark:text-zinc-400">
                  {ev.start_date}
                  {ev.start_time ? ` · ${ev.start_time}` : ""}
                  {ev.end_time ? `–${ev.end_time}` : ""}
                </p>
                <p className="text-sm text-zinc-500">
                  {[ev.location_label, ev.venue_name, ev.address].filter(Boolean).join(" · ") ||
                    "—"}
                </p>
              </div>
              <div className="flex gap-2">
                <Link
                  href={pending ? "#" : `/dashboard/event/${ev.id}/edit`}
                  className={`rounded border px-3 py-1 text-sm ${
                    pending
                      ? "pointer-events-none text-zinc-400"
                      : "border-zinc-300 text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-300"
                  }`}
                  onClick={(e) => pending && e.preventDefault()}
                >
                  Edit
                </Link>
                <button
                  type="button"
                  disabled={pending}
                  className="rounded border border-red-200 px-3 py-1 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:text-red-300"
                  onClick={() => void onDelete(ev.id)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))
        )}
      </ul>
    </main>
  );
}
