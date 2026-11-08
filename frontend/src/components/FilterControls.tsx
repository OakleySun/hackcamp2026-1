import { PERKS, PRACTICAL, TOPICS } from "@/lib/events";
import { parseFilters, toggleIn, type FilterSearch } from "@/lib/filters";
import { Check } from "lucide-react";

type ChipGroup = "practical" | "perks";

export function FilterControls({
  search,
  onChange,
  group = "practical",
}: {
  search: FilterSearch;
  onChange: (s: FilterSearch) => void;
  /** "practical" = Can I go? (used by alerts), "perks" = Free food / swag / prizes. */
  group?: ChipGroup;
}) {
  const { topics, practical, perks } = parseFilters(search);
  const chips =
    group === "perks"
      ? { legend: "Perks", key: "perks" as const, options: PERKS, on: perks as string[] }
      : {
          legend: "Can I go?",
          key: "filters" as const,
          options: PRACTICAL,
          on: practical as string[],
        };
  return (
    <div className="space-y-5">
      <fieldset>
        <legend className="eyebrow mb-2">Topics</legend>
        <div className="flex flex-wrap gap-2">
          {TOPICS.map((t) => {
            const on = topics.includes(t.slug);
            return (
              <button
                key={t.slug}
                type="button"
                aria-pressed={on}
                className="chip"
                data-on={on}
                onClick={() => onChange({ ...search, topics: toggleIn(search.topics, t.slug) })}
              >
                {on && <Check className="size-3.5" aria-hidden />}
                {t.label}
              </button>
            );
          })}
        </div>
      </fieldset>
      <div className="flex flex-col gap-5 md:flex-row md:gap-10">
        <fieldset>
          <legend className="eyebrow mb-2">{chips.legend}</legend>
          <div className="flex flex-wrap gap-2">
            {chips.options.map((p) => {
              const on = chips.on.includes(p.key);
              return (
                <button
                  key={p.key}
                  type="button"
                  aria-pressed={on}
                  className="chip chip-square"
                  data-on={on}
                  onClick={() =>
                    onChange({ ...search, [chips.key]: toggleIn(search[chips.key], p.key) })
                  }
                >
                  {on && <Check className="size-3.5" aria-hidden />}
                  {p.label}
                </button>
              );
            })}
          </div>
        </fieldset>
      </div>
    </div>
  );
}
