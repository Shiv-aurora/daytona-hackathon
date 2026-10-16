"use client";

import { FileText, HandHeart, Home, Info, KanbanSquare, List, Package, Pill as PillIcon, Siren, Truck, Utensils, Wrench, X, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { STATUSES, STATUS_META, categoryLabel, conditionLabel, householdOf, orgName, relTime, sortRequests } from "@/lib/relay/selectors";
import type { Board, RelayRequest, RequestStatus } from "@/lib/relay/types";
import { categoryBreakdown, claimedAt, countByStatus, funnel, promiseClock } from "@/lib/relay/viz";
import { CategoryBars, FunnelChart, JourneyLane, Legend, ProportionBar, statusSegments } from "./charts";
import { ActionButton, Callout, EmptyState, LoadingBlock, Monogram, PageHeader, Panel, Segmented, Select, StatusGlyph, Textarea, shortOrg } from "./ui";

const CATEGORY_ICON: Record<string, LucideIcon> = {
  food: Utensils,
  supplies: Package,
  transportation: Truck,
  shelter: Home,
  repairs: Wrench,
  medicine: PillIcon,
};
export function CategoryIcon({ category, className }: { category: string; className?: string }) {
  const Icon = CATEGORY_ICON[category] ?? Info;
  return <Icon aria-hidden className={className} />;
}

const SAMPLE_REPORT = "We need food and blankets for the family. The road is blocked so we can't get out.";
// Exercises the code-owned emergency path. Clearly labeled as a test; nothing is dispatched.
const SAMPLE_EMERGENCY = "My father fell down and can't get up.";

/* ------------------------------------------------------------------ KPI strip */

function Kpis({ board }: { board: Board }) {
  const counts = countByStatus(board.requests);
  const total = board.requests.length;
  const f = funnel(board.requests);
  return (
    <div aria-label="Request counts" className="grid grid-cols-2 overflow-hidden rounded-md border border-line bg-panel sm:grid-cols-3 lg:grid-cols-6 [&>*]:border-line [&>*:not(:first-child)]:lg:border-l [&>*]:border-b lg:[&>*]:border-b-0">
      {STATUSES.map((s) => (
        <div key={s} title={STATUS_META[s].hint} className="flex min-w-0 flex-col gap-2 px-4 py-3">
          <span className="label flex items-center gap-1.5 !normal-case !tracking-normal !text-xs !font-medium text-ink-2">
            <StatusGlyph status={s} size={13} />
            {STATUS_META[s].label}
          </span>
          <span className="num text-2xl font-medium leading-none tracking-[-0.02em] text-ink">{counts[s]}</span>
          <ProportionBar segments={[{ key: s, value: counts[s], color: STATUS_META[s].color, label: STATUS_META[s].label }, { key: "rest", value: total - counts[s], color: "transparent", label: "other" }]} height={3} />
        </div>
      ))}
      <div className="flex min-w-0 flex-col gap-2 bg-surface px-4 py-3" title="Of the requests an organization says it delivered, the share a household or a human confirmed received.">
        <span className="label !normal-case !tracking-normal !text-xs !font-medium text-ink-2">Confirmed received</span>
        <span className="flex items-baseline gap-1">
          <span className="num text-2xl font-medium leading-none tracking-[-0.02em] text-ink">{f.verifiedRate === null ? "—" : Math.round(f.verifiedRate * 100)}</span>
          {f.verifiedRate === null ? null : <span className="text-xs text-muted-foreground">%</span>}
        </span>
        <span className="text-2xs text-muted-foreground">{f.verifiedRate === null ? "Nothing delivered yet" : `of ${f.stages[2].count} delivered`}</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ composer */

function ReportForm({ board }: { board: Board }) {
  const { api, runId, act, busy, setEscalation } = useRelay();
  const [survivorId, setSurvivorId] = useState("");
  const [text, setText] = useState("");
  const chosen = survivorId || board.survivors[0]?.id || "";
  const pending = busy("report");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || !chosen) return;
    const result = await act(
      "report",
      (r) =>
        r.escalated
          ? "Emergency detected: a person has been alerted. No request was created."
          : `${r.requests.length} request${r.requests.length === 1 ? "" : "s"} created from the report.`,
      () => api.report(runId, { disaster_id: board.disaster.id, survivor_id: chosen, text }),
    );
    if (result?.escalated) setEscalation({ message: result.message ?? "" });
    if (result) setText("");
  }

  return (
    <div className="rounded-md border border-line bg-panel">
      <form onSubmit={submit} className="flex flex-col gap-2 p-2 @2xl:flex-row @2xl:items-start">
        <label htmlFor="report-survivor" className="sr-only">
          Report from
        </label>
        <Select id="report-survivor" value={chosen} onChange={(e) => setSurvivorId(e.target.value)} className="@2xl:w-48">
          {board.survivors.map((s) => (
            <option key={s.id} value={s.id}>
              {s.display_name}
            </option>
          ))}
        </Select>
        <label htmlFor="report-text" className="sr-only">
          What does this household need?
        </label>
        <Textarea
          id="report-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Log a report: what does this household need? One request is made per need."
          rows={1}
          className="min-h-8 flex-1 resize-none py-[5px]"
        />
        <ActionButton type="submit" busy={pending} disabled={!text.trim()}>
          <FileText aria-hidden /> File report
        </ActionButton>
      </form>
      <div className="flex flex-wrap items-center gap-1.5 border-t border-line px-3 py-1.5 text-2xs text-muted-foreground">
        <span>Try</span>
        <button type="button" className="rounded-[4px] border border-line px-1.5 py-px hover:bg-hover" onClick={() => setText(SAMPLE_REPORT)}>
          Food + supplies, road blocked
        </button>
        <button type="button" className="rounded-[4px] border border-line px-1.5 py-px text-promise-lapsed hover:bg-hover" onClick={() => setText(SAMPLE_EMERGENCY)}>
          Emergency test
        </button>
        <span className="ml-auto hidden sm:inline">Emergency wording is checked by code before anything else.</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ list rows */

function PromiseCell({ request, board, now }: { request: RelayRequest; board: Board; now: number }) {
  const clock = promiseClock(request, claimedAt(board, request), now);
  if (clock) {
    const pct = Math.min(1, clock.progress) * 100;
    return (
      <span className="flex min-w-0 flex-col gap-1">
        <span className="h-[3px] w-full overflow-hidden rounded-full bg-hover">
          <span className={cn("block h-full rounded-full", clock.overdue ? "bg-promise-lapsed" : "bg-promise-claimed")} style={{ width: `${pct}%` }} />
        </span>
        <span className={cn("truncate text-2xs", clock.overdue ? "font-medium text-promise-lapsed" : "text-muted-foreground")}>{relTime(request.promised_at, now)}</span>
      </span>
    );
  }
  const text: Record<RequestStatus, string> = {
    open: "Unclaimed",
    claimed: request.promised_at ? relTime(request.promised_at, now) : "No time promised",
    awaiting_verification: "Delivered · unverified",
    reopened: "Needs a person",
    resolved: "Confirmed received",
  };
  return <span className={cn("truncate text-2xs", request.status === "reopened" ? "font-medium text-promise-lapsed" : "text-muted-foreground")}>{text[request.status]}</span>;
}

function RequestRow({ request, board }: { request: RelayRequest; board: Board }) {
  const { selectRequest, selectedRequestId, now } = useRelay();
  const household = householdOf(board, request.survivor_id);
  const selected = selectedRequestId === request.id;
  const org = request.organization_id ? orgName(board, request.organization_id) : null;
  return (
    <li>
      <button
        type="button"
        onClick={() => selectRequest(selected ? null : request.id)}
        aria-pressed={selected}
        aria-label={`${categoryLabel(request.category)} request, ${household?.display_name ?? "unknown household"}, ${STATUS_META[request.status].label}`}
        className={cn(
          "grid w-full grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-3 px-3.5 py-2 text-left outline-none transition-colors @3xl:grid-cols-[1.5rem_minmax(0,1.4fr)_minmax(0,1fr)_92px_minmax(0,8.5rem)]",
          selected ? "bg-agent-soft" : "hover:bg-hover focus-visible:bg-hover",
        )}
      >
        <CategoryIcon category={request.category} className="size-4 text-muted-foreground" />
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium text-ink">{categoryLabel(request.category)}</span>
          <span className="block truncate text-2xs text-muted-foreground">
            {household?.display_name ?? "Unknown household"}
            {request.conditions?.length ? ` · ${request.conditions.map(conditionLabel).join(", ")}` : ""}
          </span>
        </span>
        <span className="hidden min-w-0 items-center gap-2 @3xl:flex">
          {org ? (
            <>
              <Monogram name={org} />
              <span className="truncate text-xs text-ink-2">{shortOrg(org)}</span>
            </>
          ) : (
            <span className="text-xs text-muted-foreground">Unassigned</span>
          )}
        </span>
        <span className="hidden @3xl:block">
          <JourneyLane request={request} />
        </span>
        <span className="min-w-0 text-right @3xl:text-left">
          <PromiseCell request={request} board={board} now={now} />
        </span>
      </button>
    </li>
  );
}

function GroupedList({ board, items }: { board: Board; items: RelayRequest[] }) {
  return (
    <div className="overflow-hidden rounded-md border border-line bg-panel">
      <div className="hidden grid-cols-[1.5rem_minmax(0,1.4fr)_minmax(0,1fr)_92px_minmax(0,8.5rem)] gap-x-3 border-b border-line bg-surface px-3.5 py-1.5 @3xl:grid">
        <span />
        <span className="label">Need</span>
        <span className="label">Organization</span>
        <span className="label" title="Requested → claimed → delivered → verified">
          Journey
        </span>
        <span className="label">Promise</span>
      </div>
      {STATUSES.map((status) => {
        const rows = items.filter((r) => r.status === status);
        if (!rows.length) return null;
        return (
          <section key={status} aria-labelledby={`grp-${status}`}>
            <h2 id={`grp-${status}`} title={STATUS_META[status].hint} className="flex items-center gap-2 border-b border-line bg-surface px-3.5 py-1.5 text-xs font-medium text-ink [&:not(:first-child)]:border-t">
              <StatusGlyph status={status} size={13} />
              {STATUS_META[status].label}
              <span className="num text-muted-foreground">{rows.length}</span>
              <span className="ml-1 hidden font-normal text-muted-foreground sm:inline">· {STATUS_META[status].hint}</span>
            </h2>
            <ul className="divide-y divide-line">
              {rows.map((r) => (
                <RequestRow key={r.id} request={r} board={board} />
              ))}
            </ul>
          </section>
        );
      })}
      {!items.length ? <p className="px-4 py-6 text-center text-sm text-muted-foreground">No requests match these filters.</p> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ board view */

function BoardCard({ request, board }: { request: RelayRequest; board: Board }) {
  const { selectRequest, selectedRequestId, now } = useRelay();
  const household = householdOf(board, request.survivor_id);
  const selected = selectedRequestId === request.id;
  return (
    <li>
      <button
        type="button"
        onClick={() => selectRequest(selected ? null : request.id)}
        aria-pressed={selected}
        aria-label={`${categoryLabel(request.category)} request, ${household?.display_name ?? "unknown household"}, ${STATUS_META[request.status].label}`}
        className={cn("w-full space-y-2 rounded-md border bg-panel p-2.5 text-left outline-none transition-colors", selected ? "border-agent bg-agent-soft" : "border-line hover:border-line-strong")}
      >
        <span className="flex items-center gap-2">
          <CategoryIcon category={request.category} className="size-3.5 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{categoryLabel(request.category)}</span>
        </span>
        <span className="block truncate text-2xs text-muted-foreground">{household?.display_name ?? "Unknown household"}</span>
        <JourneyLane request={request} width={110} />
        <span className="flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-1.5">
            {request.organization_id ? <Monogram name={orgName(board, request.organization_id)} /> : null}
            <span className="truncate text-2xs text-muted-foreground">{request.organization_id ? shortOrg(orgName(board, request.organization_id)) : "Unassigned"}</span>
          </span>
          <PromiseCell request={request} board={board} now={now} />
        </span>
      </button>
    </li>
  );
}

function BoardView({ board, items }: { board: Board; items: RelayRequest[] }) {
  return (
    <div className="grid gap-3 @xl:grid-cols-2 @4xl:grid-cols-3 @6xl:grid-cols-5">
      {STATUSES.map((status) => {
        const rows = items.filter((r) => r.status === status);
        return (
          <section key={status} aria-labelledby={`col-${status}`} className="space-y-2 rounded-md bg-surface p-2 ring-1 ring-line">
            <h2 id={`col-${status}`} title={STATUS_META[status].hint} className="flex items-center gap-2 px-1 pt-0.5 text-xs font-medium text-ink">
              <StatusGlyph status={status} size={13} />
              {STATUS_META[status].label}
              <span className="num text-muted-foreground">{rows.length}</span>
            </h2>
            {rows.length ? (
              <ul className="space-y-2">
                {rows.map((r) => (
                  <BoardCard key={r.id} request={r} board={board} />
                ))}
              </ul>
            ) : (
              <p className="px-1 pb-2 text-xs text-muted-foreground">None</p>
            )}
          </section>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ page */

export function ResponseView() {
  const { board, connection, escalation, setEscalation, orgId } = useRelay();
  const [category, setCategory] = useState("all");
  const [mineOnly, setMineOnly] = useState(false);
  const [view, setView] = useState<"list" | "board">("list");

  const categories = useMemo(() => [...new Set((board?.requests ?? []).map((r) => r.category))], [board]);
  const visible = useMemo(
    () =>
      sortRequests(board?.requests ?? []).filter(
        (r) => (category === "all" || r.category === category) && (!mineOnly || r.organization_id === orgId),
      ),
    [board, category, mineOnly, orgId],
  );

  if (!board) return connection === "error" ? null : <LoadingBlock label="Loading the request board…" />;

  const count = board.requests.length;
  const f = funnel(board.requests);
  const rows = categoryBreakdown(board.requests);

  return (
    <div className="@container space-y-5">
      <PageHeader
        title="Response"
        subtitle={
          <>
            <span className="num">{count}</span> request{count === 1 ? "" : "s"} · {board.disaster.name} · {board.disaster.region}
          </>
        }
        actions={
          <Segmented
            label="Layout"
            value={view}
            onChange={setView}
            options={[
              { value: "list", label: (<><List aria-hidden className="size-3.5" />List</>) },
              { value: "board", label: (<><KanbanSquare aria-hidden className="size-3.5" />Board</>) },
            ]}
          />
        }
      />

      <Kpis board={board} />

      <div className="grid gap-3 @4xl:grid-cols-[3fr_2fr]">
        <Panel title="Request funnel" aside={<span>Delivery is not receipt</span>}>
          <FunnelChart funnel={f} />
        </Panel>
        <Panel title="Needs by category" aside={<span className="num">{count} total</span>}>
          <CategoryBars rows={rows} />
          <Legend className="mt-3" items={statusSegments(countByStatus(board.requests)).map((s) => ({ color: s.color, label: s.label }))} />
        </Panel>
      </div>

      {escalation ? (
        <div title="Relay stopped automated handling and logged an immediate human escalation.">
          <Callout tone="danger" icon={Siren} role="alert" title="Emergency: a person was alerted">
            {escalation.message ? <p className="text-ink">{escalation.message}</p> : null}
            <p>No request created.</p>
            <button className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-ink underline underline-offset-2" onClick={() => setEscalation(null)}>
              <X aria-hidden className="size-3" /> Dismiss
            </button>
          </Callout>
        </div>
      ) : null}

      <ReportForm board={board} />

      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filters">
        {["all", ...categories].map((c) => (
          <button
            key={c}
            type="button"
            aria-pressed={category === c}
            onClick={() => setCategory(c)}
            className={cn(
              "h-6 rounded-[5px] border px-2 text-xs font-medium outline-none transition-colors",
              category === c ? "border-ink bg-ink text-panel" : "border-line bg-panel text-ink-2 hover:bg-hover",
            )}
          >
            {c === "all" ? "All" : categoryLabel(c)}
          </button>
        ))}
        <label className="ml-2 flex items-center gap-1.5 text-xs text-ink-2" title="Show only requests assigned to the acting organization">
          <input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} className="accent-[var(--agent)]" />
          Mine only
        </label>
        <span className="ml-auto text-2xs text-muted-foreground" title="Relay sorts work by deadline and status. People are never ranked.">
          Sorted by deadline · never by person
        </span>
      </div>

      {count === 0 ? <EmptyState icon={HandHeart} title="No requests yet" /> : view === "list" ? <GroupedList board={board} items={visible} /> : <BoardView board={board} items={visible} />}
    </div>
  );
}
