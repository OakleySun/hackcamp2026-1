import { Link } from "@tanstack/react-router";
import {
  Bookmark,
  BookmarkCheck,
  Calendar,
  ExternalLink,
  EyeOff,
  Gift,
  MapPin,
  Pizza,
  Ticket,
  Trophy,
  Users,
} from "lucide-react";
import {
  formatAudience,
  formatPrice,
  formatWhen,
  isRestricted,
  perkLabel,
  topicLabel,
  type Perk,
  type Ranked,
} from "@/lib/events";

const PERK_ICONS: Record<Perk, typeof Gift> = {
  free_food: Pizza,
  free_swag: Gift,
  prizes: Trophy,
};

export function PerkTags({ perks }: { perks: Perk[] }) {
  if (!perks.length) return null;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Perks">
      {perks.map((p) => {
        const Icon = PERK_ICONS[p];
        return (
          <li key={p} className="perk-tag">
            <Icon className="size-3.5" aria-hidden />
            {perkLabel(p)}
          </li>
        );
      })}
    </ul>
  );
}

export function EventCard({
  item,
  saved,
  onSave,
  onHide,
  variant = "default",
}: {
  item: Ranked;
  saved: boolean;
  onSave: () => void;
  onHide: () => void;
  variant?: "default" | "stretch" | undefined;
}) {
  const e = item.event;
  const action = e.rsvpUrl ?? e.sources[0]?.url;
  return (
    <article className="event-card" data-variant={variant}>
      <div className="flex items-center justify-between gap-2">
        <span className="status-chip" data-topic={e.topic}>
          {topicLabel(e.topic)}
        </span>
        {e.changes.length > 0 && (
          <span className="status-chip" data-kind="updated">
            Updated
          </span>
        )}
      </div>
      <h3 className="mt-3 font-display text-xl leading-tight">
        <Link
          to="/events/$id"
          params={{ id: e.id }}
          className="hover:underline focus-visible:underline"
        >
          {e.title}
        </Link>
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">{e.club}</p>
      <ul className="mt-3 space-y-1 text-sm">
        <li className="flex gap-2">
          <Calendar className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          {formatWhen(e)}
        </li>
        <li className="flex gap-2">
          <MapPin className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          {e.venue ?? "Venue not listed"}
        </li>
        <li className="flex gap-2">
          <Ticket className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          {formatPrice(e)}
        </li>
        {isRestricted(e) && (
          <li className="flex gap-2 font-medium">
            <Users className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <span>
              <span className="sr-only">Who can go: </span>
              {formatAudience(e)}
            </span>
          </li>
        )}
      </ul>
      {e.perks.length > 0 && (
        <div className="mt-3">
          <PerkTags perks={e.perks} />
        </div>
      )}
      <p className="reason mt-3">{item.reason}</p>
      <div className="mt-auto flex flex-wrap gap-2 pt-4">
        <button type="button" className="btn-ghost" aria-pressed={saved} onClick={onSave}>
          {saved ? (
            <BookmarkCheck className="size-4" aria-hidden />
          ) : (
            <Bookmark className="size-4" aria-hidden />
          )}
          {saved ? "Saved" : "Save"}
        </button>
        <button type="button" className="btn-ghost" onClick={onHide}>
          <EyeOff className="size-4" aria-hidden />
          Not interested
        </button>
        {action && (
          <a href={action} target="_blank" rel="noreferrer" className="btn-solid ml-auto">
            {e.rsvpUrl ? "RSVP" : "View source"}
            <ExternalLink className="size-3.5" aria-hidden />
          </a>
        )}
      </div>
    </article>
  );
}
