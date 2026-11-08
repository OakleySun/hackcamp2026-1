import { describe, expect, it } from "vitest";
import { toCampusEvent, type ApiEvent } from "@/lib/api";
import {
  explore,
  formatAudience,
  forYou,
  hasPerks,
  isRestricted,
  passesPractical,
  topInterests,
  addDays,
  eventsOn,
  groupByPlace,
  nextDayWithEvents,
  prevDayWithEvents,
  vancouverToday,
} from "@/lib/events";
import { validateFilterSearch } from "@/lib/filters";

const api = (over: Partial<ApiEvent>): ApiEvent => ({
  event_id: "evt-1",
  club_id: "demo-campus-coding-club",
  club_name: "Demo Campus Coding Club",
  current_revision: 1,
  state: "published",
  title: "Intro to Git",
  local_date: "2026-11-12",
  local_start: "17:00",
  local_end: "18:00",
  venue: "Demo Hall 101",
  cost_status: "free",
  beginner_friendly: true,
  topics: ["tech"],
  rsvp_url: "https://example.org/rsvp",
  start_utc: "2026-11-13T01:00+00:00",
  sources: [{ source_id: "src-direct-form", source_url: "https://example.org/flyer/intro-to-git" }],
  unknown_fields: [],
  history: [],
  latest_update: null,
  ...over,
});

const EVENTS = [
  api({ perks: ["free_food", "free_swag", "not-a-perk"] }),
  api({ event_id: "evt-2", topics: ["academic"], local_date: "2026-11-13", perks: ["prizes"] }),
  api({ event_id: "evt-3", topics: ["career"], cost_status: "paid", local_date: "2026-11-14" }),
  api({ event_id: "evt-4", topics: ["arts"], cost_status: "unknown", beginner_friendly: null }),
  api({ event_id: "evt-5", topics: ["sports"], local_start: null }),
].map(toCampusEvent);

describe("API mapping", () => {
  it("maps backend fields onto the UI model", () => {
    const e = EVENTS[0]!;
    expect(e).toMatchObject({
      id: "evt-1",
      club: "Demo Campus Coding Club",
      topic: "tech",
      start: "2026-11-12T17:00",
      timeKnown: true,
      cost: "free",
      beginner: true,
    });
    expect(e.sources[0]).toEqual({
      label: "example.org/flyer/intro-to-git",
      url: "https://example.org/flyer/intro-to-git",
    });
  });
  it("missing start time is Time TBD", () => {
    expect(EVENTS[4]!.timeKnown).toBe(false);
  });
  it("only real corrections become changes, not first-time fills", () => {
    const e = toCampusEvent(
      api({
        history: [
          {
            revision: 2,
            changed: { local_end: { old: null, new: "18:00" } },
            confirmed_at: "2026-11-07T10:00:00+00:00",
          },
          {
            revision: 3,
            changed: { venue: { old: "Demo Hall 101", new: "Demo Hall 204" } },
            confirmed_at: "2026-11-07T11:00:00+00:00",
          },
        ],
      }),
    );
    expect(e.changes).toEqual([
      {
        field: "Venue",
        from: "Demo Hall 101",
        to: "Demo Hall 204",
        confirmedAt: "2026-11-07T11:00:00+00:00",
      },
    ]);
  });
});

describe("practical filters", () => {
  it("unknown price never passes Free", () => {
    expect(passesPractical(EVENTS[3]!, ["free"])).toBe(false);
  });
  it("unknown level never passes Beginner-friendly", () => {
    expect(passesPractical(EVENTS[3]!, ["beginner"])).toBe(false);
  });
  it("Time TBD never passes After 4 p.m.", () => {
    expect(passesPractical(EVENTS[4]!, ["after4"])).toBe(false);
  });
  it("explore picks respect practical filters and cap at three", () => {
    const picks = explore(EVENTS, ["tech"], ["free"], "surprise");
    expect(picks.length).toBeLessThanOrEqual(3);
    expect(picks.every((p) => p.event.cost === "free")).toBe(true);
  });
  it("stay close only suggests nearby topics", () => {
    const picks = explore(EVENTS, ["tech"], [], "close");
    expect(picks.length).toBeGreaterThan(0);
    expect(picks.every((p) => ["academic", "career"].includes(p.event.topic))).toBe(true);
  });
  it("for you only returns events in a chosen topic", () => {
    expect(forYou(EVENTS, ["tech"], []).map((r) => r.event.id)).toEqual(["evt-1"]);
  });
});

