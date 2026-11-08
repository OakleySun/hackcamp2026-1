import type { ReactNode } from "react";
import { dayDate, dayLabel, type DayGroup } from "@/lib/calendar";
import { vancouverToday, type CampusEvent } from "@/lib/events";

/** Day-grouped list with a dashed rail: one dot and heading per day, cards on the right. */
export function Timeline({
  groups,
  renderEvent,
  today = vancouverToday(),
}: {
  groups: DayGroup[];
  renderEvent: (e: CampusEvent) => ReactNode;
  today?: string;
}) {
  return (
    <ol className="timeline">
      {groups.map(({ day, events }) => {
        const label = dayLabel(day, today);
        const date = dayDate(day);
        return (
          <li key={day || "tbd"} className="tl-day" data-today={day === today}>
            <div className="tl-date">
              <p className="tl-weekday">{date || label}</p>
              {date && <p className="tl-sub">{label}</p>}
            </div>
            <ul className="grid gap-3">
              {events.map((e) => (
                <li key={e.id}>{renderEvent(e)}</li>
              ))}
            </ul>
          </li>
        );
      })}
    </ol>
  );
}
