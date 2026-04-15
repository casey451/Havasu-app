import Link from "next/link";

import { getBusinessProfile } from "@/lib/api";

export default async function BusinessProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const decoded = decodeURIComponent(id);

  let profile;
  try {
    profile = await getBusinessProfile(decoded);
  } catch {
    return (
      <main className="mx-auto max-w-2xl px-4 py-8">
        <p className="text-zinc-600 dark:text-zinc-400">Business not found.</p>
        <Link href="/" className="mt-4 inline-block text-sm text-blue-600 hover:underline">
          ← Home
        </Link>
      </main>
    );
  }

  const tags = profile.tags?.length ? profile.tags : [];

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <Link href="/" className="text-sm text-blue-600 hover:underline">
        ← Home
      </Link>
      <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">{profile.category_group}</p>
      <h1 className="mt-2 text-2xl font-bold text-zinc-900 dark:text-zinc-50">{profile.name}</h1>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
        <span className="font-medium">{profile.category}</span>
        {profile.city ? ` · ${profile.city}` : null}
      </p>
      {tags.length > 0 ? (
        <ul className="mt-4 flex flex-wrap gap-2">
          {tags.map((t) => (
            <li
              key={t}
              className="rounded-full bg-zinc-200 px-2.5 py-0.5 text-xs text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200"
            >
              {t}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="mt-6 whitespace-pre-wrap text-zinc-800 dark:text-zinc-200">
        {profile.description}
      </p>
      {(profile.phone || profile.website || profile.address) && (
        <dl className="mt-6 space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
          {profile.phone ? (
            <div>
              <dt className="font-medium text-zinc-500 dark:text-zinc-400">Phone</dt>
              <dd>{profile.phone}</dd>
            </div>
          ) : null}
          {profile.website ? (
            <div>
              <dt className="font-medium text-zinc-500 dark:text-zinc-400">Website</dt>
              <dd>
                <a
                  href={profile.website.startsWith("http") ? profile.website : `https://${profile.website}`}
                  className="text-blue-600 hover:underline"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {profile.website}
                </a>
              </dd>
            </div>
          ) : null}
          {profile.address ? (
            <div>
              <dt className="font-medium text-zinc-500 dark:text-zinc-400">Address</dt>
              <dd>{profile.address}</dd>
            </div>
          ) : null}
        </dl>
      )}

      <section className="mt-10">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Upcoming events</h2>
        {profile.upcoming_events.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">No upcoming listings yet.</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {profile.upcoming_events.map((e) => (
              <li key={e.id}>
                <Link
                  href={`/event/u-${e.id}`}
                  className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                >
                  {e.title}
                </Link>
                <p className="text-sm text-zinc-600 dark:text-zinc-400">
                  {e.start_date}
                  {e.start_time ? ` · ${e.start_time}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
