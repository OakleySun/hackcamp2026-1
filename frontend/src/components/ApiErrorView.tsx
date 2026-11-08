import { useRouter, type ErrorComponentProps } from "@tanstack/react-router";
import { API_URL } from "@/lib/api";

/** Route-level error view for loader failures, usually the backend not running. */
export function ApiErrorView({ error, reset }: ErrorComponentProps) {
  const router = useRouter();
  return (
    <main className="mx-auto max-w-xl px-4 py-20 text-center">
      <h1 className="font-display text-3xl">Events didn't load</h1>
      <p className="mt-3 text-muted-foreground">
        {error instanceof Error ? error.message : "Something went wrong."}
      </p>
      <p className="mt-2 text-sm text-muted-foreground">
        API: <code>{API_URL || "Same origin"}</code>
      </p>
      <button
        type="button"
        className="btn-solid mt-6"
        onClick={() => {
          reset();
          void router.invalidate();
        }}
      >
        Try again
      </button>
    </main>
  );
}
