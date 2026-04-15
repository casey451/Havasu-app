"use client";

import { useEffect } from "react";

import { pollNotificationsFeed, requestNotificationPermissionOnce } from "@/lib/notifications";

const POLL_MS = 90_000;

export function NotificationPoller() {
  useEffect(() => {
    requestNotificationPermissionOnce();
    void pollNotificationsFeed();
    const t = window.setInterval(() => {
      void pollNotificationsFeed();
    }, POLL_MS);
    return () => window.clearInterval(t);
  }, []);

  return null;
}
