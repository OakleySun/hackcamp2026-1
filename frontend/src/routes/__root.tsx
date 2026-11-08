import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
  type ErrorComponentProps,
} from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { AuthProvider, useAuth } from "../lib/auth";
import { Toaster } from "../components/ui/sonner";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link to="/" className="btn-solid">
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: ErrorComponentProps) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          This page didn't load
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong on our end. You can try refreshing or head back home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="btn-solid"
          >
            Try again
          </button>
          <a href="/" className="btn-ghost">
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    // Replace these placeholders with the app's name and description when first building the app.
    // Each content route, / included, must still set its own head(). Never add og:image or
    // twitter:image here: every page without its own would inherit the root's preview image.
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Quad — UBC campus events" },
      { name: "description", content: "Discover UBC club events matched to your interests." },

      { property: "og:title", content: "Quad — UBC campus events" },
      {
        property: "og:description",
        content: "Discover UBC club events matched to your interests.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      {
        rel: "stylesheet",
        href: appCss,
      },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap",
      },
      { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

/** Signed-out: Log in + Sign up. Signed-in: Account. Hidden until the stored session is checked. */
function AccountNav() {
  const { user, ready } = useAuth();
  if (!ready) return null;
  if (user)
    return (
      <Link to={user.onboarded ? "/account" : "/setup"} className="nav-link">
        {user.onboarded ? "Account" : "Finish setup"}
      </Link>
    );
  return (
    <>
      <Link to="/login" className="nav-link">
        Log in
      </Link>
      <Link to="/signup" className="btn-pill">
        Sign up
      </Link>
    </>
  );
}

/** Vancouver time, as Luma shows the local time in its header. Rendered after mount to avoid SSR drift. */
function Clock() {
  const [now, setNow] = useState<string | null>(null);
  useEffect(() => {
    const tick = () =>
      setNow(
        new Date().toLocaleTimeString("en-CA", {
          hour: "numeric",
          minute: "2-digit",
          timeZone: "America/Vancouver",
        }),
      );
    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, []);
  if (!now) return null;
  return (
    <span className="hidden text-sm text-white/60 md:inline" aria-label="Current time in Vancouver">
      {now} <span className="text-white/40">Vancouver</span>
    </span>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        {/* Required: nested routes render here. Removing <Outlet /> breaks all child routes. */}
        <header className="site-header sticky top-0 z-10">
          <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-1.5 px-4 py-2.5 md:px-8">
            <Link
              to="/"
              className="mr-auto flex items-baseline gap-2 text-xl font-semibold tracking-tight"
            >
              <span>
                quad<span className="text-gold">.</span>
              </span>
              <span className="hidden text-xs font-medium text-white/50 sm:inline">
                UBC Vancouver
              </span>
            </Link>
            <Link to="/" className="nav-link" activeOptions={{ exact: true, includeSearch: false }}>
              Discover
            </Link>
            <Link to="/map" className="nav-link">
              Map
            </Link>
            <Link to="/pulse" className="nav-link">
              Pulse
            </Link>
            <Link to="/genie" className="nav-link">
              Ask Genie
            </Link>
            <Link to="/calendar" className="nav-link">
              Calendar
            </Link>
            <span className="mx-2 hidden h-5 w-px bg-white/20 md:inline" aria-hidden />
            <Clock />
            <AccountNav />
          </nav>
        </header>
        <Outlet />
        <footer className="mx-auto max-w-6xl px-4 pb-10 pt-6 text-sm text-muted-foreground md:px-8">
          <div className="border-t border-border pt-6">
            <p>
              Quad is a student project at UBC Vancouver, on the traditional, ancestral and unceded
              territory of the xʷməθkʷəy̓əm (Musqueam) people. Not affiliated with the University of
              British Columbia or the AMS.
            </p>
          </div>
        </footer>
        <Toaster />
      </AuthProvider>
    </QueryClientProvider>
  );
}
