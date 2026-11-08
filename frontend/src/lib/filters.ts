import { PERKS, PRACTICAL, TOPICS, type Perk, type Practical, type Topic } from "./events";

export type FilterSearch = {
  topics?: string | undefined;
  filters?: string | undefined;
  perks?: string | undefined;
};

const list = (v: unknown) => (typeof v === "string" && v ? v.split(",") : []);
const csv = (l: string[]) => (l.length ? l.join(",") : undefined);

export function validateFilterSearch(s: Record<string, unknown>): FilterSearch {
  return {
    topics: csv(list(s["topics"]).filter((t) => TOPICS.some((x) => x.slug === t))),
    filters: csv(list(s["filters"]).filter((t) => PRACTICAL.some((x) => x.key === t))),
    perks: csv(list(s["perks"]).filter((t) => PERKS.some((x) => x.key === t))),
  };
}

export const parseFilters = (s: FilterSearch) => ({
  topics: list(s["topics"]) as Topic[],
  practical: list(s["filters"]) as Practical[],
  perks: list(s["perks"]) as Perk[],
});

export const toggleIn = (value: string | undefined, v: string) => {
  const l = list(value);
  return csv(l.includes(v) ? l.filter((x) => x !== v) : [...l, v]);
};