describe("perks", () => {
  it("keeps only known perks from the API", () => {
    expect(EVENTS[0]!.perks).toEqual(["free_food", "free_swag"]);
    expect(EVENTS[4]!.perks).toEqual([]);
  });
  it("an event must offer every selected perk", () => {
    expect(EVENTS.filter((e) => hasPerks(e, ["free_food"])).map((e) => e.id)).toEqual(["evt-1"]);
    expect(EVENTS.filter((e) => hasPerks(e, ["free_food", "prizes"]))).toEqual([]);
    expect(EVENTS.filter((e) => hasPerks(e, []))).toHaveLength(EVENTS.length);
  });
  it("added perks are not shown as corrections", () => {
    const e = toCampusEvent(
      api({
        history: [
          {
            revision: 2,
            changed: { perks: { old: [], new: ["free_food"] } },
            confirmed_at: "2026-11-07T10:00:00+00:00",
          },
        ],
      }),
    );
    expect(e.changes).toEqual([]);
  });
  it("the URL keeps valid perks only", () => {
    expect(validateFilterSearch({ perks: "free_food,bogus,prizes" }).perks).toBe(
      "free_food,prizes",
    );
  });
});

describe("top interests (Discover topic sections)", () => {
  const topics = (r: { topic: string }[]) => r.map((x) => x.topic);
  it("with no signals, shows the busiest topics", () => {
    const extra = toCampusEvent(api({ event_id: "evt-6", topics: ["sports"] }));
    expect(topics(topInterests([...EVENTS, extra], {}))).toEqual(["sports", "tech"]);
  });
  it("follows the profile's interests in order", () => {
    const r = topInterests(EVENTS, { profile: ["arts", "sports"] });
    expect(r).toEqual([
      { topic: "arts", why: "From your interests" },
      { topic: "sports", why: "From your interests" },
    ]);
  });
  it("topics picked on the page beat the profile", () => {
    expect(
      topics(topInterests(EVENTS, { chosen: ["career"], profile: ["arts", "sports"] })),
    ).toEqual(["career", "arts"]);
  });
  it("saved events pull their topic up", () => {
    const r = topInterests(EVENTS, { saved: [EVENTS[4]!] });
    expect(r[0]).toEqual({ topic: "sports", why: "You saved 1 Sports event" });
  });
  it("skips interests with nothing coming up", () => {
    expect(topics(topInterests(EVENTS, { profile: ["wellness", "arts"] }))).toEqual([
      "arts",
      "tech",
    ]);
  });
});

describe("who can go", () => {
  const ev = (audience: string[]) => toCampusEvent(api({ audience }));
  it("labels the groups and drops unknown ones", () => {
    expect(formatAudience(ev(["first_years", "cs_students", "aliens"]))).toBe(
      "1st-year students · Computer Science students",
    );
  });
  it("tells open, restricted and unstated apart", () => {
    expect(formatAudience(ev(["anyone"]))).toBe("Anyone");
    expect(isRestricted(ev(["anyone"]))).toBe(false);
    expect(isRestricted(ev(["women"]))).toBe(true);
    expect(formatAudience(ev([]))).toBe("Not listed");
    expect(isRestricted(ev([]))).toBe(false);
  });
  it("filling in the audience is not a correction", () => {
    const e = toCampusEvent(
      api({
        history: [
          {
            revision: 2,
            changed: { audience: { old: [], new: ["women"] } },
            confirmed_at: "2026-11-07T10:00:00+00:00",
          },
        ],
      }),
    );
    expect(e.changes).toEqual([]);
  });
});

describe("map helpers", () => {
  const at = (
    id: string,
    date: string,
    place: { id: string; name: string } | null,
    start = "17:00",
  ) =>
    toCampusEvent(
      api({
        event_id: id,
        local_date: date,
        local_start: start,
        place: place && { ...place, lat: 49.26, lng: -123.25 },
      }),
    );
  const icics = { id: "icics", name: "ICICS" };
  const nest = { id: "nest", name: "AMS Nest" };
  const evs = [
    at("a", "2026-11-12", icics, "18:00"),
    at("b", "2026-11-12", icics, "12:00"),
    at("c", "2026-11-12", nest),
    at("d", "2026-11-12", null),
    at("e", "2026-11-19", nest),
  ];
  it("today is the Vancouver date, not UTC", () => {
    expect(vancouverToday(new Date("2026-11-09T06:30:00Z"))).toBe("2026-11-08"); // 10:30 p.m. PST
  });
  it("steps across month ends", () => {
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
  });
  it("groups a day's events into one pin per building, in time order", () => {
    const { pins, unplaced } = groupByPlace(eventsOn(evs, "2026-11-12"));
    expect(pins.map((p) => [p.place.id, p.events.map((e) => e.id)])).toEqual([
      ["icics", ["b", "a"]],
      ["nest", ["c"]],
    ]);
    expect(unplaced.map((e) => e.id)).toEqual(["d"]);
  });
  it("finds the next and previous days with events", () => {
    expect(nextDayWithEvents(evs, "2026-11-08")).toBe("2026-11-12");
    expect(nextDayWithEvents(evs, "2026-11-19")).toBeNull();
    expect(prevDayWithEvents(evs, "2026-11-19", "2026-11-08")).toBe("2026-11-12");
    expect(prevDayWithEvents(evs, "2026-11-12", "2026-11-08")).toBeNull();
  });
});
