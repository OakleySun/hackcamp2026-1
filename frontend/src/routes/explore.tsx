import { createFileRoute, redirect } from "@tanstack/react-router";
import { validateFilterSearch } from "@/lib/filters";

// Discover and Explore were the same timeline with different filters; Explore now lives at "/".
// Keep the old address working for shared links, carrying any filters across.
export const Route = createFileRoute("/explore")({
  validateSearch: validateFilterSearch,
  beforeLoad: ({ search }) => {
    throw redirect({ to: "/", search, replace: true });
  },
});
