import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Check } from "lucide-react";
import { ApiErrorView } from "@/components/ApiErrorView";
import { EventCard } from "@/components/EventCard";
import { Section } from "@/components/Section";
import { fetchEvents } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  TOPICS,
  explore,
  forYou,
  hasAny,
  topInterests,
  topicLabel,
  type Ranked,
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

function Discover() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: "/" });
  const { user } = useAuth();
  const { topics: chosen } = parseFilters(search);
  const [saved, toggleSaved] = useLocalSet("quad:saved");
  const [hidden, toggleHidden] = useLocalSet("quad:hidden");

  const events = Route.useLoaderData();
  const pool = events.filter((e) => !hidden.has(e.id));
  const profile = user?.interests ?? [];
  // Chips picked on this page win; otherwise the profile's interests are active.
  const active: Topic[] = chosen.length ? chosen : profile;
  const featured = topInterests(pool, {
    chosen,
    profile,
    saved: events.filter((e) => saved.has(e.id)),
  });
  // No interests yet: Recommended is "popular", and "Try something new" steps away from the top topics.
  const recommended = forYou(pool, active, []).slice(0, 3);
  const stretch = explore(pool, active.length ? active : featured.map((f) => f.topic), []);

  const toggleTopic = (slug: string) => {
    const next = toggleIn(active.join(",") || undefined, slug);
    // Toggling back to exactly the profile's interests drops the override from the URL.
    const same = next && profile.length && next === profile.join(",");
    void navigate({ search: { ...search, topics: same ? undefined : next }, replace: true });
  };

  const card = (r: Ranked, variant?: "stretch") => (
    <EventCard
      key={r.event.id}
      item={r}
      variant={variant}
      saved={saved.has(r.event.id)}
      onSave={() => toggleSaved(r.event.id)}
      onHide={() => toggleHidden(r.event.id)}
    />
  );
  const grid = (items: Ranked[], variant?: "stretch") =>
    items.length ? (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((r) => card(r, variant))}
      </div>
    ) : (
      <p className="text-muted-foreground">Nothing coming up here right now.</p>
    );

  const interestsNote = chosen.length
    ? "Showing picks for these topics"
    : profile.length
      ? "From your profile. Tap to try others"
      : user
        ? "Pick topics to personalise"
        : "Pick topics, or sign up to save them";

  return (
    <main className="mx-auto max-w-6xl px-4 pb-24 md:px-8">
      <section className="py-10 md:py-14">
        <h1 className="font-display text-4xl leading-[1.05] md:text-6xl">
          What's on at UBC
          <br />
          <span className="text-primary">this week.</span>
        </h1>
        <p className="mt-3 max-w-xl text-muted-foreground">
          Picked for you from club posters, Instagram and newsletters. Want to dig through
          everything?{" "}
          <Link to="/explore" className="underline">
            Explore all events
          </Link>
          .
        </p>
      </section>

      <section aria-label="Your interests" className="panel">
        <fieldset>
          <legend className="eyebrow mb-2">Your interests</legend>
          <div className="flex flex-wrap gap-2">
            {TOPICS.map((t) => {
              const on = active.includes(t.slug);
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
                </button>
              );
            })}
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            {interestsNote}
            {!user && (
              <>
                {" · "}
                <Link to="/signup" className="underline">
                  Sign up
                </Link>
              </>
            )}
            {chosen.length > 0 && profile.length > 0 && (
              <>
                {" · "}
                <button
                  type="button"
                  className="underline"
                  onClick={() =>
                    void navigate({ search: { ...search, topics: undefined }, replace: true })
                  }
                >
                  Back to my profile
                </button>
              </>
            )}
          </p>
        </fieldset>
      </section>

      <Section
        title="Recommended"
        note={active.length ? "Top picks from your interests" : "Popular this week"}
      >
        {grid(recommended)}
      </Section>

      {featured.map(({ topic, why }) => (
        <Section key={topic} title={topicLabel(topic)} note={why}>
          {grid(
            pool
              .filter((e) => hasAny(e, [topic]))
              .sort((a, b) => a.start.localeCompare(b.start))
              .slice(0, 3)
              .map((e) => ({ event: e, reason: `More ${topicLabel(topic)} events` })),
          )}
        </Section>
      ))}

      <Section title="Try something new" note="A step outside your usual">
        {grid(stretch, "stretch")}
      </Section>

      {hidden.size > 0 && (
        <p className="mt-10 text-sm text-muted-foreground">
          {hidden.size} hidden event{hidden.size > 1 ? "s" : ""}.{" "}
          <button
            type="button"
            className="underline"
            onClick={() => [...hidden].forEach(toggleHidden)}
          >
            Show them again
          </button>
        </p>
      )}
    </main>
  );
}
