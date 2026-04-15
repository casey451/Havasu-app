"use client";

import { FormEvent, useState } from "react";

import { submitActivity } from "@/lib/api";

function toApiDate(input: string): string {
  if (!input) return "";
  return input.slice(0, 10);
}

export default function SubmitPage() {
  const [title, setTitle] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [location, setLocation] = useState("Lake Havasu");
  const [category, setCategory] = useState("events");
  const [tags, setTags] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setStatus(null);
    setError(null);
    try {
      const result = await submitActivity({
        title: title.trim(),
        location: location.trim(),
        category,
        tags: tags
          .split(",")
          .map((t) => t.trim().toLowerCase())
          .filter(Boolean),
        description: description.trim(),
        time_slots: [
          {
            start_time: `${toApiDate(startDate)}T${startDate.slice(11, 16)}:00`.slice(11),
            end_time: `${toApiDate(endDate || startDate)}T${(endDate || startDate).slice(11, 16)}:00`.slice(11),
            date: toApiDate(startDate),
            recurring: false,
          },
        ],
      });
      setStatus(result.duplicate ? "Duplicate submission already exists." : "Event submitted successfully");
      setTitle("");
      setStartDate("");
      setEndDate("");
      setTags("");
      setDescription("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submit failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-xl px-4 py-8">
      <h1 className="text-2xl font-semibold">Submit Activity</h1>
      <p className="mt-1 text-sm text-zinc-600">Share a class, schedule, or event happening in Lake Havasu.</p>
      <form onSubmit={onSubmit} className="mt-6 space-y-5 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Title</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500"
            required
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Start date/time</span>
          <input
            type="datetime-local"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500"
            required
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">End date/time</span>
          <input
            type="datetime-local"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500"
            required
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Location</span>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500"
            required
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Category</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500"
          >
            <option value="events">Events</option>
            <option value="kids">Kids</option>
            <option value="fitness">Fitness</option>
            <option value="nightlife">Nightlife</option>
          </select>
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Tags (comma separated)</span>
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="kids, family, water"
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500"
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Description</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Submitting..." : "Submit"}
        </button>
      </form>
      {status ? <p className="mt-4 text-sm text-green-700">{status}</p> : null}
      {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}
    </main>
  );
}
