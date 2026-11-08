export const TOPICS = [
  { slug: "tech", label: "Tech", near: ["academic", "career"] },
  { slug: "career", label: "Career", near: ["tech", "academic", "social"] },
  { slug: "academic", label: "Academic", near: ["tech", "career", "culture"] },
  { slug: "arts", label: "Arts", near: ["culture", "social"] },
  { slug: "sports", label: "Sports", near: ["wellness", "social"] },
  { slug: "culture", label: "Culture", near: ["arts", "social", "academic"] },
  { slug: "social", label: "Social", near: ["culture", "sports", "arts"] },
  { slug: "wellness", label: "Wellness", near: ["sports", "arts"] },
] as const;

export type Topic = (typeof TOPICS)[number]["slug"];
export const topicLabel = (t: string) => TOPICS.find((x) => x.slug === t)?.label ?? t;

export const PRACTICAL = [
  { key: "free", label: "Free" },
  { key: "beginner", label: "Beginner-friendly" },
  { key: "after4", label: "After 4 p.m." },
] as const;
export type Practical = (typeof PRACTICAL)[number]["key"];

// Keep in sync with PERKS in app/extract.py.
export const PERKS = [
  { key: "free_food", label: "Free food" },
  { key: "free_swag", label: "Free swag" },
  { key: "prizes", label: "Prizes" },
] as const;
export type Perk = (typeof PERKS)[number]["key"];
export const perkLabel = (p: string) => PERKS.find((x) => x.key === p)?.label ?? p;

// Keep in sync with AUDIENCES in app/extract.py. ["anyone"] = open to all, [] = not stated.
export const AUDIENCES = [
  { key: "anyone", label: "Anyone" },
  { key: "ubc_students", label: "UBC students" },
  { key: "first_years", label: "1st-year students" },
  { key: "grad_students", label: "Grad students" },
  { key: "women", label: "Women" },
  { key: "women_nonbinary", label: "Women & non-binary students" },
  { key: "cs_students", label: "Computer Science students" },
  { key: "engineering_students", label: "Engineering students" },
  { key: "science_students", label: "Science students" },
  { key: "arts_students", label: "Arts students" },
  { key: "business_students", label: "Sauder / Commerce students" },
  { key: "international_students", label: "International students" },
  { key: "members_only", label: "Club members" },
  { key: "19_plus", label: "19+" },
] as const;
export type Audience = (typeof AUDIENCES)[number]["key"];
export const audienceLabel = (a: string) => AUDIENCES.find((x) => x.key === a)?.label ?? a;
/** True when the event is limited to certain groups (not open to anyone, not unstated). */
export const isRestricted = (e: CampusEvent) =>
  e.audience.length > 0 && !e.audience.includes("anyone");
/** "Anyone", "1st-year students · Computer Science students", or "Not listed". */
export const formatAudience = (e: CampusEvent) =>
  e.audience.length ? e.audience.map(audienceLabel).join(" · ") : "Not listed";

export const COMFORT = [
  { key: "close", label: "Stay close" },
  { key: "mix", label: "Mix it up" },
  { key: "surprise", label: "Surprise me" },
] as const;
export type Comfort = (typeof COMFORT)[number]["key"];

export type Source = { label: string; url: string };
export type Change = { field: string; from: string; to: string; confirmedAt: string };
export type Cost = "free" | "paid" | "unknown";

/** UI model of a published event. Built from the API response by `toCampusEvent` in ./api. */
export type CampusEvent = {
  id: string;
  title: string;
  club: string;
  topic: Topic | null; // primary topic for recommendations; null when unclassified
  topics: Topic[];
  date: string | null; // YYYY-MM-DD, America/Vancouver
  start: string; // local ISO date-time, "" when the date is unknown
  timeKnown: boolean;
  end: string | null; // HH:MM
  venue: string | null;
  cost: Cost;
  beginner: boolean | null; // null = not stated
  perks: Perk[];
  audience: Audience[];
  place: Place | null; // UBC building matched from the venue; null = not on the map
  rsvpUrl: string | null;
  sources: Source[];
  changes: Change[];
};

export const isFree = (e: CampusEvent) => e.cost === "free";
export const isAfter4 = (e: CampusEvent) => e.timeKnown && new Date(e.start).getHours() >= 16;

export function passesPractical(e: CampusEvent, p: Practical[]) {
  // Unknown price or level never passes a restrictive filter (matches the backend and n8n rules).
  if (p.includes("free") && !isFree(e)) return false;
  if (p.includes("beginner") && e.beginner !== true) return false;
  if (p.includes("after4") && !isAfter4(e)) return false;
  return true;
}

/** Every selected perk must be offered. */
export const hasPerks = (e: CampusEvent, perks: Perk[]) => perks.every((p) => e.perks.includes(p));

const byDate = (a: CampusEvent, b: CampusEvent) => a.start.localeCompare(b.start);
export const hasAny = (e: CampusEvent, topics: Topic[]) => e.topics.some((t) => topics.includes(t));

export type Ranked = { event: CampusEvent; reason: string };

export function forYou(events: CampusEvent[], topics: Topic[], practical: Practical[]): Ranked[] {
  const pool = events.filter((e) => passesPractical(e, practical));
  const matched = topics.length ? pool.filter((e) => hasAny(e, topics)) : pool;
  return [...matched]
    .sort((a, b) => Number(b.beginner === true) - Number(a.beginner === true) || byDate(a, b))
    .slice(0, 6)
    .map((e) => {
      const hit = e.topics.find((t) => topics.includes(t));
      return {
        event: e,
        reason: hit ? `Matches your interest in ${topicLabel(hit)}` : "Popular this week",
      };
    });
}

