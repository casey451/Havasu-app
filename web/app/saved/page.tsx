"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { getSaved, removeItem, type SavedItem } from "@/lib/saved";

function useSavedItems() {
  const [saved, setSaved] = useState<SavedItem[]>([]);

  useEffect(() => {
    setSaved(getSaved());
  }, []);

  function onRemove(id: string) {
    removeItem(id);
    setSaved(getSaved());
  }

  return { saved, onRemove };
}

export default function SavedPage() {
  const { saved, onRemove } = useSavedItems();
  const hasItems = useMemo(() => saved.length > 0, [saved]);

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">Saved</h1>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        Quickly revisit events and places you marked for later.
      </p>

      {!hasItems ? (
        <p className="mt-6 rounded-lg border border-dashed border-zinc-300 p-6 text-center text-zinc-500 dark:border-zinc-600">
          No saved items yet.
        </p>
      ) : (
        <ul className="mt-6 space-y-3">
          {saved.map((item) => (
            <li
              key={item.id}
              className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-700 dark:bg-zinc-900"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">
                    {item.title || "Untitled"}
                  </h2>
                  {item.start_date ? (
                    <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{item.start_date}</p>
                  ) : null}
                  {item.location_label ? (
                    <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-500">{item.location_label}</p>
                  ) : null}
                </div>
                <div className="flex items-center gap-2">
                  {item.event_ref ? (
                    <Link
                      href={`/event/${encodeURIComponent(item.event_ref)}`}
                      className="rounded-md border border-zinc-300 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
                    >
                      Open
                    </Link>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => onRemove(item.id)}
                    className="rounded-md border border-zinc-300 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
                  >
                    Remove
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
