import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useAuth } from "@/lib/auth";

/** Sign-up and log-in share one form. New accounts go to setup; returning ones to Discover. */
export function AuthForm({ mode }: { mode: "signup" | "login" }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isSignup = mode === "signup";

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email)) return setError("Enter a valid email address.");
    if (password.length < 8) return setError("Passwords need at least 8 characters.");
    setError("");
    setBusy(true);
    try {
      const user = isSignup
        ? await auth.signup(email, password)
        : await auth.login(email, password);
      await navigate({ to: user.onboarded ? "/" : "/setup" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto max-w-md px-4 pb-24 md:px-8">
      <section className="py-10 md:py-14">
        <h1 className="font-display text-4xl md:text-5xl">
          {isSignup ? "Make an account" : "Welcome back"}
        </h1>
        <p className="mt-3 text-muted-foreground">
          {isSignup
            ? "Save your interests once and Discover picks events for you on every visit."
            : "Log in to get picks based on your profile."}
        </p>
      </section>
      <form onSubmit={submit} className="panel space-y-5" noValidate>
        <div>
          <label htmlFor="email" className="eyebrow mb-2 block">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@student.ubc.ca"
            className="field"
          />
        </div>
        <div>
          <label htmlFor="password" className="eyebrow mb-2 block">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete={isSignup ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="field"
            aria-describedby="password-hint"
          />
          {isSignup && (
            <p id="password-hint" className="mt-2 text-xs text-muted-foreground">
              At least 8 characters.
            </p>
          )}
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <button type="submit" className="btn-solid w-full justify-center" disabled={busy}>
          {busy ? "One moment…" : isSignup ? "Create account" : "Log in"}
        </button>
        <p className="text-center text-sm text-muted-foreground">
          {isSignup ? "Already have an account? " : "New to Quad? "}
          <Link to={isSignup ? "/login" : "/signup"} className="underline">
            {isSignup ? "Log in" : "Make an account"}
          </Link>
        </p>
      </form>
    </main>
  );
}
