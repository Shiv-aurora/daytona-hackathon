// Simulated clock. Contract: every ts is HOURS since the run's day 0 (RunMeta.day0, an ISO timestamp).
const NY = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export const SCENARIO_HOURS = 43 * 24; // six weeks: days 0-42

function parts(day0: string, ts: number) {
  const p = Object.fromEntries(NY.formatToParts(new Date(Date.parse(day0) + ts * 3_600_000)).map((x) => [x.type, x.value]));
  return { date: `${p.weekday} ${p.month} ${p.day}`, time: `${p.hour}:${p.minute}` };
}

export const simDay = (ts: number) => Math.floor(ts / 24);

/** "Day 13 · Wed Sep 15 · 10:24" (New York time). */
export function fmtClock(day0: string, ts: number) {
  const p = parts(day0, ts);
  return `Day ${simDay(ts)} · ${p.date} · ${p.time}`;
}

/** "Sep 15 10:24" for compact rows. */
export function fmtShort(day0: string, ts: number) {
  const p = parts(day0, ts);
  return `${p.date.split(" ").slice(1).join(" ")} ${p.time}`;
}

/** Hours -> "45m", "18h", "2d 9h". */
export function fmtHours(hours: number) {
  const h = Math.abs(hours);
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 48) return `${Math.floor(h)}h`;
  const d = Math.floor(h / 24);
  const rest = Math.round(h - d * 24);
  return rest ? `${d}d ${rest}h` : `${d}d`;
}
