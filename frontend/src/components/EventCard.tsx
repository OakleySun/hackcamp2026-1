import { Link, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import {
  CalendarCheck,
  CalendarPlus,
  ExternalLink,
  EyeOff,
  Gift,
  MapPin,
  Pizza,
  Trophy,
  Users,
} from "lucide-react";
import { ClubAvatar, DateLeaf } from "@/components/Bits";
import {
  formatAudience,
  formatPrice,
  isRestricted,
  perkLabel,
  topicLabel,
  type CampusEvent,
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

/** Time only ("5:00 p.m."), or the full date when the card sits outside a day group. */
export const formatTime = (e: CampusEvent) =>
  !e.date
    ? "Date TBD"
    : e.timeKnown
      ? new Date(e.start).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" })
      : "Time TBD";

/** Toggle an event in the calendar and confirm it with a toast. Shared by cards and the event page. */
export function useCalendarToggle() {
  const navigate = useNavigate();
  return (e: CampusEvent, saved: boolean, toggle: () => void) => {
    toggle();
    if (saved) {
      toast("Removed from your calendar", {
        description: e.title,
        action: { label: "Undo", onClick: toggle },
      });
    } else {
      toast("Added to your calendar", {
        description: e.title,
        action: { label: "View calendar", onClick: () => void navigate({ to: "/calendar" }) },
      });
    }
  };
}

export function CalendarButton({
  event,
  saved,
  onToggle,
  compact = false,
}: {
  event: CampusEvent;
  saved: boolean;
  onToggle: () => void;
  compact?: boolean;
}) {
  const toggle = useCalendarToggle();
  return (
    <button
      type="button"
      className={saved ? "btn-ghost" : "btn-solid"}
      aria-pressed={saved}
      onClick={() => toggle(event, saved, onToggle)}
    >
      {saved ? (
        <CalendarCheck className="size-4" aria-hidden />
      ) : (
        <CalendarPlus className="size-4" aria-hidden />
      )}
      {saved ? "In calendar" : compact ? "Add" : "Add to calendar"}
    </button>
  );
}

/**
 * One event in a day-grouped timeline, laid out as a Luma list row: time, title, host and venue
 * on the left; the calendar action on the right. The day heading carries the date.
 */
export function EventRow({
  item,
  saved,
  onSave,
  onHide,
}: {
  item: Ranked;
  saved: boolean;
  onSave: () => void;
  onHide: () => void;
}) {
  const e = item.event;
  const source = e.rsvpUrl ?? e.sources[0]?.url;
  const hide = () => {
    onHide();
    toast("Event hidden", { description: e.title, action: { label: "Undo", onClick: onHide } });
  };
  const facts = [
    formatPrice(e),
    e.beginner === true ? "Beginner-friendly" : null,
    ...e.perks.map(perkLabel),
    isRestricted(e) ? `For ${formatAudience(e)}` : null,
  ].filter((f): f is string => !!f);
  return (
    <article className="event-row">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{formatTime(e)}</span>
          {item.reason && <span className="reason-tag">{item.reason}</span>}
          {e.changes.length > 0 && (
            <span className="status-chip" data-kind="updated">
              Updated
            </span>
          )}
        </p>
        <h3 className="mt-1 text-lg leading-snug font-semibold">
          <Link to="/events/$id" params={{ id: e.id }} className="hover:underline">
            {e.title}
          </Link>
        </h3>
        <p className="mt-1.5 flex items-center gap-2 text-sm text-muted-foreground">
          <ClubAvatar name={e.club} />
          <span className="truncate">{e.club}</span>
        </p>
        <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
          <MapPin className="size-3.5 shrink-0" aria-hidden />
          {e.venue ?? "Venue not listed"}
        </p>
        <p className="mt-2 text-sm text-muted-foreground">{facts.join(", ")}</p>
      </div>
      <div className="flex flex-row flex-wrap items-center gap-1 sm:flex-col sm:flex-nowrap sm:items-end">
        <CalendarButton event={e} saved={saved} onToggle={onSave} compact />
        {source && (
          <a href={source} target="_blank" rel="noreferrer" className="btn-quiet text-xs">
            {e.rsvpUrl ? "RSVP" : "Source"}
            <ExternalLink className="size-3" aria-hidden />
          </a>
        )}
        <button
          type="button"
          className="btn-quiet text-xs"
          aria-label={`Not interested in ${e.title}`}
          onClick={hide}
        >
          <EyeOff className="size-3.5" aria-hidden />
          Not interested
        </button>
      </div>
    </article>
  );
}
