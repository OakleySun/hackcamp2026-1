import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { FilterControls } from "@/components/FilterControls";
import { ApiError, subscribe, verifySubscription, type SubscribeResult } from "@/lib/api";
import { parseFilters, validateFilterSearch } from "@/lib/filters";
import { topicLabel } from "@/lib/events";

export const Route = createFileRoute("/subscribe")({
  validateSearch: validateFilterSearch,
  head: () => ({
    meta: [
      { title: "Get event alerts · Quad" },
      {
        name: "description",
        content: "Email alerts for UBC club events that match your topics and filters.",
      },
      { property: "og:title", content: "Get event alerts · Quad" },
      { property: "og:description", content: "UBC club event alerts, straight to your inbox." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Subscribe,
});

function Subscribe() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: "/subscribe" });
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<SubscribeResult | null>(null);
  const [verified, setVerified] = useState(false);
  const { topics, practical } = parseFilters(search);

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email)) return setError("Enter a valid email address.");
    setError("");
    setSending(true);
    try {
      setResult(
        await subscribe({
          email,
          topics,
          want_free: practical.includes("free"),
          want_beginner: practical.includes("beginner"),
          after_4pm: practical.includes("after4"),
        }),
      );
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? "That email is already subscribed."
          : e instanceof Error
            ? e.message
            : "Something went wrong.",
      );
    } finally {
      setSending(false);
    }
  };

  const verify = async () => {
    if (!result?.verify_token) return;
    try {
      await verifySubscription(result.verify_token);
      setVerified(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't confirm the email.");
    }
  };

  if (result)
    return (
      <main className="mx-auto max-w-xl px-4 py-20 text-center">
        <CheckCircle2 className="mx-auto size-12 text-primary" aria-hidden />
        <h1 className="mt-4 font-display text-4xl">
          {verified ? "You're on the list" : "Check your inbox"}
        </h1>
        <p className="mt-3 text-muted-foreground">
          {verified ? "We'll email " : "Confirm your address and we'll email "}
          <strong className="text-foreground">{email}</strong> when a new
          {topics.length ? ` ${topics.map(topicLabel).join(", ")}` : ""} event matches your choices,
          and again if one you were told about changes time or place. Each email has a link to
          change your choices or unsubscribe.
        </p>
        {result.verify_token && !verified && (
          <div className="mt-6">
            <button type="button" className="btn-solid" onClick={verify}>
              Confirm email (demo)
            </button>
            <p className="mt-2 text-xs text-muted-foreground">
              Demo mode: no email is sent, so confirm here.
            </p>
          </div>
        )}
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        <Link to="/" search={search} className="btn-solid mt-8">
          Keep browsing
        </Link>
      </main>
    );

  return (
    <main className="mx-auto max-w-3xl px-4 pb-24 md:px-8">
      <section className="py-10 md:py-14">
        <h1 className="font-display text-4xl md:text-5xl">Get alerts</h1>
        <p className="mt-3 max-w-xl text-muted-foreground">
          An email when a club posts an event that matches your topics and filters, plus a heads-up
          if it changes time or place. Browsing never needs an account.
        </p>
      </section>
      <form onSubmit={submit} className="panel space-y-6" noValidate>
        <div>
          <label htmlFor="email" className="eyebrow mb-2 block">
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@student.ubc.ca"
            className="field"
            aria-invalid={!!error}
            aria-describedby={error ? "email-err" : undefined}
          />
          {error && (
            <p id="email-err" className="mt-2 text-sm text-destructive">
              {error}
            </p>
          )}
        </div>
        <FilterControls search={search} onChange={(s) => navigate({ search: s, replace: true })} />
        <button type="submit" className="btn-solid" disabled={sending}>
          {sending ? "Signing you up…" : "Sign me up"}
        </button>
        <p className="text-xs text-muted-foreground">
          Every email includes a manage and unsubscribe link.
        </p>
      </form>
    </main>
  );
}
