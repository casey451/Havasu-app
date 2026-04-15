import type { NormalizedEvent } from "@/lib/types";

import { EventCard } from "./EventCard";

export function EventList({
  events,
  emptyMessage = "Nothing to show.",
}: {
  events: NormalizedEvent[];
  emptyMessage?: string;
}) {
  if (!events.length) {
    return (
      <p className="rounded-lg border border-dashed border-zinc-300 p-6 text-center text-zinc-500 dark:border-zinc-600">
        {emptyMessage}
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-3">
      {events.map((e, i) => (
        <li key={e.event_ref ?? `${e.title}-${e.start_date}-${e.start_time}-${i}`}>
          <EventCard event={e} />
        </li>
      ))}
    </ul>
  );
}
