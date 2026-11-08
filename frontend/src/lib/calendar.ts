// "Add to calendar": saved events live in localStorage (useLocalSet "quad:saved") and can be
// pushed out to Google Calendar or downloaded as .ics for Apple Calendar and Outlook.
import { addDays, formatDay, vancouverToday, type CampusEvent } from "./events";

const TZ = "America/Vancouver";

export type DayGroup = { day: string; events: CampusEvent[] };

/** Events grouped by Vancouver date, earliest day first; events without a date come last under "". */
export function groupByDay(events: CampusEvent[]): DayGroup[] {
  const groups = new Map<string, CampusEvent[]>();
  for (const e of [...events].sort((a, b) => a.start.localeCompare(b.start))) {
    const key = e.date ?? "";
    groups.set(key, [...(groups.get(key) ?? []), e]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a === "" ? 1 : b === "" ? -1 : a.localeCompare(b)))
    .map(([day, evs]) => ({ day, events: evs }));
}

/** "Today", "Tomorrow" or the weekday for a YYYY-MM-DD day. */
export function dayLabel(day: string, today = vancouverToday()) {
  if (!day) return "Date TBD";
  if (day === today) return "Today";
  if (day === addDays(today, 1)) return "Tomorrow";
  return formatDay(day).split(",")[0] ?? formatDay(day);
}

/** Short date for timeline headings: "Nov 12". */
export const dayDate = (day: string) =>
  day
    ? new Date(`${day}T12:00:00Z`).toLocaleDateString("en-CA", {
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      })
    : "";

const pad = (n: number) => String(n).padStart(2, "0");
const compact = (day: string, hhmm: string) =>
  `${day.replace(/-/g, "")}T${hhmm.replace(":", "")}00`;

function endTime(e: CampusEvent): string {
  if (e.end) return e.end;
  const [h = 0, m = 0] = (e.start.split("T")[1] ?? "00:00").split(":").map(Number);
  return h >= 23 ? "23:59" : `${pad(h + 1)}:${pad(m)}`;
}

function describe(e: CampusEvent, siteUrl: string) {
  return [
    `Hosted by ${e.club}`,
    e.rsvpUrl ? `RSVP: ${e.rsvpUrl}` : null,
    e.sources[0] ? `Source: ${e.sources[0].url}` : null,
    `On Quad: ${siteUrl}/events/${e.id}`,
  ]
    .filter(Boolean)
    .join("\n");
}

/** Google Calendar "add event" link; all-day when the start time is unknown. */
export function googleCalendarUrl(e: CampusEvent, siteUrl = "") {
  if (!e.date) return null;
  const dates = e.timeKnown
    ? `${compact(e.date, e.start.split("T")[1] ?? "00:00")}/${compact(e.date, endTime(e))}`
    : `${e.date.replace(/-/g, "")}/${addDays(e.date, 1).replace(/-/g, "")}`;
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: e.title,
    dates,
    ctz: TZ,
    details: describe(e, siteUrl),
  });
  if (e.venue) params.set("location", e.venue);
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

const escapeIcs = (s: string) =>
  s.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");

/** RFC 5545 line folding: 75 octets max, continuation lines start with a space. */
function fold(line: string) {
  const out: string[] = [];
  let rest = line;
  while (new TextEncoder().encode(rest).length > 75) {
    let cut = 75;
    while (new TextEncoder().encode(rest.slice(0, cut)).length > 75) cut--;
    out.push(rest.slice(0, cut));
    rest = ` ${rest.slice(cut)}`;
  }
  out.push(rest);
  return out.join("\r\n");
}

/** One VEVENT per dated event; Vancouver local times with a TZID, all-day when the time is unknown. */
export function buildIcs(events: CampusEvent[], siteUrl = "", now = new Date()) {
  const stamp = now
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}/, "");
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Quad//UBC campus events//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "X-WR-CALNAME:Quad",
    `X-WR-TIMEZONE:${TZ}`,
  ];
  for (const e of events) {
    if (!e.date) continue;
    lines.push("BEGIN:VEVENT", `UID:${e.id}@quad.ubc`, `DTSTAMP:${stamp}`);
    if (e.timeKnown) {
      lines.push(
        `DTSTART;TZID=${TZ}:${compact(e.date, e.start.split("T")[1] ?? "00:00")}`,
        `DTEND;TZID=${TZ}:${compact(e.date, endTime(e))}`,
      );
    } else {
      lines.push(
        `DTSTART;VALUE=DATE:${e.date.replace(/-/g, "")}`,
        `DTEND;VALUE=DATE:${addDays(e.date, 1).replace(/-/g, "")}`,
      );
    }
    lines.push(`SUMMARY:${escapeIcs(e.title)}`);
    if (e.venue) lines.push(`LOCATION:${escapeIcs(e.venue)}`);
    lines.push(`DESCRIPTION:${escapeIcs(describe(e, siteUrl))}`);
    if (e.rsvpUrl) lines.push(`URL:${e.rsvpUrl}`);
    lines.push("END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  return `${lines.map(fold).join("\r\n")}\r\n`;
}

/** Trigger a browser download of an .ics file. */
export function downloadIcs(filename: string, events: CampusEvent[]) {
  const blob = new Blob([buildIcs(events, window.location.origin)], {
    type: "text/calendar;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".ics") ? filename : `${filename}.ics`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** A safe file name from an event title. */
export const icsFilename = (title: string) =>
  `${
    title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "event"
  }.ics`;
