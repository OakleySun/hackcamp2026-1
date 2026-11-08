import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { ArrowLeft, ArrowRight, Download, ExternalLink, MapPin } from "lucide-react";
import { ClubAvatar, DateLeaf } from "@/components/Bits";
import { ApiErrorView } from "@/components/ApiErrorView";
import { CalendarButton } from "@/components/EventCard";
import { fetchEvent } from "@/lib/api";
import { downloadIcs, googleCalendarUrl, icsFilename } from "@/lib/calendar";
import { useLocalSet } from "@/lib/useLocalSet";
import {
  formatAudience,
  formatPrice,
  formatStamp,
  formatWhen,
  perkLabel,
  topicLabel,
} from "@/lib/events";

export const Route = createFileRoute("/events/$id")({
  loader: async ({ params }) => {
    const event = await fetchEvent(params.id);
    if (!event) throw notFound();
    return { event };
  },
  errorComponent: ApiErrorView,
  head: ({ loaderData }) => {
    const t = loaderData ? `${loaderData.event.title} · Quad` : "Event not found · Quad";
    const d = loaderData
      ? `${loaderData.event.club} — ${formatWhen(loaderData.event)}, ${loaderData.event.venue ?? "venue TBD"}`
      : "This event could not be found.";
    return {
      meta: [
        { title: t },
        { name: "description", content: d },
        { property: "og:title", content: t },
        { property: "og:description", content: d },
        { property: "og:type", content: "article" },
        { name: "twitter:card", content: "summary" },
        ...(loaderData ? [] : [{ name: "robots", content: "noindex" }]),
      ],
    };
  },
  notFoundComponent: () => (
    <main className="mx-auto max-w-3xl px-4 py-20 text-center">
      <h1 className="text-3xl">We couldn't find that event</h1>
      <Link to="/" className="btn-solid mt-6">
        Back to Discover
      </Link>
    </main>
  ),
  component: EventPage,
});

const clock = (hhmm: string) => {
  const [h = 0, m = 0] = hhmm.split(":").map(Number);
  return new Date(2000, 0, 1, h, m).toLocaleTimeString("en-CA", {
    hour: "numeric",
    minute: "2-digit",
  });
};

