import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Download, ExternalLink, MapPin, X } from "lucide-react";
import { ApiErrorView } from "@/components/ApiErrorView";
import { formatTime } from "@/components/EventCard";
import { Timeline } from "@/components/Timeline";
import { fetchEvents } from "@/lib/api";
import { downloadIcs, googleCalendarUrl, groupByDay, icsFilename } from "@/lib/calendar";
import { vancouverToday, type CampusEvent } from "@/lib/events";
import { useLocalSet } from "@/lib/useLocalSet";

export const Route = createFileRoute("/calendar")({
  loader: () => fetchEvents(),
  staleTime: 30_000,
  errorComponent: ApiErrorView,
  head: () => ({
    meta: [
      { title: "Your calendar · Quad" },
      {
        name: "description",
        content: "Events you've added on Quad, ready to sync to Google or Apple Calendar.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: CalendarPage,
});

const WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

/** Month grid cells for YYYY-MM: leading blanks, then each day as YYYY-MM-DD. */
function monthCells(month: string): (string | null)[] {
  const [y = 2026, m = 1] = month.split("-").map(Number);
  const first = new Date(Date.UTC(y, m - 1, 1));
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const cells: (string | null)[] = Array.from({ length: first.getUTCDay() }, () => null);
  for (let d = 1; d <= days; d++) cells.push(`${month}-${String(d).padStart(2, "0")}`);
  return cells;
}
const shiftMonth = (month: string, n: number) => {
  const [y = 2026, m = 1] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + n, 1));
  return d.toISOString().slice(0, 7);
};
const monthTitle = (month: string) =>
  new Date(`${month}-15T12:00:00Z`).toLocaleDateString("en-CA", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });

function CalendarPage() {
  const events = Route.useLoaderData();
  const [saved, toggleSaved] = useLocalSet("quad:saved");
  const today = vancouverToday();
  const [month, setMonth] = useState(today.slice(0, 7));
  const [day, setDay] = useState<string | null>(null);

  const mine = useMemo(() => events.filter((e) => saved.has(e.id)), [events, saved]);
  const upcoming = mine.filter((e) => !e.date || e.date >= today);
  const past = mine.filter((e) => e.date && e.date < today);
  const busy = new Set(mine.map((e) => e.date).filter(Boolean));
  const shown = day ? upcoming.filter((e) => e.date === day) : upcoming;
  const groups = groupByDay(shown);

  const remove = (e: CampusEvent) => {
    toggleSaved(e.id);
    toast("Removed from your calendar", {
      description: e.title,
      action: { label: "Undo", onClick: () => toggleSaved(e.id) },
    });
  };

  const row = (e: CampusEvent) => {
    const google = googleCalendarUrl(
      e,
      typeof window === "undefined" ? "" : window.location.origin,
    );
    return (
      <article className="event-card p-4">
        <p className="text-sm font-medium text-muted-foreground">{formatTime(e)}</p>
        <h3 className="mt-1 text-lg leading-snug">
          <Link to="/events/$id" params={{ id: e.id }} className="hover:underline">
            {e.title}
          </Link>
        </h3>
        <p className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
          <span>By {e.club}</span>
          <span aria-hidden>·</span>
          <span className="inline-flex items-center gap-1">
            <MapPin className="size-3.5" aria-hidden />
            {e.venue ?? "Venue not listed"}
          </span>
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {google && (
            <a href={google} target="_blank" rel="noreferrer" className="btn-ghost">
              Google Calendar
              <ExternalLink className="size-3.5" aria-hidden />
            </a>
          )}
          {e.date && (
            <button
              type="button"
              className="btn-ghost"
              onClick={() => downloadIcs(icsFilename(e.title), [e])}
            >
              <Download className="size-4" aria-hidden />
              Apple / Outlook (.ics)
            </button>
          )}
          <button type="button" className="btn-quiet ml-auto" onClick={() => remove(e)}>
            <X className="size-4" aria-hidden />
            Remove
          </button>
        </div>
      </article>
    );
  };

  return (
    <main className="mx-auto max-w-4xl px-4 pb-24 md:px-6">
      <section className="flex flex-wrap items-end justify-between gap-4 py-10">
        <div>
          <h1 className="text-3xl md:text-4xl">Your calendar</h1>
          <p className="mt-2 text-muted-foreground">
            Events you've added on Quad. Send them to Google, Apple or Outlook from here.
          </p>
        </div>
        {upcoming.some((e) => e.date) && (
          <button
            type="button"
            className="btn-solid"
            onClick={() => downloadIcs("quad-calendar.ics", upcoming)}
          >
            <Download className="size-4" aria-hidden />
            Export all (.ics)
          </button>
        )}
      </section>

      {mine.length === 0 ? (
        <div className="panel py-12 text-center">
          <h2 className="text-2xl">Nothing in your calendar yet</h2>
          <p className="mx-auto mt-2 max-w-md text-muted-foreground">
            Press <strong>Add to calendar</strong> on any event and it will show up here, ready to
            sync to the calendar you already use.
          </p>
          <Link to="/" className="btn-solid mt-6">
            Browse events
          </Link>
        </div>
      ) : (
        <div className="grid gap-8 md:grid-cols-[17rem_minmax(0,1fr)]">
          <aside className="panel self-start p-4 md:sticky md:top-20 md:p-4">
            <div className="flex items-center justify-between">
              <button
                type="button"
                className="btn-quiet"
                aria-label="Previous month"
                onClick={() => setMonth(shiftMonth(month, -1))}
              >
                <ChevronLeft className="size-4" aria-hidden />
              </button>
              <p className="font-semibold">{monthTitle(month)}</p>
              <button
                type="button"
                className="btn-quiet"
                aria-label="Next month"
                onClick={() => setMonth(shiftMonth(month, 1))}
              >
                <ChevronRight className="size-4" aria-hidden />
              </button>
            </div>
            <div className="mt-3 grid grid-cols-7 gap-y-1 text-center text-xs text-muted-foreground">
              {WEEKDAYS.map((w) => (
                <span key={w}>{w}</span>
              ))}
            </div>
            <div className="mt-1 grid grid-cols-7 gap-y-1 text-center text-sm">
              {monthCells(month).map((d, i) =>
                d ? (
                  <button
                    key={d}
                    type="button"
                    className="relative mx-auto flex size-9 items-center justify-center rounded-full data-[on=true]:bg-primary data-[on=true]:text-primary-foreground data-[today=true]:ring-2 data-[today=true]:ring-gold disabled:text-muted-foreground/60 hover:not-disabled:bg-muted"
                    data-on={day === d}
                    data-today={d === today}
                    disabled={!busy.has(d)}
                    aria-pressed={day === d}
                    aria-label={`${d}${busy.has(d) ? ", has events" : ""}`}
                    onClick={() => setDay(day === d ? null : d)}
                  >
                    {Number(d.slice(-2))}
                    {busy.has(d) && (
                      <span
                        className="absolute bottom-1 size-1 rounded-full bg-current"
                        aria-hidden
                      />
                    )}
                  </button>
                ) : (
                  <span key={`blank-${i}`} />
                ),
              )}
            </div>
            {day && (
              <button
                type="button"
                className="btn-quiet mt-3 w-full justify-center"
                onClick={() => setDay(null)}
              >
                Show all upcoming
              </button>
            )}
          </aside>

          <div>
            {groups.length ? (
              <Timeline groups={groups} renderEvent={row} today={today} />
            ) : (
              <div className="panel text-center">
                <p className="text-muted-foreground">
                  {day ? "Nothing on this day." : "No upcoming events in your calendar."}
                </p>
              </div>
            )}
            {past.length > 0 && !day && (
              <section className="mt-12">
                <h2 className="mb-4 text-xl text-muted-foreground">Past</h2>
                <ul className="divide-y divide-border rounded-2xl border border-border">
                  {past
                    .sort((a, b) => b.start.localeCompare(a.start))
                    .map((e) => (
                      <li
                        key={e.id}
                        className="flex flex-wrap items-center gap-2 px-4 py-3 text-sm"
                      >
                        <span className="text-muted-foreground">{e.date}</span>
                        <Link
                          to="/events/$id"
                          params={{ id: e.id }}
                          className="font-medium hover:underline"
                        >
                          {e.title}
                        </Link>
                        <button
                          type="button"
                          className="btn-quiet ml-auto"
                          onClick={() => remove(e)}
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                </ul>
              </section>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
