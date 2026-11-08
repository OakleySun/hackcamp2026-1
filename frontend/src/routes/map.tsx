import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, MapPin } from "lucide-react";
import { ApiErrorView } from "@/components/ApiErrorView";
import { CampusMap } from "@/components/CampusMap";
import { fetchEvents } from "@/lib/api";
import {
  addDays,
  eventsOn,
  formatDay,
  formatWhen,
  groupByPlace,
  nextDayWithEvents,
  prevDayWithEvents,
  topicLabel,
  vancouverToday,
} from "@/lib/events";

type MapSearch = { day?: string | undefined };

export const Route = createFileRoute("/map")({
  validateSearch: (s: Record<string, unknown>): MapSearch => ({
    day:
      typeof s["day"] === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s["day"]) ? s["day"] : undefined,
  }),
  loader: () => fetchEvents(),
  staleTime: 30_000,
  errorComponent: ApiErrorView,
  head: () => ({
    meta: [
      { title: "Campus map · Quad" },
      {
        name: "description",
        content: "See where today's UBC club events are happening on a campus map.",
      },
      { property: "og:title", content: "Campus map · Quad" },
      { property: "og:description", content: "Today's UBC club events on a campus map." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: MapPage,
});

const time = (iso: string, known: boolean) =>
  known
    ? new Date(iso).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" })
    : "Time TBD";

function MapPage() {
  const events = Route.useLoaderData();
  const search = Route.useSearch();
  const navigate = useNavigate({ from: "/map" });
  const today = vancouverToday();
  const day = search.day && search.day >= today ? search.day : today;
  const [selected, setSelected] = useState<string | null>(null);

  const dayEvents = useMemo(() => eventsOn(events, day), [events, day]);
  const { pins, unplaced } = useMemo(() => groupByPlace(dayEvents), [dayEvents]);
  const next = nextDayWithEvents(events, day);
  const prev = prevDayWithEvents(events, day, today);

  const go = (d: string) => {
    setSelected(null);
    void navigate({ search: { day: d === today ? undefined : d }, replace: true });
  };
  const label = day === today ? "Today" : day === addDays(today, 1) ? "Tomorrow" : formatDay(day);

  return (
    <main className="mx-auto max-w-6xl px-4 pb-24 md:px-8">
      <section className="py-10">
        <h1 className="font-display text-4xl md:text-5xl">Campus map</h1>
        <p className="mt-2 text-muted-foreground">
          Where things are happening on campus, one day at a time.
        </p>
      </section>

      <div className="panel mb-5 flex flex-wrap items-center gap-3 py-3 md:py-3">
        <button
          type="button"
          className="btn-ghost"
          onClick={() => go(addDays(day, -1))}
          disabled={day <= today}
          aria-label="Previous day"
        >
          <ChevronLeft className="size-4" aria-hidden />
        </button>
        <div className="min-w-0">
          <p className="font-display text-xl leading-tight">{label}</p>
          {label !== formatDay(day) && (
            <p className="text-sm text-muted-foreground">{formatDay(day)}</p>
          )}
        </div>
        <button
          type="button"
          className="btn-ghost"
          onClick={() => go(addDays(day, 1))}
          aria-label="Next day"
        >
          <ChevronRight className="size-4" aria-hidden />
        </button>
        <label className="ml-auto flex items-center gap-2 text-sm">
          <span className="eyebrow">Date</span>
          <input
            type="date"
            className="field w-auto py-1.5"
            value={day}
            min={today}
            onChange={(e) => e.target.value && go(e.target.value)}
          />
        </label>
        {day !== today && (
          <button type="button" className="btn-ghost" onClick={() => go(today)}>
            Today
          </button>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="relative">
          <CampusMap
            pins={pins}
            selected={selected}
            onSelect={setSelected}
            onOpenEvent={(id) => void navigate({ to: "/events/$id", params: { id } })}
          />
          {dayEvents.length === 0 && (
            <div className="pointer-events-none absolute inset-x-4 top-4 z-[500] flex justify-center">
              <div className="panel pointer-events-auto max-w-sm py-4 text-center">
                <p className="font-display text-lg">
                  Nothing on{" "}
                  {label === "Today" || label === "Tomorrow" ? label.toLowerCase() : "this day"}.
                </p>
                {next ? (
                  <button type="button" className="btn-solid mt-3" onClick={() => go(next)}>
                    Jump to {formatDay(next)}
                    <ChevronRight className="size-4" aria-hidden />
                  </button>
                ) : (
                  <p className="mt-1 text-sm text-muted-foreground">No upcoming events yet.</p>
                )}
              </div>
            </div>
          )}
        </div>

        <aside aria-label={`Events on ${formatDay(day)}`} className="space-y-3">
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {dayEvents.length} event{dayEvents.length === 1 ? "" : "s"}
            {pins.length > 0 && ` in ${pins.length} building${pins.length === 1 ? "" : "s"}`}
          </p>

          {pins.map((g) => (
            <section
              key={g.place.id}
              className="panel map-row cursor-pointer p-4 md:p-4"
              data-on={selected === g.place.id}
              onClick={() => setSelected(g.place.id)}
            >
              <h2 className="flex items-center gap-2 font-display text-lg">
                <MapPin className="size-4 shrink-0 text-primary" aria-hidden />
                <button
                  type="button"
                  className="text-left hover:underline"
                  onClick={() => setSelected(g.place.id)}
                >
                  {g.place.name}
                </button>
              </h2>
              <ul className="mt-2 space-y-2">
                {g.events.map((e) => (
                  <li key={e.id} className="text-sm">
                    <Link
                      to="/events/$id"
                      params={{ id: e.id }}
                      className="font-semibold hover:underline"
                      onClick={(ev) => ev.stopPropagation()}
                    >
                      {e.title}
                    </Link>
                    <p className="text-muted-foreground">
                      {time(e.start, e.timeKnown)} · {e.venue} · {topicLabel(e.topic)}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          ))}

          {unplaced.length > 0 && (
            <section className="panel p-4 md:p-4">
              <h2 className="font-display text-lg">Not on the map</h2>
              <p className="text-xs text-muted-foreground">
                We couldn't place these venues on campus.
              </p>
              <ul className="mt-2 space-y-2">
                {unplaced.map((e) => (
                  <li key={e.id} className="text-sm">
                    <Link
                      to="/events/$id"
                      params={{ id: e.id }}
                      className="font-semibold hover:underline"
                    >
                      {e.title}
                    </Link>
                    <p className="text-muted-foreground">
                      {formatWhen(e).split(" · ")[1]} · {e.venue ?? "Venue not listed"}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {dayEvents.length > 0 && (prev || next) && (
            <div className="flex flex-wrap gap-2 pt-1 text-sm">
              {prev && (
                <button type="button" className="underline" onClick={() => go(prev)}>
                  ← {formatDay(prev)}
                </button>
              )}
              {next && (
                <button type="button" className="ml-auto underline" onClick={() => go(next)}>
                  Next events: {formatDay(next)} →
                </button>
              )}
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}
