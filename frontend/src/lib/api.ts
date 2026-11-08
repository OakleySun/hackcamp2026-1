// Client for the FastAPI backend in ../app (see app/main.py).
// On Maritime, the browser uses Nitro's same-origin proxy and SSR calls FastAPI directly.
import {
  AUDIENCES,
  PERKS,
  TOPICS,
  type Audience,
  type CampusEvent,
  type Change,
  type Cost,
  type Perk,
  type Place,
  type Source,
  type Topic,
} from "./events";

const configuredUrl = import.meta.env["VITE_API_URL"] as string | undefined;
const localBackend = "http://127.0.0.1:8000";
export const API_URL =
  configuredUrl === "same-origin"
    ? (typeof window === "undefined" ? localBackend : "")
    : (configuredUrl || localBackend).replace(/\/+$/, "");

/** Shape returned by service.public_event. */
export type ApiEvent = {
  event_id: string;
  club_id: string;
  club_name?: string;
  current_revision: number;
  state: string;
  title: string;
  local_date: string | null; // YYYY-MM-DD, America/Vancouver
  local_start: string | null; // HH:MM
  local_end: string | null;
  venue: string | null;
  cost_status: Cost;
  beginner_friendly: boolean | null;
  topics: string[];
  perks?: string[];
  audience?: string[];
  place?: Place | null;
  rsvp_url: string | null;
  start_utc: string | null;
  sources: { source_id: string; source_url: string }[];
  unknown_fields: string[];
  history?: ApiRevision[];
  latest_update: ApiRevision | null;
};
type ApiRevision = {
  revision: number;
  changed: Record<string, { old: unknown; new: unknown }>;
  confirmed_at: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

/** FastAPI sends a string for HTTPException and a list of {loc, msg} for validation errors. */
function errorText(detail: unknown): string {
  if (typeof detail === "string") return capitalize(detail);
  if (Array.isArray(detail) && detail.length) {
    const d = detail[0] as { loc?: unknown[]; msg?: string };
    const field = String(d.loc?.at(-1) ?? "").replace(/_/g, " ");
    return capitalize(
      `${field ? `${field}: ` : ""}${(d.msg ?? "invalid value").replace(/^Value error, /, "")}`,
    );
  }
  return "";
}
const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(`Can't reach the API at ${API_URL || "this site"}.`);
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
    throw new ApiError(
      errorText(body?.detail) || res.statusText || `Request failed (${res.status})`,
      res.status,
    );
  }
  return (await res.json()) as T;
}

// ------------------------------------------------------------ mapping

const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  local_date: "Date",
  local_start: "Start time",
  local_end: "End time",
  venue: "Venue",
  cost_status: "Price",
  beginner_friendly: "Level",
  topics: "Topics",
  rsvp_url: "RSVP link",
};

