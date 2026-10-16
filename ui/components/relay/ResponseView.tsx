"use client";

import { FileText, HandHeart, Home, Info, Package, Pill as PillIcon, Siren, Truck, Utensils, Wrench, X, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { STATUSES, STATUS_META, categoryLabel, conditionLabel, householdOf, orgName, relTime, sortRequests } from "@/lib/relay/selectors";
import type { Board, RelayRequest } from "@/lib/relay/types";
import { ActionButton, Callout, Card, EmptyState, LoadingBlock, Select, StatusBadge, Textarea } from "./ui";

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
    <Card className="p-3">
      <form onSubmit={submit} className="flex flex-col gap-2 @2xl:flex-row @2xl:items-center">
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
          placeholder="What does this household need? One request is made per need."
          rows={1}
          className="min-h-9 flex-1 resize-none"
        />
        <ActionButton type="submit" busy={pending} disabled={!text.trim()}>
          <FileText aria-hidden /> File report
        </ActionButton>
      </form>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>Try</span>
        <button type="button" className="rounded-md border border-line px-2 py-0.5 hover:bg-muted" onClick={() => setText(SAMPLE_REPORT)}>
          Food + supplies
        </button>
        <button
          type="button"
          className="rounded-md border border-promise-lapsed/40 px-2 py-0.5 text-promise-lapsed hover:bg-promise-lapsed/10"
          onClick={() => setText(SAMPLE_EMERGENCY)}
        >
          Emergency test
        </button>
      </div>
    </Card>
  );
}

function RequestCard({ request, board }: { request: RelayRequest; board: Board }) {
  const { selectRequest, selectedRequestId, now } = useRelay();
  const household = householdOf(board, request.survivor_id);
  const selected = selectedRequestId === request.id;
  const tip = [
    request.conditions?.length ? request.conditions.map((c) => conditionLabel(c)).join(", ") : null,
    request.promised_at && request.status === "claimed" ? relTime(request.promised_at, now) : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <li>
      <button
        type="button"
        onClick={() => selectRequest(selected ? null : request.id)}
        aria-pressed={selected}
        aria-label={`${categoryLabel(request.category)} request, ${household?.display_name ?? "unknown household"}, ${STATUS_META[request.status].label}`}
        title={tip || undefined}
        className={cn(
          "w-full space-y-2.5 rounded-lg border bg-surface p-3 text-left outline-none transition hover:border-agent/50 hover:shadow-sm focus-visible:ring-3 focus-visible:ring-ring/50",
          selected ? "border-agent shadow-sm ring-2 ring-agent/30" : "border-line",
        )}
      >
        <span className="flex items-center gap-3">
          <span aria-hidden className="grid size-9 shrink-0 place-items-center rounded-md bg-agent/10 text-agent">
            <CategoryIcon category={request.category} className="size-5" />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium text-ink">{household?.display_name ?? "Unknown household"}</span>
            <span className="block truncate text-xs text-muted-foreground">{categoryLabel(request.category)}</span>
          </span>
        </span>
        <span className="flex items-center justify-between gap-2">
          <span className="truncate rounded-md border border-line px-1.5 py-0.5 text-[11px] text-muted-foreground">
            {request.organization_id ? orgName(board, request.organization_id) : "Unassigned"}
          </span>
          <StatusBadge status={request.status} />
        </span>
      </button>
    </li>
  );
}

export function ResponseView() {
  const { board, connection, escalation, setEscalation, orgId } = useRelay();
  const [category, setCategory] = useState("all");
  const [mineOnly, setMineOnly] = useState(false);

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

  return (
    <div className="@container space-y-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">Response</h1>
        <p className="text-sm text-muted-foreground">
          <span className="tabular-nums">{count}</span> request{count === 1 ? "" : "s"} · {board.disaster.name}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2 @xl:grid-cols-5" aria-label="Request counts">
        {STATUSES.map((s) => (
          <Card key={s} title={STATUS_META[s].hint} className="flex items-center gap-3 px-3 py-2">
            <span className="text-2xl font-semibold leading-none tabular-nums text-ink">{board.requests.filter((r) => r.status === s).length}</span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span aria-hidden className={cn("size-2 rounded-full", STATUS_META[s].dot)} />
              {STATUS_META[s].label}
            </span>
          </Card>
        ))}
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
              "rounded-md border px-2.5 py-1 text-xs font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
              category === c ? "border-agent bg-agent text-white" : "border-line bg-surface text-muted-foreground hover:bg-muted",
            )}
          >
            {c === "all" ? "All" : categoryLabel(c)}
          </button>
        ))}
        <label className="ml-2 flex items-center gap-1.5 text-xs text-muted-foreground" title="Show only requests assigned to the acting organization">
          <input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} className="accent-[var(--agent)]" />
          Mine only
        </label>
        <span
          className="ml-auto text-[11px] text-muted-foreground"
          title="Relay sorts work by deadline and status. People are never ranked."
        >
          Sorted by deadline · never by person
        </span>
      </div>

      {count === 0 ? (
        <EmptyState icon={HandHeart} title="No requests yet" />
      ) : (
        <div className="grid gap-3 @xl:grid-cols-2 @4xl:grid-cols-3 @6xl:grid-cols-5">
          {STATUSES.map((status) => {
            const items = visible.filter((r) => r.status === status);
            return (
              <section key={status} aria-labelledby={`col-${status}`} className="space-y-2 rounded-lg bg-muted/50 p-2">
                <h2
                  id={`col-${status}`}
                  title={STATUS_META[status].hint}
                  className="flex items-center gap-2 px-1 pt-1 text-xs font-medium text-ink"
                >
                  <span aria-hidden className={cn("size-2 rounded-full", STATUS_META[status].dot)} />
                  {STATUS_META[status].label}
                  <span className="rounded-full bg-surface px-1.5 text-[11px] tabular-nums text-muted-foreground">{items.length}</span>
                </h2>
                {items.length ? (
                  <ul className="space-y-2">
                    {items.map((r) => (
                      <RequestCard key={r.id} request={r} board={board} />
                    ))}
                  </ul>
                ) : (
                  <p className="px-1 pb-2 text-xs text-muted-foreground">None</p>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
