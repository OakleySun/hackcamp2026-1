import { createFileRoute, Link } from "@tanstack/react-router";
import { ApiErrorView } from "@/components/ApiErrorView";
import { fetchPulse } from "@/lib/api";

export const Route = createFileRoute("/pulse")({
  loader: fetchPulse,
  staleTime: 30_000,
  errorComponent: ApiErrorView,
  head: () => ({
    meta: [
      { title: "Campus Pulse · Quad" },
      { name: "description", content: "See how Quad finds and analyzes UBC club events." },
    ],
  }),
  component: Pulse,
});

const localTime = new Intl.DateTimeFormat("en-CA", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "America/Vancouver",
});

function Pulse() {
  const { refreshed_at, metrics, events } = Route.useLoaderData();
  const stats = metrics && [
    ["Source announcements", metrics.announcements],
    ["Upcoming events analyzed", metrics.upcoming_events],
    ["Event updates recorded", metrics.event_revisions],
    ["Venues identified by AI", metrics.venues_placed_by_ai],
    ["Possible duplicates", metrics.possible_duplicates],
  ] as const;

  return (
    <main className="mx-auto max-w-6xl px-4 pb-24 md:px-8">
      <section className="py-10">
        <h1 className="font-display text-4xl md:text-5xl">Campus Pulse</h1>
        <p className="mt-2 text-muted-foreground">See how Quad’s event sources become campus insights.</p>
        {refreshed_at && (
          <p className="mt-3 text-sm text-muted-foreground">
            Databricks last refreshed{" "}
            <time dateTime={refreshed_at}>{localTime.format(new Date(refreshed_at))}</time>
            {" Vancouver time"}
          </p>
        )}
      </section>
      {stats ? (
        <>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {stats.map(([label, value]) => (
              <div key={label} className="panel">
                <dt className="text-sm text-muted-foreground">{label}</dt>
                <dd className="mt-2 font-display text-3xl">{value}</dd>
              </div>
            ))}
          </dl>
          <section className="mt-10">
            <h2 className="font-display text-2xl">Recently analyzed events</h2>
            {events.length ? (
              <ul className="mt-4 grid gap-4 md:grid-cols-2">
                {events.map((event) => (
                  <li key={event.event_id} className="panel">
                    <Link to="/events/$id" params={{ id: event.event_id }} className="nav-link font-medium">
                      {event.title}
                    </Link>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {event.club_name} · <time dateTime={event.local_date}>{event.local_date}</time>
                    </p>
                    {event.building_name && (
                      <p className="mt-2 text-sm">
                        {event.location_method === "ai_query" ? "AI building suggestion" : "Campus building"}
                        {" · "}{event.building_name}
                      </p>
                    )}
                    <a href={event.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm underline">
                      View source
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-muted-foreground">New or updated events appear after the next analysis.</p>
            )}
          </section>
        </>
      ) : (
        <p className="panel text-muted-foreground">Campus insights will appear after the first Databricks refresh.</p>
      )}
    </main>
  );
}
