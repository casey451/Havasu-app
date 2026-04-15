import { redirect } from "next/navigation";

/** Old JSON-in-query URLs — bookmarks still land somewhere useful. */
export default function LegacyEventDetailRedirect() {
  redirect("/");
}
