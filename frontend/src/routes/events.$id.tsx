import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { ArrowLeft, ArrowRight, ExternalLink } from "lucide-react";
import { ApiErrorView } from "@/components/ApiErrorView";
import { fetchEvent } from "@/lib/api";
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
      <h1 className="font-display text-3xl">We couldn't find that event</h1>
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
  const rows: [string, string][] = [
    ["When", e.timeKnown && e.end ? `${formatWhen(e)} – ${clock(e.end)}` : formatWhen(e)],
    ["Where", e.venue ?? "Not listed"],
    ["Price", e.cost === "unknown" ? "Not listed" : formatPrice(e)],
    ["Who can go", formatAudience(e) + (e.beginner ? " · Beginners welcome" : "")],
    ["Perks", e.perks.length ? e.perks.map(perkLabel).join(" · ") : "None listed"],
    ["Hosted by", e.club],
  ];
  return (
    <main className="mx-auto max-w-3xl px-4 pb-24 md:px-8">
      <Link
        to="/"
        className="mt-8 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Back to Discover
      </Link>
      <header className="mt-6">
        <div className="flex flex-wrap gap-2">
          {e.topics.map((t) => (
            <span key={t} className="status-chip" data-topic={t}>
              {topicLabel(t)}
            </span>
          ))}
        </div>
        <h1 className="mt-4 font-display text-4xl leading-tight md:text-5xl">{e.title}</h1>
        <p className="mt-3 text-lg text-muted-foreground">{e.club}</p>
      </header>

      <dl className="panel mt-8 divide-y divide-border p-0">
        {rows.map(([k, v]) => (
          <div key={k} className="grid grid-cols-3 gap-4 px-5 py-3">
            <dt className="eyebrow self-center">{k}</dt>
            <dd
              className={`col-span-2 ${v.includes("Not listed") || v.includes("None listed") || v.includes("TBD") ? "italic text-muted-foreground" : ""}`}
            >
              {v}
            </dd>
          </div>
        ))}
      </dl>

      {e.rsvpUrl && (
        <a href={e.rsvpUrl} target="_blank" rel="noreferrer" className="btn-solid mt-6">
          RSVP
          <ExternalLink className="size-4" aria-hidden />
        </a>
      )}

      {e.changes.length > 0 && (
        <section className="mt-12">
          <h2 className="font-display text-2xl">Confirmed changes</h2>
          <ul className="mt-4 space-y-3">
            {e.changes.map((c, i) => (
              <li key={i} className="panel flex flex-wrap items-center gap-3 py-4">
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

      {e.sources.length > 0 && (
        <section className="mt-12">
          <h2 className="font-display text-2xl">Where we found this</h2>
          <ul className="mt-4 space-y-2">
            {e.sources.map((s) => (
              <li key={s.url}>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 underline underline-offset-4 hover:text-primary"
                >
                  {s.label}
                  <ExternalLink className="size-3.5" aria-hidden />
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
