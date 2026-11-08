import { useMutation } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowUpRight, Search } from "lucide-react";
import { useState } from "react";
import { askGenie, type GenieResult } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { topicLabel } from "@/lib/events";

export const Route = createFileRoute("/genie")({
  head: () => ({
    meta: [
      { title: "Ask Genie · Quad" },
      { name: "description", content: "Find upcoming UBC events that match your interests." },
    ],
  }),
  component: Genie,
});

const examples = [
  "Give me three running events",
  "I’m trying to learn more about AI",
  "Find three free events from different organizers this week",
];

const dateLabel = new Intl.DateTimeFormat("en-CA", {
  weekday: "short",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function timeLabel(time: string | null) {
  if (!time) return "Time to be announced";
  const [hour, minute] = time.split(":").map(Number);
  return (
    (hour % 12 || 12) + ":" + String(minute).padStart(2, "0") + (hour < 12 ? " a.m." : " p.m.")
  );
}

function Genie() {
  const { user } = useAuth();
  const [question, setQuestion] = useState("");
  const search = useMutation({ mutationFn: askGenie });

  function ask(value: string) {
    const trimmed = value.trim();
    if (trimmed.length < 2 || search.isPending) return;
    setQuestion(trimmed);
    search.mutate(trimmed);
  }

  return (
    <main className="mx-auto max-w-3xl px-4 pb-24 md:px-8">
      <section className="py-10 md:py-14">
        <h1 className="font-display text-4xl md:text-5xl">Ask Genie</h1>
        <p className="mt-2 text-muted-foreground">
          Tell Genie what you want to try. Get a shortlist of upcoming UBC events with source links.
        </p>
        <form
          className="panel mt-6"
          onSubmit={(event) => {
            event.preventDefault();
            ask(question);
          }}
        >
          <label htmlFor="genie-question" className="text-sm font-medium">
            What are you looking for?
          </label>
          <div className="mt-2 flex flex-wrap gap-2">
            <input
              id="genie-question"
              className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-2 text-base"
              placeholder="I’m trying to learn more about AI"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              maxLength={280}
              autoComplete="off"
            />
            <button
              className="btn-solid inline-flex items-center gap-2 disabled:opacity-50"
              disabled={search.isPending || question.trim().length < 2}
            >
              <Search size={16} aria-hidden="true" /> Ask
            </button>
          </div>
        </form>
        <div className="mt-4 flex flex-wrap gap-2">
          {examples.map((example) => (
            <button
              key={example}
              type="button"
              disabled={search.isPending}
              className="chip disabled:opacity-50"
              onClick={() => ask(example)}
            >
              {example}
            </button>
          ))}
        </div>
        {user && user.interests.length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-sm text-muted-foreground">From your Quad interests</p>
            <div className="flex flex-wrap gap-2">
              {user.interests.map((interest) => (
                <button
                  key={interest}
                  type="button"
                  disabled={search.isPending}
                  className="chip disabled:opacity-50"
                  onClick={() => ask("Find " + interest + " events")}
                >
                  {topicLabel(interest)}
                </button>
              ))}
            </div>
          </div>
        )}
      </section>
      <div role="status" aria-live="polite">
        {search.isPending && (
          <p className="panel text-muted-foreground">Looking through upcoming events…</p>
        )}
        {search.isError && (
          <p className="panel text-muted-foreground">
            The search couldn’t load. Try again in a moment.
          </p>
        )}
        {search.data && <Results result={search.data} />}
      </div>
    </main>
  );
}

function Results({ result }: { result: GenieResult }) {
  if (result.events.length === 0) {
    return (
      <div className="panel">
        <h2 className="font-display text-xl">No matching upcoming events</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Try a broader topic or a wider date range. You can also{" "}
          <Link to="/explore" className="underline">
            browse the full event list
          </Link>
          .
        </p>
      </div>
    );
  }
  const shown = result.events.length;
  return (
    <section>
      <h2 className="font-display text-2xl">
        {shown < result.requested ? "Only " : ""}
        {shown} matching {shown === 1 ? "event" : "events"}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {result.engine === "genie"
          ? "Ranked with Databricks Genie"
          : "Matched from Quad’s event listings"}{" "}
        · Vancouver time
      </p>
      <ul className="mt-4 grid gap-3">
        {result.events.map((event) => (
          <li key={event.event_id} className="panel">
            <Link
              to="/events/$id"
              params={{ id: event.event_id }}
              className="font-medium hover:underline"
            >
              {event.title}
            </Link>
            <p className="mt-1 text-sm text-muted-foreground">{event.club_name}</p>
            <p className="mt-2 text-sm">
              <time dateTime={event.local_date}>
                {dateLabel.format(new Date(event.local_date + "T00:00:00Z"))}
              </time>
              {" · "}
              {timeLabel(event.local_start)}
              {event.venue ? " · " + event.venue : ""}
              {event.cost_status === "free" ? " · Free" : ""}
            </p>
            <a
              href={event.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-flex items-center gap-1 text-sm underline"
            >
              Original listing <ArrowUpRight size={14} aria-hidden="true" />
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