export function explore(
  events: CampusEvent[],
  topics: Topic[],
  practical: Practical[],
  comfort: Comfort = "mix", // no UI control any more; "mix" blends nearby and far topics
): Ranked[] {
  if (!topics.length) return [];
  const near = new Set(
    topics
      .flatMap((t) => TOPICS.find((x) => x.slug === t)!.near)
      .filter((t) => !topics.includes(t as Topic)),
  );
  const pool = events
    .filter((e): e is CampusEvent & { topic: Topic } => e.topic !== null)
    .filter((e) => passesPractical(e, practical) && !hasAny(e, topics));
  const nearEv = pool.filter((e) => near.has(e.topic)).sort(byDate);
  const farEv = pool.filter((e) => !near.has(e.topic)).sort(byDate);
  const ordered =
    comfort === "close"
      ? nearEv
      : comfort === "mix"
        ? [...nearEv.slice(0, 2), ...farEv, ...nearEv.slice(2)]
        : [...farEv, ...nearEv];
  const seen = new Set<string>();
  return ordered
    .filter((e) => (seen.has(e.topic) ? false : (seen.add(e.topic), true)))
    .slice(0, 3)
    .map((e) => ({
      event: e,
      reason: near.has(e.topic)
        ? `${topicLabel(e.topic)} sits close to ${topics.map(topicLabel).join(" & ")}`
        : `Something completely different: ${topicLabel(e.topic)}`,
    }));
}

export type TopInterest = { topic: Topic; why: string };

/**
 * The student's strongest topics, best first, for the topic sections on Discover.
 * Signals: chips picked on the page (3 pts), profile interests (2 pts, earlier picks slightly
 * ahead), and topics of saved events (1 pt each). Only topics with upcoming events are returned,
 * so a section is never empty; with no signals at all, the busiest topics come first.
 */
export function topInterests(
  events: CampusEvent[],
  signals: { chosen?: Topic[]; profile?: Topic[]; saved?: CampusEvent[] },
  limit = 2,
): TopInterest[] {
  const { chosen = [], profile = [], saved = [] } = signals;
  const count = new Map<Topic, number>();
  for (const e of events) for (const t of e.topics) count.set(t, (count.get(t) ?? 0) + 1);
  const savedCount = new Map<Topic, number>();
  for (const e of saved) for (const t of e.topics) savedCount.set(t, (savedCount.get(t) ?? 0) + 1);

  const score = (t: Topic) =>
    (chosen.includes(t) ? 3 : 0) +
    (profile.includes(t) ? 2 - profile.indexOf(t) * 0.01 : 0) +
    (savedCount.get(t) ?? 0);
  const why = (t: Topic) => {
    if (chosen.includes(t)) return `Because you picked ${topicLabel(t)}`;
    if (profile.includes(t)) return `From your interests`;
    const n = savedCount.get(t) ?? 0;
    if (n) return `You saved ${n} ${topicLabel(t)} event${n > 1 ? "s" : ""}`;
    return `Popular right now`;
  };

  return TOPICS.map((x) => x.slug as Topic)
    .filter((t) => (count.get(t) ?? 0) > 0)
    .sort((a, b) => score(b) - score(a) || (count.get(b) ?? 0) - (count.get(a) ?? 0))
    .slice(0, limit)
    .map((t) => ({ topic: t, why: why(t) }));
}

// ------------------------------------------------------------ map

export type Place = { id: string; name: string; lat: number; lng: number };

/** Today's date in Vancouver as YYYY-MM-DD, whatever the viewer's time zone. */
export const vancouverToday = (now = new Date()) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "America/Vancouver" }).format(now);

export const addDays = (day: string, n: number) => {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

export const eventsOn = (events: CampusEvent[], day: string) =>
  events.filter((e) => e.date === day).sort(byDate);

/** First day after `day` that has events, or null. */
export const nextDayWithEvents = (events: CampusEvent[], day: string) =>
  events
    .map((e) => e.date)
    .filter((d): d is string => !!d && d > day)
    .sort()[0] ?? null;
export const prevDayWithEvents = (events: CampusEvent[], day: string, min: string) =>
  events
    .map((e) => e.date)
    .filter((d): d is string => !!d && d < day && d >= min)
    .sort()
    .at(-1) ?? null;

export type PlaceGroup = { place: Place; events: CampusEvent[] };

/** One pin per building; events without a known building are returned separately. */
export function groupByPlace(events: CampusEvent[]): {
  pins: PlaceGroup[];
  unplaced: CampusEvent[];
} {
  const pins = new Map<string, PlaceGroup>();
  const unplaced: CampusEvent[] = [];
  for (const e of events) {
    if (!e.place) unplaced.push(e);
    else {
      const g = pins.get(e.place.id) ?? { place: e.place, events: [] };
      g.events.push(e);
      pins.set(e.place.id, g);
    }
  }
  return { pins: [...pins.values()], unplaced };
}

export const formatDay = (day: string) =>
  new Date(`${day}T12:00:00Z`).toLocaleDateString("en-CA", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });

export function upcoming(events: CampusEvent[], practical: Practical[]): Ranked[] {
  return events
    .filter((e) => passesPractical(e, practical))
    .sort(byDate)
    .map((e) => ({ event: e, reason: e.topic ? `${topicLabel(e.topic)} · ${e.club}` : e.club }));
}

export function formatWhen(e: CampusEvent) {
  if (!e.date) return "Date TBD";
  const d = new Date(e.start);
  const date = d.toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric" });
  if (!e.timeKnown) return `${date} · Time TBD`;
  const time = d.toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" });
  return `${date} · ${time}`;
}
export const formatPrice = (e: CampusEvent) =>
  e.cost === "free" ? "Free" : e.cost === "paid" ? "Paid" : "Price not listed";
export const formatStamp = (s: string) =>
  new Date(s).toLocaleString("en-CA", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