function formatValue(field: string, v: unknown): string {
  if (v === null || v === undefined || v === "") return "Not listed";
  if ((field === "local_start" || field === "local_end") && typeof v === "string") {
    const [h = 0, m = 0] = v.split(":").map(Number);
    return new Date(2000, 0, 1, h, m).toLocaleTimeString("en-CA", {
      hour: "numeric",
      minute: "2-digit",
    });
  }
  if (field === "local_date" && typeof v === "string") {
    return new Date(`${v}T00:00`).toLocaleDateString("en-CA", {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  }
  if (field === "cost_status") return v === "free" ? "Free" : v === "paid" ? "Paid" : "Not listed";
  if (field === "beginner_friendly") return v ? "Beginner-friendly" : "Some experience helps";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

function sourceLabel(url: string): string {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, "");
    const path = u.pathname.replace(/\/+$/, "");
    if (host.endsWith("instagram.com")) return `Instagram @${path.split("/")[1] ?? ""}`;
    // Several announcements often share a host, so keep the path to tell them apart.
    return path ? `${host}${path.length > 40 ? `${path.slice(0, 40)}…` : path}` : host;
  } catch {
    return url;
  }
}

const isTopic = (t: string): t is Topic => TOPICS.some((x) => x.slug === t);
const isPerk = (p: string): p is Perk => PERKS.some((x) => x.key === p);
const isAudience = (a: string): a is Audience => AUDIENCES.some((x) => x.key === a);
const isEmpty = (v: unknown) =>
  v === null || v === undefined || (Array.isArray(v) && v.length === 0);

export function toCampusEvent(a: ApiEvent): CampusEvent {
  const topics = a.topics.filter(isTopic);
  const revisions = a.history ?? (a.latest_update ? [a.latest_update] : []);
  // Only real corrections: a field filled in for the first time (old = null) is not a "change".
  const changes: Change[] = revisions.flatMap((r) =>
    Object.entries(r.changed)
      // Perks only accumulate, so an added perk is news, not a correction.
      // A first-time fill (old = null or []) isn't a change either.
      .filter(([field, d]) => field !== "perks" && !isEmpty(d.old))
      .map(([field, d]) => ({
        field: FIELD_LABELS[field] ?? field,
        from: formatValue(field, d.old),
        to: formatValue(field, d.new),
        confirmedAt: r.confirmed_at,
      })),
  );
  const sources: Source[] = a.sources.map((s) => ({
    label: sourceLabel(s.source_url),
    url: s.source_url,
  }));
  return {
    id: a.event_id,
    title: a.title,
    club: a.club_name ?? a.club_id,
    topic: topics[0] ?? null,
    topics,
    date: a.local_date,
    start: a.local_date ? `${a.local_date}T${a.local_start ?? "00:00"}` : "",
    timeKnown: !!a.local_date && !!a.local_start,
    end: a.local_end,
    venue: a.venue,
    cost: a.cost_status,
    beginner: a.beginner_friendly,
    perks: (a.perks ?? []).filter(isPerk),
    audience: (a.audience ?? []).filter(isAudience),
    place: a.place ?? null,
    rsvpUrl: a.rsvp_url,
    sources,
    changes,
  };
}

// ------------------------------------------------------------ endpoints

export async function fetchEvents(): Promise<CampusEvent[]> {
  return (await request<ApiEvent[]>("/api/events")).map(toCampusEvent);
}

export type PulseSnapshot = {
  refreshed_at: string | null;
  metrics: {
    announcements: number;
    upcoming_events: number;
    event_revisions: number;
    venues_placed_by_ai: number;
    possible_duplicates: number;
  } | null;
  events: {
    event_id: string;
    revision: number;
    title: string;
    club_name: string;
    local_date: string;
    source_url: string;
    building_name: string | null;
    location_method: string | null;
  }[];
};

export const fetchPulse = () => request<PulseSnapshot>("/api/pulse");

export type GenieResult = {
  engine: "genie" | "quad";
  requested: number;
  matched: number;
  events: {
    event_id: string;
    title: string;
    club_name: string;
    local_date: string;
    local_start: string | null;
    venue: string | null;
    cost_status: Cost;
    beginner_friendly: number | null;
    source_url: string;
  }[];
};

export const askGenie = (question: string) =>
  request<GenieResult>("/api/genie", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

export async function fetchEvent(id: string): Promise<CampusEvent | null> {
  try {
    return toCampusEvent(await request<ApiEvent>(`/api/events/${encodeURIComponent(id)}`));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export type SubscribeBody = {
  email: string;
  topics: string[];
  want_free: boolean;
  want_beginner: boolean;
  after_4pm: boolean;
};
/** In APP_MODE=demo the backend returns the verify/manage tokens so the flow works without email. */
export type SubscribeResult = {
  subscriber_id: string;
  verify_token?: string;
  manage_token?: string;
};

export const subscribe = (body: SubscribeBody) =>
  request<SubscribeResult>("/api/subscriptions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const verifySubscription = (token: string) =>
  request<{ verified: boolean }>(`/verify?token=${encodeURIComponent(token)}`, { method: "POST" });
