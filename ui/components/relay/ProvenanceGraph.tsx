"use client";

// Verified outcomes (other disaster) → reviewed lesson → open requests here that it applies to.
// Only the lesson's own conditions are matched against this disaster's requests: no survivor record ever crosses.
import { ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { categoryLabel, conditionLabel, lessonStatus } from "@/lib/relay/selectors";
import type { Board, Lesson } from "@/lib/relay/types";
import { provenance, type ProvenanceLink } from "@/lib/relay/viz";
import { StatusGlyph } from "./ui";

const ROW = 46; // height reserved per outcome / request node
const NODE_H = 38;
const MID_H = 118;
const PAD = 14;

function receivedText(board: Board, id: string): string {
  const v = board.verifications.find((x) => x.id === id);
  if (!v) return "verified outcome";
  return v.received === true ? "received" : v.received === false ? "did not arrive" : "unconfirmed";
}

function LessonRow({ lesson, link, board, sourceName }: { lesson: Lesson; link: ProvenanceLink; board: Board; sourceName: string }) {
  const status = lessonStatus(lesson, board);
  const leftN = Math.max(1, link.outcomeIds.length);
  const rightN = Math.max(1, link.appliesTo.length);
  const H = Math.max(leftN * ROW, rightN * ROW, MID_H) + PAD * 2;
  const centre = H / 2;
  const colY = (i: number, n: number) => centre - (n * ROW) / 2 + i * ROW + ROW / 2;
  const L = { x0: 0, x1: 28 };
  const M = { x0: 37, x1: 63 };
  const R = { x0: 72, x1: 100 };
  const link2 = (y1: number, y2: number, xa: number, xb: number) => `M${xa} ${y1} C${xa + (xb - xa) / 2} ${y1} ${xa + (xb - xa) / 2} ${y2} ${xb} ${y2}`;

  const box = (key: string, x0: number, x1: number, y: number, h: number, children: ReactNode, className?: string) => (
    <div key={key} className={cn("absolute", className)} style={{ left: `${x0}%`, width: `${x1 - x0}%`, top: y - h / 2, height: h }}>
      {children}
    </div>
  );

  return (
    <div className="relative" style={{ height: H }}>
      <svg aria-hidden className="absolute inset-0 size-full" viewBox={`0 0 100 ${H}`} preserveAspectRatio="none">
        {link.outcomeIds.map((id, i) => (
          <path key={id} d={link2(colY(i, leftN), centre, L.x1, M.x0)} fill="none" stroke="var(--agent)" strokeOpacity="0.5" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        ))}
        {link.appliesTo.map((a, i) => (
          <path key={a.id} d={link2(centre, colY(i, rightN), M.x1, R.x0)} fill="none" stroke="var(--agent)" strokeOpacity="0.5" strokeWidth="1.5" strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
        ))}
      </svg>

      {link.outcomeIds.map((id, i) =>
        box(
          `o-${id}`,
          L.x0,
          L.x1,
          colY(i, leftN),
          NODE_H,
          <div className="flex h-full flex-col justify-center rounded-md border border-line bg-panel px-2.5" title={id}>
            <span className="truncate font-mono text-[10.5px] text-ink">{id}</span>
            <span className="truncate text-2xs text-muted-foreground">{receivedText(board, id)}</span>
          </div>,
        ),
      )}

      {box(
        "lesson",
        M.x0,
        M.x1,
        centre,
        MID_H,
        <div className={cn("flex h-full flex-col justify-between rounded-md border bg-panel p-3", status === "draft" ? "border-dashed border-line-strong" : "border-agent shadow-[0_0_0_3px_color-mix(in_srgb,var(--agent)_12%,transparent)]")}>
          <p className="line-clamp-3 text-[12.5px] font-medium leading-snug text-ink" title={lesson.recommendation}>
            {lesson.recommendation}
          </p>
          <p className="flex flex-wrap items-center gap-x-1.5 text-2xs text-muted-foreground">
            {status === "draft" ? <span>Draft · not shared</span> : (
              <span className="inline-flex items-center gap-1 font-medium text-agent">
                <ShieldCheck aria-hidden className="size-3" /> {status === "historical" ? "Approved" : "Approved here"}
              </span>
            )}
            {lesson.conditions.map((c) => (
              <span key={c}>· {conditionLabel(c)}</span>
            ))}
          </p>
        </div>,
      )}

      {link.appliesTo.length
        ? link.appliesTo.map((a, i) => {
            const req = board.requests.find((r) => r.id === a.id)!;
            return box(
              `a-${a.id}`,
              R.x0,
              R.x1,
              colY(i, rightN),
              NODE_H,
              <div className="flex h-full items-center gap-2 rounded-md border border-line bg-panel px-2.5">
                <StatusGlyph status={req.status} />
                <span className="min-w-0 leading-tight">
                  <span className="block truncate text-xs font-medium text-ink">{categoryLabel(a.category)}</span>
                  <span className="block truncate text-2xs text-muted-foreground">matches {a.matched.map(conditionLabel).join(", ")}</span>
                </span>
              </div>,
            );
          })
        : box(
            "none",
            R.x0,
            R.x1,
            centre,
            NODE_H,
            <div className="flex h-full items-center rounded-md border border-dashed border-line-strong px-2.5 text-2xs text-muted-foreground">
              {status === "draft" ? "Not shared until a person approves it" : status === "approved" ? "Shared to other disasters" : "Nothing open here matches"}
            </div>,
          )}
      <span className="sr-only">
        Lesson from {sourceName} cites {link.outcomeIds.length} verified outcomes and applies to {link.appliesTo.length} requests here.
      </span>
    </div>
  );
}

export function ProvenanceGraph() {
  const { board, disasters } = useRelay();
  if (!board) return null;
  const links = provenance(board);
  if (!links.length) return <p className="text-sm text-muted-foreground">No lessons yet. Verified outcomes become lessons after a person reviews them.</p>;
  const lessons = [...board.lessons].sort((a, b) => Number(b.approved) - Number(a.approved) || Date.parse(b.created_at) - Date.parse(a.created_at));
  const sourceName = (l: Lesson) => disasters.find((d) => d.id === l.source_disaster_id)?.name ?? l.source_disaster_id;
  const firstSource = lessons.find((l) => l.source_disaster_id !== board.disaster.id);
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[620px]">
        <div className="relative mb-1 grid h-5 text-2xs">
          <span className="label absolute left-0">Verified outcomes{firstSource ? ` · ${sourceName(firstSource)}` : ""}</span>
          <span className="label absolute" style={{ left: "37%" }}>
            Reviewed lesson
          </span>
          <span className="label absolute" style={{ left: "72%" }}>
            Applies to · {board.disaster.name}
          </span>
        </div>
        <div className="divide-y divide-line">
          {lessons.map((l) => (
            <LessonRow key={l.id} lesson={l} link={links.find((x) => x.lessonId === l.id)!} board={board} sourceName={sourceName(l)} />
          ))}
        </div>
      </div>
    </div>
  );
}
