import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Check } from "lucide-react";
import { ApiErrorView } from "@/components/ApiErrorView";
import { EventRow } from "@/components/EventCard";
import { Timeline } from "@/components/Timeline";
import { fetchEvents } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { groupByDay } from "@/lib/calendar";
import {
  PERKS,
  TOPICS,
  addDays,
  explore,
  forYou,
  hasAny,
  hasPerks,
  topicLabel,
  vancouverToday,
  type CampusEvent,
  type Topic,
} from "@/lib/events";
import { parseFilters, toggleIn, validateFilterSearch } from "@/lib/filters";
import { useLocalSet } from "@/lib/useLocalSet";

export const Route = createFileRoute("/")({
  validateSearch: validateFilterSearch,
  // Filtering happens in the browser, so chip clicks (search changes) don't refetch.
  loader: () => fetchEvents(),
  staleTime: 30_000,
  errorComponent: ApiErrorView,
  head: () => ({
    meta: [
      { title: "Discover campus events · Quad" },
      {
        name: "description",
        content:
          "Recommended UBC club events, picks from your favourite topics, and something new to try.",
      },
      { property: "og:title", content: "Discover campus events · Quad" },
      {
        property: "og:description",
        content: "UBC club events matched to you, with stretch picks to try something new.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Discover,
});

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

function Discover() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: "/" });
  const { user } = useAuth();
  const { topics: chosen, perks } = parseFilters(search);
  const [saved, toggleSaved] = useLocalSet("quad:saved");
  const [hidden, toggleHidden] = useLocalSet("quad:hidden");

  const events = Route.useLoaderData();
  const today = vancouverToday();
  const pool = events.filter((e) => !hidden.has(e.id));
  const profile = user?.interests ?? [];
  // Chips picked on this page win; otherwise the profile's interests are active.
  const active: Topic[] = chosen.length ? chosen : profile;

  // One timeline, no repeats: a "For you" or "Something different" tag marks why an event stands out.
  const reasons = new Map<string, string>();
  if (active.length) {
    for (const r of forYou(pool, active, []).slice(0, 3)) reasons.set(r.event.id, "For you");
    for (const r of explore(pool, active, []).slice(0, 1))
      reasons.set(r.event.id, "Something different");
  }
  const shown = (
    active.length ? pool.filter((e) => hasAny(e, active) || reasons.has(e.id)) : pool
  ).filter((e) => hasPerks(e, perks));
  const groups = groupByDay(shown);
  const clubs = new Set(pool.map((e) => e.club)).size;
  const thisWeek = pool.filter((e) => e.date && e.date <= addDays(today, 7)).length;

  const topicCount = new Map<string, number>();
  for (const e of pool) for (const t of e.topics) topicCount.set(t, (topicCount.get(t) ?? 0) + 1);
  const topicOrder = [...TOPICS].sort(
    (a, b) => (topicCount.get(b.slug) ?? 0) - (topicCount.get(a.slug) ?? 0),
  );

  const toggleTopic = (slug: string) => {
    const next = toggleIn(active.join(",") || undefined, slug);
    // Toggling back to exactly the profile's interests drops the override from the URL.
    const same = next && profile.length && next === profile.join(",");
    void navigate({ search: { ...search, topics: same ? undefined : next }, replace: true });
  };

  const row = (e: CampusEvent) => (
    <EventRow
      item={{ event: e, reason: reasons.get(e.id) ?? "" }}
      saved={saved.has(e.id)}
      onSave={() => toggleSaved(e.id)}
      onHide={() => toggleHidden(e.id)}
    />
  );

  return (
    <main className="mx-auto max-w-3xl px-4 pb-24 md:px-6">
      <header className="pt-10 pb-8 md:pt-14">
        <p className="text-sm font-medium text-muted-foreground">UBC Vancouver</p>
        <h1 className="mt-1 text-3xl md:text-4xl">What's happening on campus</h1>
        <p className="mt-3 max-w-prose text-muted-foreground">
          {plural(pool.length, "upcoming club event")} from {plural(clubs, "club")},
          {thisWeek > 0 ? ` ${thisWeek} in the next seven days.` : " none in the next seven days."}{" "}
          Quad reads the posters, Instagram accounts and newsletters so you don't have to.
        </p>
      </header>

      <section aria-label="Filter by topic" className="border-y border-border py-4">
        <div className="flex flex-wrap items-center gap-2">
          {topicOrder.map((t) => {
            const on = active.includes(t.slug);
            const n = topicCount.get(t.slug) ?? 0;
            return (
              <button
                key={t.slug}
                type="button"
                aria-pressed={on}
                className="chip"
                data-on={on}
                onClick={() => toggleTopic(t.slug)}
              >
                {on && <Check className="size-3.5" aria-hidden />}
                {t.label}
                {n > 0 && (
                  <span className={on ? "text-white/70" : "text-muted-foreground"}>{n}</span>
                )}
              </button>
            );
          })}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2" aria-label="Filter by perks">
          {PERKS.map((p) => {
            const on = perks.includes(p.key);
            return (
              <button
                key={p.key}
                type="button"
                aria-pressed={on}
                className="chip"
                data-on={on}
                onClick={() =>
                  void navigate({
                    search: { ...search, perks: toggleIn(search.perks, p.key) },
                    replace: true,
                  })
                }
              >
                {on && <Check className="size-3.5" aria-hidden />}
                {p.label}
              </button>
            );
          })}
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          {chosen.length
            ? "Showing these topics only."
            : profile.length
              ? "Showing your interests. Tap a topic to look elsewhere."
              : "Showing everything. Pick topics to narrow it down"}
          {!user && (
            <>
              , or{" "}
              <Link to="/signup" className="text-link underline underline-offset-4">
                sign up
              </Link>{" "}
              to save them.
            </>
          )}
          {chosen.length > 0 && profile.length > 0 && (
            <>
              {" "}
              <button
                type="button"
                className="text-link underline underline-offset-4"
                onClick={() =>
                  void navigate({ search: { ...search, topics: undefined }, replace: true })
                }
              >
                Back to my interests
              </button>
            </>
          )}
        </p>
      </section>

      <section className="pt-8" aria-label="Upcoming events">
        {groups.length ? (
          <Timeline groups={groups} renderEvent={row} today={today} />
        ) : (
          <div className="panel text-center">
            <h2 className="text-xl">
              {active.length
                ? `Nothing coming up in ${active.map(topicLabel).join(", ")}`
                : "Nothing matches those filters"}
            </h2>
            <p className="mt-2 text-muted-foreground">
              Try another topic or perk, or see everything on campus.
            </p>
            <button
              type="button"
              className="btn-solid mt-5"
              onClick={() => void navigate({ search: {}, replace: true })}
            >
              Show everything
            </button>
          </div>
        )}
      </section>

      {hidden.size > 0 && (
        <p className="mt-10 text-sm text-muted-foreground">
          {plural(hidden.size, "hidden event")}.{" "}
          <button
            type="button"
            className="text-link underline underline-offset-4"
            onClick={() => [...hidden].forEach(toggleHidden)}
          >
            Show them again
          </button>
        </p>
      )}
    </main>
  );
}
