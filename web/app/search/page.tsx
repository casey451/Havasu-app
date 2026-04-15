"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { EventList } from "@/components/EventList";
import type { NormalizedEvent } from "@/lib/types";
import { searchEvents } from "@/lib/api";

function SearchInner() {
  const router = useRouter();
  const params = useSearchParams();
  const initialQ = params.get("q") ?? "";

  const [q, setQ] = useState(initialQ);
  const [results, setResults] = useState<NormalizedEvent[]>([]);
  const [aiHints, setAiHints] = useState<string[] | null>(null);
  const [showFallbackNotice, setShowFallbackNotice] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = useCallback(
    async (query: string) => {
      const t = query.trim();
      if (!t) {
        setResults([]);
        setAiHints(null);
        setShowFallbackNotice(false);
        setError(null);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await searchEvents(t);
        const safe = Array.isArray(data.results) ? data.results : [];
        setResults(safe);
        setShowFallbackNotice(safe[0]?.source === "fallback");
        const hints =
          data.ai && Array.isArray(data.ai.suggestions) ? data.ai.suggestions : null;
        setAiHints(hints && hints.length > 0 ? hints : null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Search failed");
        setResults([]);
        setAiHints(null);
        setShowFallbackNotice(false);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (initialQ.trim()) {
      void runSearch(initialQ);
    }
  }, [initialQ, runSearch]);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const t = q.trim();
    router.replace(t ? `/search?q=${encodeURIComponent(t)}` : "/search");
    void runSearch(t);
  }

  return (
    <div className="space-y-6">
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          type="search"
          name="q"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search events…"
          className="min-w-0 flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
        />
        <button
          type="submit"
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
        >
          Search
        </button>
      </form>

      {loading ? (
        <p className="text-sm text-zinc-500">Loading…</p>
      ) : error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : (
        <>
          <EventList
            events={results}
            emptyMessage={
              initialQ.trim()
                ? "No matching events or listings yet."
                : "Type a query and search."
            }
          />
          {showFallbackNotice ? (
            <p className="text-sm text-zinc-500">
              Nothing exact found — here are some popular options.
            </p>
          ) : null}
          {aiHints && aiHints.length > 0 ? (
            <div className="mt-8 rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-900/50">
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                Suggestions
              </p>
              <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-zinc-600 dark:text-zinc-400">
                {aiHints.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">Search</h1>
      <p className="mt-1 text-sm text-zinc-500">Title substring search; optional tips when results are sparse.</p>
      <div className="mt-6">
        <Suspense fallback={<p className="text-zinc-500">Loading…</p>}>
          <SearchInner />
        </Suspense>
      </div>
    </main>
  );
}
