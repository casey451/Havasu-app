"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { EventForm } from "@/components/EventForm";
import { createBusinessEvent } from "@/lib/api";
import type { BusinessEventInput } from "@/lib/types";
import { getStoredToken } from "@/lib/authStorage";

export default function NewEventPage() {
  const router = useRouter();
  const token = getStoredToken()!;

  async function handleSubmit(data: BusinessEventInput) {
    await createBusinessEvent(token, data);
    router.push("/dashboard");
    router.refresh();
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/dashboard" className="text-sm text-blue-600 hover:underline">
        ← Dashboard
      </Link>
      <h1 className="mt-4 text-2xl font-bold text-zinc-900 dark:text-zinc-50">Create event</h1>
      <div className="mt-6">
        <EventForm submitLabel="Create" onSubmit={handleSubmit} />
      </div>
    </main>
  );
}
