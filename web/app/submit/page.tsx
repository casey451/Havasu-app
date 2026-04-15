"use client";

import { useState } from "react";

import { submitItem } from "@/lib/api";

type Category = "event" | "service";

export default function SubmitPage() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<Category>("event");
  const [tagsText, setTagsText] = useState("");
  const [startDate, setStartDate] = useState("");
  const [location, setLocation] = useState("Lake Havasu");
  const [loading, setLoading] = useState(false);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setOkMsg(null);
    setErrMsg(null);
    try {
      const tags = tagsText
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      await submitItem({
        title: title.trim(),
        description: description.trim(),
        tags,
        category,
        start_date: category === "event" ? startDate || null : null,
        location: location.trim() || "Lake Havasu",
      });
      setOkMsg("Submitted for review");
      setTitle("");
      setDescription("");
      setTagsText("");
      setStartDate("");
      setCategory("event");
      setLocation("Lake Havasu");
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">Submit</h1>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        Share an event or service. Submissions are reviewed before going live.
      </p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <label className="block">
          <span className="mb-1 block text-sm text-zinc-700 dark:text-zinc-300">Title</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-sm text-zinc-700 dark:text-zinc-300">Description</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-sm text-zinc-700 dark:text-zinc-300">Category</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as Category)}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="event">event</option>
            <option value="service">service</option>
          </select>
        </label>

        {category === "event" ? (
          <label className="block">
            <span className="mb-1 block text-sm text-zinc-700 dark:text-zinc-300">Date</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
        ) : null}

        <label className="block">
          <span className="mb-1 block text-sm text-zinc-700 dark:text-zinc-300">
            Tags (comma separated)
          </span>
          <input
            value={tagsText}
            onChange={(e) => setTagsText(e.target.value)}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-sm text-zinc-700 dark:text-zinc-300">Location</span>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          />
        </label>

        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
        >
          {loading ? "Submitting..." : "Submit for review"}
        </button>
      </form>

      {okMsg ? <p className="mt-4 text-sm text-emerald-600 dark:text-emerald-400">{okMsg}</p> : null}
      {errMsg ? <p className="mt-4 text-sm text-red-600">{errMsg}</p> : null}
    </main>
  );
}
