"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { EventForm } from "@/components/EventForm";
import { listBusinessEvents, updateBusinessEvent } from "@/lib/api";
import type { BusinessEvent, BusinessEventInput } from "@/lib/types";
import { getStoredToken } from "@/lib/authStorage";

export default function EditEventPage() {
  const router = useRouter();
  const params = useParams();
  const id = Number(params.id);
  const token = getStoredToken()!;

  const [ev, setEv] = useState<BusinessEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await listBusinessEvents(token);
      const found = list.find((e) => e.id === id) ?? null;
      if (!found) {
        setNotFound(true);
      } else {
        setEv(found);
      }
    } catch {
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [token, id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleSubmit(data: BusinessEventInput) {
    await updateBusinessEvent(token, id, data);
    router.push("/dashboard");
    router.refresh();
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8 text-sm text-zinc-500">Loading…</main>
    );
  }

  if (notFound || !ev) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <p>Event not found.</p>
        <Link href="/dashboard" className="mt-4 inline-block text-blue-600 hover:underline">
          Back
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/dashboard" className="text-sm text-blue-600 hover:underline">
        ← Dashboard
      </Link>
      <h1 className="mt-4 text-2xl font-bold text-zinc-900 dark:text-zinc-50">Edit event</h1>
      <div className="mt-6">
        <EventForm initial={ev} submitLabel="Save" onSubmit={handleSubmit} />
      </div>
    </main>
  );
}
