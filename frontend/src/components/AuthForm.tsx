import { Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { fetchAuthProviders, googleSignInUrl, useAuth } from "@/lib/auth";

/** Sign-up and log-in share one form. New accounts go to setup; returning ones to Discover. */
export function AuthForm({ mode }: { mode: "signup" | "login" }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [google, setGoogle] = useState(false);
  const isSignup = mode === "signup";

  useEffect(() => {
    fetchAuthProviders()
      .then((p) => setGoogle(p.google))
      .catch(() => setGoogle(false)); // older backend or offline: keep the email form only
  }, []);

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
        {google && (
          <>
            <a href={googleSignInUrl()} className="btn-ghost w-full justify-center gap-2 py-2.5">
              <GoogleMark />
              Continue with Google
            </a>
            <p className="flex items-center gap-3 text-xs text-muted-foreground" aria-hidden>
              <span className="h-px flex-1 bg-border" />
              or use email
              <span className="h-px flex-1 bg-border" />
            </p>
          </>
        )}
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

/** Google's "G" mark, as Google's branding guidelines ask for on sign-in buttons. */
function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" className="size-4" aria-hidden>
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}
