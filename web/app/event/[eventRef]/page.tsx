import Link from "next/link";

import { getPublicEvent } from "@/lib/api";
import type { PublicEventDetail } from "@/lib/types";

function formatTime(e: PublicEventDetail): string | null {
  if (!e.has_start_time) return null;
  const s = e.start_time?.trim() || "";
  if (!e.has_end_time || !e.end_time?.trim()) return s || null;
  return `${s} – ${e.end_time.trim()}`;
}

function formatLocation(e: PublicEventDetail): string {
  const vn = (e.venue_name ?? "").trim();
  const ad = (e.address ?? "").trim();
  const lb = (e.location_label ?? "").trim();
  if (vn && ad) return `${vn} · ${ad}`;
  if (vn) return vn;
  if (ad) return ad;
  return lb;
}

export default async function PublicEventPage({
  params,
}: {
  params: Promise<{ eventRef: string }>;
}) {
  const { eventRef } = await params;
  const decoded = decodeURIComponent(eventRef);

  let event: PublicEventDetail;
  try {
    event = await getPublicEvent(decoded);
  } catch {
    return (
      <main className="mx-auto max-w-2xl px-4 py-8">
        <p className="text-zinc-600 dark:text-zinc-400">Event not found.</p>
        <Link href="/" className="mt-4 inline-block text-sm text-blue-600 hover:underline">
          ← Home
        </Link>
      </main>
    );
  }

  const time = formatTime(event);
  const loc = event.has_location ? formatLocation(event) : "";
  const date =
    event.type === "event"
      ? event.date || event.start_date || ""
      : event.weekday || event.start_date || "";
  const desc = (event.description ?? "").trim();

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <Link href="/" className="text-sm text-blue-600 hover:underline">
        ← Home
      </Link>
      {event.source === "user" ? (
        <p className="mt-3">
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100">
            Local Business
          </span>
        </p>
      ) : null}
      <h1 className="mt-4 text-2xl font-bold text-zinc-900 dark:text-zinc-50">
        {event.title || "Untitled"}
      </h1>
      {date ? (
        <p className="mt-2 text-zinc-700 dark:text-zinc-300">{date}</p>
      ) : null}
      {time ? (
        <p className="mt-1 text-zinc-600 dark:text-zinc-400">{time}</p>
      ) : null}
      {loc ? (
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">{loc}</p>
      ) : null}
      {desc ? (
        <p className="mt-6 whitespace-pre-wrap text-zinc-800 dark:text-zinc-200">{desc}</p>
      ) : null}
      {event.source_url ? (
        <p className="mt-6">
          <a
            href={event.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-blue-600 hover:underline"
          >
            Source
          </a>
        </p>
      ) : null}
    </main>
  );
}
