import { describe, expect, it } from "vitest";
import { toCampusEvent, type ApiEvent } from "@/lib/api";
import { buildIcs, dayLabel, googleCalendarUrl, groupByDay, icsFilename } from "@/lib/calendar";

const api = (over: Partial<ApiEvent>): ApiEvent => ({
  event_id: "evt-1",
  club_id: "demo-campus-coding-club",
  club_name: "Demo Campus Coding Club",
  current_revision: 1,
  state: "published",
  title: "Intro to Git; part 1, hands-on",
  local_date: "2026-11-12",
  local_start: "17:00",
  local_end: "18:00",
  venue: "Demo Hall 101",
  cost_status: "free",
  beginner_friendly: true,
  topics: ["tech"],
  rsvp_url: "https://example.org/rsvp",
  start_utc: "2026-11-13T01:00+00:00",
  sources: [{ source_id: "src-direct-form", source_url: "https://example.org/flyer" }],
  unknown_fields: [],
  history: [],
  latest_update: null,
  ...over,
});

const timed = toCampusEvent(api({}));
const noEnd = toCampusEvent(api({ event_id: "evt-2", local_end: null, local_start: "23:30" }));
const allDay = toCampusEvent(
  api({ event_id: "evt-3", local_start: null, local_date: "2026-11-13" }),
);
const undated = toCampusEvent(api({ event_id: "evt-4", local_date: null, local_start: null }));

describe("groupByDay", () => {
  it("groups by Vancouver date in order and puts undated events last", () => {
    const groups = groupByDay([allDay, undated, timed, noEnd]);
    expect(groups.map((g) => g.day)).toEqual(["2026-11-12", "2026-11-13", ""]);
    expect(groups[0]!.events.map((e) => e.id)).toEqual(["evt-1", "evt-2"]);
  });

  it("labels today, tomorrow and weekdays", () => {
    expect(dayLabel("2026-11-12", "2026-11-12")).toBe("Today");
    expect(dayLabel("2026-11-13", "2026-11-12")).toBe("Tomorrow");
    expect(dayLabel("2026-11-14", "2026-11-12")).toBe("Saturday");
    expect(dayLabel("", "2026-11-12")).toBe("Date TBD");
  });
});

describe("googleCalendarUrl", () => {
  it("uses Vancouver local times with an explicit time zone", () => {
    const url = new URL(googleCalendarUrl(timed, "https://quad.test")!);
    expect(url.searchParams.get("dates")).toBe("20261112T170000/20261112T180000");
    expect(url.searchParams.get("ctz")).toBe("America/Vancouver");
    expect(url.searchParams.get("location")).toBe("Demo Hall 101");
    expect(url.searchParams.get("details")).toContain("https://quad.test/events/evt-1");
  });

  it("defaults to one hour when the end is unknown and all-day when the time is unknown", () => {
    expect(new URL(googleCalendarUrl(noEnd)!).searchParams.get("dates")).toBe(
      "20261112T233000/20261112T235900",
    );
    const early = toCampusEvent(api({ local_end: null, local_start: "09:15" }));
    expect(new URL(googleCalendarUrl(early)!).searchParams.get("dates")).toBe(
      "20261112T091500/20261112T101500",
    );
    expect(new URL(googleCalendarUrl(allDay)!).searchParams.get("dates")).toBe("20261113/20261114");
    expect(googleCalendarUrl(undated)).toBeNull();
  });
});

describe("buildIcs", () => {
  it("writes one VEVENT per dated event with escaped text and CRLF line endings", () => {
    const ics = buildIcs(
      [timed, allDay, undated],
      "https://quad.test",
      new Date("2026-11-01T00:00:00Z"),
    );
    expect(ics.match(/BEGIN:VEVENT/g)).toHaveLength(2);
    expect(ics).toContain("DTSTART;TZID=America/Vancouver:20261112T170000\r\n");
    expect(ics).toContain("DTEND;TZID=America/Vancouver:20261112T180000\r\n");
    expect(ics).toContain("DTSTART;VALUE=DATE:20261113\r\n");
    expect(ics).toContain("SUMMARY:Intro to Git\\; part 1\\, hands-on\r\n");
    expect(ics).toContain("UID:evt-1@quad.ubc\r\n");
    expect(ics.endsWith("END:VCALENDAR\r\n")).toBe(true);
  });

  it("folds long lines at 75 octets", () => {
    const ics = buildIcs([timed], "https://quad.test");
    for (const line of ics.split("\r\n"))
      expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75);
    expect(ics).toMatch(/\r\n [^\r\n]/);
  });

  it("builds safe file names", () => {
    expect(icsFilename("Intro to Git; part 1, hands-on")).toBe("intro-to-git-part-1-hands-on.ics");
    expect(icsFilename("???")).toBe("event.ics");
  });
});
