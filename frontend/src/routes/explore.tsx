import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { EventCard } from "@/components/EventCard";
import { ApiErrorView } from "@/components/ApiErrorView";
import { FilterControls } from "@/components/FilterControls";
import { fetchEvents } from "@/lib/api";
import { hasAny, hasPerks, upcoming } from "@/lib/events";
import { parseFilters, validateFilterSearch } from "@/lib/filters";
import { useLocalSet } from "@/lib/useLocalSet";

export const Route = createFileRoute("/explore")({
  validateSearch: validateFilterSearch,
  loader: () => fetchEvents(),
  staleTime: 30_000,
  errorComponent: ApiErrorView,
  head: () => ({
    meta: [
      { title: "Explore all events · Quad" },
      {
        name: "description",
        content:
          "Browse every upcoming UBC club event by topic and perks like free food, swag and prizes.",
      },
      { property: "og:title", content: "Explore all events · Quad" },
      { property: "og:description", content: "Filter every upcoming UBC club event." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Explore,
});

function Explore() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: "/explore" });
  const { topics, perks } = parseFilters(search);
  const [saved, toggleSaved] = useLocalSet("quad:saved");
  const [hidden, toggleHidden] = useLocalSet("quad:hidden");
  const events = Route.useLoaderData();
  const results = upcoming(
    events.filter(
      (e) => !hidden.has(e.id) && (!topics.length || hasAny(e, topics)) && hasPerks(e, perks),
    ),
    [],
  );

  return (
    <main className="mx-auto max-w-6xl px-4 pb-24 md:px-8">
      <section className="py-10">
        <h1 className="font-display text-4xl md:text-5xl">Explore</h1>
        <p className="mt-2 text-muted-foreground">Every upcoming event, in date order.</p>
      </section>
      <section aria-label="Filters" className="panel">
        <FilterControls
          search={search}
          group="perks"
          onChange={(s) => navigate({ search: s, replace: true })}
        />
      </section>
      <p className="mt-8 mb-4 text-sm text-muted-foreground" aria-live="polite">
        {results.length} event{results.length === 1 ? "" : "s"}
      </p>
      {results.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {results.map((r) => (
            <EventCard
              key={r.event.id}
              item={r}
              saved={saved.has(r.event.id)}
              onSave={() => toggleSaved(r.event.id)}
              onHide={() => toggleHidden(r.event.id)}
            />
          ))}
        </div>
      ) : (
        <div className="panel text-center">
          <h2 className="font-display text-2xl">Nothing matches those filters</h2>
          <button type="button" className="btn-solid mt-5" onClick={() => navigate({ search: {} })}>
            Clear filters
          </button>
        </div>
      )}
    </main>
  );
}
