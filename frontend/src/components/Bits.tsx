/** Luma-style date leaf: month on a blue cap, day number underneath. */
export function DateLeaf({ day, size }: { day: string | null; size?: "lg" }) {
  if (!day) {
    return (
      <span className="date-leaf" data-size={size} aria-label="Date to be announced">
        <span className="leaf-month">TBD</span>
        <span className="leaf-day">?</span>
      </span>
    );
  }
  const d = new Date(`${day}T12:00:00Z`);
  const month = d.toLocaleDateString("en-CA", { month: "short", timeZone: "UTC" });
  return (
    <span className="date-leaf" data-size={size}>
      <span className="leaf-month">{month}</span>
      <span className="leaf-day">{d.getUTCDate()}</span>
    </span>
  );
}

const initials = (name: string) =>
  name
    .replace(/^(UBC|The)\s+/i, "")
    .split(/\s+/)
    .filter((w) => /^[A-Za-z0-9]/.test(w))
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");

/** Initials on UBC blue, where Luma shows the host's photo. */
export function ClubAvatar({ name, size }: { name: string; size?: "lg" }) {
  return (
    <span className="club-avatar" data-size={size} aria-hidden>
      {initials(name) || "?"}
    </span>
  );
}
