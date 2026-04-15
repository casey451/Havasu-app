"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { getMe, getMyBusinessProfile, saveMyBusinessProfile } from "@/lib/api";
import { getStoredToken, getStoredUser } from "@/lib/authStorage";
import type { BusinessProfile, BusinessProfileInput } from "@/lib/types";

const empty: BusinessProfileInput = {
  name: "",
  description: "",
  category: "",
  phone: "",
  website: "",
  address: "",
  city: "Lake Havasu",
  is_active: true,
};

function toForm(p: BusinessProfile | null): BusinessProfileInput {
  if (!p) return { ...empty };
  return {
    name: p.name,
    description: p.description,
    category: p.category,
    phone: p.phone ?? "",
    website: p.website ?? "",
    address: p.address ?? "",
    city: p.city || "Lake Havasu",
    is_active: p.is_active,
  };
}

export default function DashboardProfilePage() {
  const token = getStoredToken()!;
  const [user, setUser] = useState(getStoredUser());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<BusinessProfileInput>(empty);
  const [hasProfile, setHasProfile] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    setSuccess(null);
    try {
      const me = await getMe(token);
      setUser(me);
      if (me.role !== "business" || me.status !== "approved") {
        setLoading(false);
        return;
      }
      const p = await getMyBusinessProfile(token);
      setHasProfile(p !== null);
      setForm(toForm(p));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setSuccess(null);
    const name = form.name.trim();
    const description = form.description.trim();
    const category = form.category.trim();
    if (!name || !description || !category) {
      setErr("Name, description, and category are required.");
      return;
    }
    setSaving(true);
    try {
      const payload: BusinessProfileInput = {
        name,
        description,
        category,
        phone: (form.phone ?? "").trim() || null,
        website: (form.website ?? "").trim() || null,
        address: (form.address ?? "").trim() || null,
        city: (form.city ?? "").trim() || "Lake Havasu",
        is_active: form.is_active,
      };
      await saveMyBusinessProfile(token, payload);
      setSuccess(hasProfile ? "Profile saved." : "Profile created.");
      setHasProfile(true);
      const refreshed = await getMyBusinessProfile(token);
      if (refreshed) setForm(toForm(refreshed));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8 text-sm text-zinc-500">Loading…</main>
    );
  }

  if (user?.role !== "business" || user.status !== "approved") {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <Link href="/dashboard" className="text-sm text-blue-600 hover:underline">
          ← Dashboard
        </Link>
        <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">
          Business profile is only available for approved business accounts.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/dashboard" className="text-sm text-blue-600 hover:underline">
        ← Dashboard
      </Link>
      <h1 className="mt-4 text-2xl font-bold text-zinc-900 dark:text-zinc-50">
        {hasProfile ? "Edit business profile" : "Create business profile"}
      </h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        Tags are updated automatically from your name and description. Category is mapped into a
        public group (Home Services, Food & Drink, etc.).
      </p>

      {success ? (
        <p className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">
          {success}
        </p>
      ) : null}
      {err ? (
        <p className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          {err}
        </p>
      ) : null}

      <form onSubmit={(e) => void onSubmit(e)} className="mt-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Business name
          </label>
          <input
            className="mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            required
            maxLength={200}
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Description
          </label>
          <textarea
            className="mt-1 min-h-[120px] w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            required
            maxLength={8000}
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Category
          </label>
          <input
            className="mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
            placeholder="e.g. HVAC, breakfast, yoga"
            value={form.category}
            onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
            required
            maxLength={200}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Phone
            </label>
            <input
              className="mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
              value={form.phone ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
              maxLength={40}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Website
            </label>
            <input
              className="mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
              value={form.website ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, website: e.target.value }))}
              maxLength={500}
            />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Address
          </label>
          <input
            className="mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
            value={form.address ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
            maxLength={500}
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">City</label>
          <input
            className="mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
            value={form.city ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}
            maxLength={200}
          />
        </div>
        <div className="flex items-center gap-2">
          <input
            id="is_active"
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
          />
          <label htmlFor="is_active" className="text-sm text-zinc-700 dark:text-zinc-300">
            List my business publicly
          </label>
        </div>
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {saving ? "Saving…" : hasProfile ? "Save profile" : "Create profile"}
        </button>
      </form>
    </main>
  );
}
