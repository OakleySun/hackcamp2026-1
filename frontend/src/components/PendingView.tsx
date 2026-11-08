import { Skeleton } from "@/components/ui/skeleton";

export function PendingView() {
  return (
    <main className="mx-auto max-w-6xl px-4 pb-24 md:px-8" aria-busy="true">
      <p className="sr-only" role="status">
        Loading events
      </p>
      <Skeleton className="mt-10 h-10 w-64 rounded-xl motion-reduce:animate-none md:h-14" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 mt-10">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-56 rounded-2xl motion-reduce:animate-none" />
        ))}
      </div>
    </main>
  );
}
