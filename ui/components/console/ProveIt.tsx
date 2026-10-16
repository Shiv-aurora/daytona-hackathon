import { FlaskConical } from "lucide-react";
import type { Comparison } from "@/lib/mock";

const W = 640;
const H = 260;
const PAD = { l: 44, r: 16, t: 16, b: 32 };
const pct = (v: number | null) => (v === null ? "no open promises" : `${Math.round(v * 100)}%`);

type Series = { name: string; values: (number | null)[]; stroke: string; dash?: string };

/** Promise recall by age: Relay vs the plain long-context baseline, straight from W4's evaluator. */
export function ProveIt({ comparison }: { comparison: Comparison | null | undefined }) {
  if (!comparison) {
    return (
      <section aria-labelledby="prove-title" className="grid flex-1 place-items-center p-8">
        <div className="max-w-md text-center">
          <FlaskConical aria-hidden className="mx-auto size-8 text-muted-foreground" />
          <h2 id="prove-title" className="mt-3 text-xl font-semibold">
            Not yet measured
          </h2>
          <p className="mt-1 text-base text-muted-foreground">The chart appears once the evaluator has scored Relay and the baseline on this scenario.</p>
        </div>
      </section>
    );
  }
  const buckets = comparison.relay.promise_recall.by_age;
  const base = new Map(comparison.baseline.promise_recall.by_age.map((b) => [b.label, b.recall]));
  const series: Series[] = [
    { name: "Relay", values: buckets.map((b) => b.recall), stroke: "var(--agent)" },
    { name: "Baseline (long context)", values: buckets.map((b) => base.get(b.label) ?? null), stroke: "var(--muted)", dash: "6 5" },
  ];
  const x = (i: number) => PAD.l + (buckets.length > 1 ? (i / (buckets.length - 1)) * (W - PAD.l - PAD.r) : 0);
  const y = (v: number) => PAD.t + (1 - v) * (H - PAD.t - PAD.b);
  const path = (vals: (number | null)[]) =>
    vals.map((v, i) => (v === null ? "" : `${i === 0 || vals[i - 1] === null ? "M" : "L"}${x(i)},${y(v)}`)).join(" ");

  return (
    <section aria-labelledby="prove-title" className="flex-1 overflow-y-auto p-6">
      <h2 id="prove-title" className="text-xl font-semibold">
        Promise recall by age
      </h2>
      <p className="text-base text-muted-foreground">Share of still-open promises each system names, by how long ago the promise was made.</p>
      <ul className="mt-3 flex gap-6 text-sm" aria-hidden>
        {series.map((s) => (
          <li key={s.name} className="flex items-center gap-2">
            <svg width="28" height="8">
              <line x1="0" x2="28" y1="4" y2="4" stroke={s.stroke} strokeWidth="3" strokeDasharray={s.dash} />
            </svg>
            {s.name}
          </li>
        ))}
      </ul>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full max-w-3xl" role="img" aria-label="Promise recall by age chart; values in the table below">
        {[0, 0.5, 1].map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="var(--border)" />
            <text x={PAD.l - 8} y={y(v) + 4} textAnchor="end" className="fill-muted-foreground text-xs">
              {v * 100}%
            </text>
          </g>
        ))}
        {buckets.map((b, i) => (
          <text key={b.label} x={x(i)} y={H - 10} textAnchor="middle" className="fill-muted-foreground text-xs">
            {b.label}
          </text>
        ))}
        {series.map((s) => (
          <g key={s.name}>
            <path d={path(s.values)} fill="none" stroke={s.stroke} strokeWidth="3" strokeDasharray={s.dash} strokeLinejoin="round" />
            {s.values.map((v, i) => v !== null && <circle key={i} cx={x(i)} cy={y(v)} r="4" fill={s.dash ? "var(--surface)" : s.stroke} stroke={s.stroke} strokeWidth="2" />)}
          </g>
        ))}
      </svg>
      <table className="sr-only">
        <caption>Promise recall by age</caption>
        <thead>
          <tr>
            <th>Promise age</th>
            {series.map((s) => (
              <th key={s.name}>{s.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {buckets.map((b, i) => (
            <tr key={b.label}>
              <td>{b.label}</td>
              {series.map((s) => (
                <td key={s.name}>{pct(s.values[i] ?? null)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
