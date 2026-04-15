import { EventList } from "@/components/EventList";
import { getDiscover } from "@/lib/api";

export default async function HomePage() {
  let discoverData;
  let err: string | null = null;
  try {
    discoverData = await getDiscover();
  } catch (e) {
    err = e instanceof Error ? e.message : "Could not load calendar";
    discoverData = { today: [], weekend: [], popular: [] };
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">What&apos;s on in Havasu</h1>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        Live discovery feed for today, this weekend, and popular picks.
      </p>

      {err ? (
        <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {err}
          <span className="mt-2 block text-zinc-600 dark:text-zinc-400">
            Is the API running? Use{" "}
            <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">uvicorn api.main:app</code> and
            check <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">web/next.config.ts</code>{" "}
            rewrites.
          </span>
        </p>
      ) : null}

      <section className="mt-10">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Happening Today</h2>
        <EventList events={discoverData.today} emptyMessage="Nothing scheduled today." />
      </section>

      <section className="mt-12 border-t border-zinc-200 pt-10 dark:border-zinc-800">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">This Weekend</h2>
        <EventList events={discoverData.weekend} emptyMessage="Nothing scheduled this weekend." />
      </section>

      <section className="mt-12 border-t border-zinc-200 pt-10 dark:border-zinc-800">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          Popular Around Havasu
        </h2>
        <EventList events={discoverData.popular} emptyMessage="Popular picks are loading soon." />
      </section>
    </main>
  );
}
