import Link from "next/link";

import { listBusinesses } from "@/lib/api";

function shortDesc(s: string, max = 180): string {
  const t = s.trim().replace(/\s+/g, " ");
  if (t.length <= max) return t;
  return `${t.slice(0, max).trim()}…`;
}

export default async function BusinessesPage() {
  let rows;
  try {
    rows = await listBusinesses(200);
  } catch {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <p className="text-zinc-600 dark:text-zinc-400">Could not load businesses.</p>
        <Link href="/" className="mt-4 inline-block text-sm text-blue-600 hover:underline">
          ← Home
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/" className="text-sm text-blue-600 hover:underline">
        ← Home
      </Link>
      <h1 className="mt-4 text-2xl font-bold text-zinc-900 dark:text-zinc-50">Local businesses</h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        Structured listings from approved business accounts.
      </p>

      <ul className="mt-8 space-y-4">
        {rows.length === 0 ? (
          <li className="rounded-lg border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-600">
            No businesses listed yet.
          </li>
        ) : (
          rows.map((b) => (
            <li key={b.id}>
              <Link
                href={`/business/${encodeURIComponent(b.id)}`}
                className="block rounded-lg border border-zinc-200 bg-white p-4 transition hover:border-zinc-300 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-600"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">{b.name}</h2>
                  <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                    {b.category_group}
                  </span>
                </div>
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">{b.category}</p>
                <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">{shortDesc(b.description)}</p>
                {b.tags && b.tags.length > 0 ? (
                  <ul className="mt-3 flex flex-wrap gap-1.5">
                    {b.tags.map((t) => (
                      <li
                        key={t}
                        className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                      >
                        {t}
                      </li>
                    ))}
                  </ul>
                ) : null}
                <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">{b.city}</p>
              </Link>
            </li>
          ))
        )}
      </ul>
    </main>
  );
}
