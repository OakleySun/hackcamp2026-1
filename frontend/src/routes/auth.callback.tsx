import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";

// The backend sends the browser here after Google sign-in, with either #code=…&next=… or #error=….
// The code is single-use and short-lived; it's traded for a session and removed from the address bar.
export const Route = createFileRoute("/auth/callback")({
  head: () => ({
    meta: [{ title: "Signing in · Quad" }, { name: "robots", content: "noindex" }],
  }),
  component: AuthCallback,
});

/** Same-site paths only; anything else goes to Discover. */
const safeNext = (p: string | null) => (p && p.startsWith("/") && !p.startsWith("//") ? p : "/");

function AuthCallback() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return; // React dev mode runs effects twice; the code only works once
    done.current = true;
    const params = new URLSearchParams(window.location.hash.slice(1));
    window.history.replaceState(null, "", window.location.pathname);
    const code = params.get("code");
    if (!code) {
      setError(params.get("error") || "The sign-in didn't finish. Please try again.");
      return;
    }
    auth
      .redeemGoogle(code)
      .then((user) =>
        navigate({ to: user.onboarded ? safeNext(params.get("next")) : "/setup", replace: true }),
      )
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Something went wrong. Please try again."),
      );
  }, [auth, navigate]);

  return (
    <main className="mx-auto max-w-md px-4 pb-24 md:px-8">
      <section className="py-10 md:py-14">
        {error ? (
          <>
            <h1 className="font-display text-4xl">Couldn't sign you in</h1>
            <p role="alert" className="mt-3 text-muted-foreground">
              {error}
            </p>
            <Link to="/login" className="btn-solid mt-6">
              Back to log in
            </Link>
          </>
        ) : (
          <>
            <h1 className="font-display text-4xl">Signing you in…</h1>
            <p className="mt-3 text-muted-foreground" aria-live="polite">
              One moment while we finish signing you in with Google.
            </p>
          </>
        )}
      </section>
    </main>
  );
}