function EventPage() {
  const { event: e } = Route.useLoaderData();
  const [saved, toggleSaved] = useLocalSet("quad:saved");
  const google = googleCalendarUrl(e, typeof window === "undefined" ? "" : window.location.origin);
  const inCalendar = saved.has(e.id);
  const dateLong = e.date
    ? new Date(`${e.date}T12:00:00Z`).toLocaleDateString("en-CA", {
        weekday: "long",
        month: "long",
        day: "numeric",
        timeZone: "UTC",
      })
    : "Date to be announced";
  const timeLine = !e.date
    ? null
    : !e.timeKnown
      ? "Time to be announced"
      : `${clock(e.start.split("T")[1] ?? "00:00")}${e.end ? ` – ${clock(e.end)}` : ""} PT`;
  const details: [string, string][] = [
    ["Price", e.cost === "unknown" ? "Not listed" : formatPrice(e)],
    ["Who can go", formatAudience(e) + (e.beginner ? " · Beginners welcome" : "")],
    ["Perks", e.perks.length ? e.perks.map(perkLabel).join(" · ") : "None listed"],
  ];
  const missing = (v: string) => /Not listed|None listed|TBD/.test(v);

  return (
    <main className="mx-auto max-w-5xl px-4 pb-24 md:px-8">
      <Link
        to="/"
        className="mt-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Back to Discover
      </Link>

      <div className="mt-6 grid gap-8 md:grid-cols-[18rem_minmax(0,1fr)] md:gap-12">
        <aside className="space-y-6 md:sticky md:top-24 md:self-start">
          <div className="poster-tile">
            <div className="flex flex-wrap gap-1.5">
              {e.topics.map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-white/15 px-2.5 py-0.5 text-xs font-medium text-white"
                >
                  {topicLabel(t)}
                </span>
              ))}
            </div>
            <DateLeaf day={e.date} size="lg" />
          </div>

          <section className="glass rounded-2xl p-4">
            <h2 className="eyebrow">Hosted by</h2>
            <p className="mt-2 flex items-center gap-3 font-medium">
              <ClubAvatar name={e.club} size="lg" />
              {e.club}
            </p>
          </section>

          {e.sources.length > 0 && (
            <section className="glass rounded-2xl p-4">
              <h2 className="eyebrow">Where we found this</h2>
              <ul className="mt-2 space-y-1.5 text-sm">
                {e.sources.map((s) => (
                  <li key={s.url}>
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-link underline underline-offset-4"
                    >
                      {s.label}
                      <ExternalLink className="size-3.5" aria-hidden />
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>

        <article>
          <header>
            <h1 className="text-3xl leading-tight md:text-5xl">{e.title}</h1>
            {e.changes.length > 0 && (
              <p className="mt-3">
                <span className="status-chip" data-kind="updated">
                  Updated · see confirmed changes below
                </span>
              </p>
            )}
          </header>

          <ul className="mt-6 space-y-4">
            <li className="flex items-center gap-4">
              <DateLeaf day={e.date} />
              <div>
                <p className="font-medium">{dateLong}</p>
                {timeLine && <p className="text-sm text-muted-foreground">{timeLine}</p>}
              </div>
            </li>
            <li className="flex items-center gap-4">
              <span className="icon-box">
                <MapPin className="size-5" aria-hidden />
              </span>
              <div>
                <p className={`font-medium ${e.venue ? "" : "italic text-muted-foreground"}`}>
                  {e.venue ?? "Venue not listed"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {e.place ? (
                    <Link
                      to="/map"
                      search={{ day: e.date ?? undefined }}
                      className="text-link underline underline-offset-4"
                    >
                      {e.place.name} · see on the campus map
                    </Link>
                  ) : (
                    "UBC Vancouver"
                  )}
                </p>
              </div>
            </li>
          </ul>

          <section className="glass mt-8 rounded-2xl p-5" aria-labelledby="calendar-h">
            <h2 id="calendar-h" className="eyebrow">
              Your calendar
            </h2>
            <p className="mt-1 text-sm">
              {inCalendar
                ? "This event is in your Quad calendar."
                : "Add this event so it shows up in your Quad calendar."}
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <CalendarButton event={e} saved={inCalendar} onToggle={() => toggleSaved(e.id)} />
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
                  .ics
                </button>
              )}
            </div>
            {e.rsvpUrl && (
              <p className="mt-4 text-sm text-muted-foreground">
                Spots are handled by the organizer:{" "}
                <a
                  href={e.rsvpUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-link underline underline-offset-4"
                >
                  RSVP with {e.club}
                </a>
                .
              </p>
            )}
          </section>

          <section className="mt-8">
            <h2 className="text-xl">Details</h2>
            <dl className="glass mt-3 divide-y divide-border rounded-2xl">
              {details.map(([k, v]) => (
                <div key={k} className="grid grid-cols-3 gap-4 px-5 py-3">
                  <dt className="eyebrow self-center">{k}</dt>
                  <dd className={`col-span-2 ${missing(v) ? "italic text-muted-foreground" : ""}`}>
                    {v}
                  </dd>
                </div>
              ))}
            </dl>
          </section>

          {e.changes.length > 0 && (
            <section className="mt-8">
              <h2 className="text-xl">Confirmed changes</h2>
              <ul className="mt-3 space-y-3">
                {e.changes.map((c, i) => (
                  <li key={i} className="glass flex flex-wrap items-center gap-3 rounded-2xl p-4">
                    <span className="status-chip" data-kind="updated">
                      {c.field} changed
                    </span>
                    <span className="text-muted-foreground line-through">{c.from}</span>
                    <ArrowRight className="size-4" aria-label="changed to" />
                    <span className="font-semibold">{c.to}</span>
                    <span className="ml-auto text-sm text-muted-foreground">
                      Confirmed {formatStamp(c.confirmedAt)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </article>
      </div>
    </main>
  );
}
