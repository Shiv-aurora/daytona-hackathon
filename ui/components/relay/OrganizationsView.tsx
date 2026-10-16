"use client";

import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { categoryLabel, relTime } from "@/lib/relay/selectors";
import { coverage, orgLoad } from "@/lib/relay/viz";
import { CategoryIcon } from "./ResponseView";
import { Legend, ProportionBar, statusSegments } from "./charts";
import { LoadingBlock, Monogram, PageHeader, Panel, StatusGlyph, shortOrg } from "./ui";

export function OrganizationsView() {
  const { board, orgId, setOrgId, selectRequest, now, connection } = useRelay();
  if (!board) return connection === "error" ? null : <LoadingBlock label="Loading organizations…" />;

  const cov = coverage(board);
  const loads = orgLoad(board);
  const cols = `minmax(7rem,1fr) repeat(${cov.orgs.length}, minmax(0,1fr)) 5.5rem`;

  return (
    <div className="@container space-y-5">
      <PageHeader
        title="Organizations"
        subtitle={
          <>
            <span className="num">{board.organizations.length}</span> volunteer organizations · {board.disaster.name}
          </>
        }
      />

      <Panel title="Coverage" aside={<span>Who can supply what, and what is waiting</span>} bodyClassName="p-0">
        <div role="table" aria-label="Capability coverage" className="text-sm">
          <div role="row" className="grid items-center gap-x-3 border-b border-line bg-surface px-3.5 py-2" style={{ gridTemplateColumns: cols }}>
            <span role="columnheader" className="label">
              Need
            </span>
            {cov.orgs.map((o) => (
              <span role="columnheader" key={o.id} className="flex min-w-0 items-center gap-1.5">
                <Monogram name={o.name} active={o.id === orgId} />
                <span className="truncate text-xs font-medium text-ink">{shortOrg(o.name)}</span>
              </span>
            ))}
            <span role="columnheader" className="label text-right">
              Waiting
            </span>
          </div>
          {cov.categories.map((cat) => {
            const waiting = cov.unclaimed[cat] ?? 0;
            const unmet = cov.unmet.includes(cat);
            return (
              <div role="row" key={cat} className="grid items-center gap-x-3 border-b border-line px-3.5 py-2.5 last:border-b-0" style={{ gridTemplateColumns: cols }}>
                <span role="rowheader" className="flex items-center gap-2 text-xs text-ink">
                  <CategoryIcon category={cat} className="size-3.5 text-muted-foreground" />
                  {categoryLabel(cat)}
                </span>
                {cov.orgs.map((o) => {
                  const cell = cov.cells[cat][o.id];
                  return (
                    <span role="cell" key={o.id} className="flex items-center gap-1.5">
                      {cell.capable ? (
                        <>
                          <span
                            aria-label={`${shortOrg(o.name)} can supply ${categoryLabel(cat).toLowerCase()}; ${cell.active} active, ${cell.resolved} resolved`}
                            className={cn("grid size-5 place-items-center rounded-full border text-[10px] font-medium", cell.active ? "border-agent bg-agent text-panel" : "border-agent/50 text-agent")}
                          >
                            {cell.active || ""}
                          </span>
                          {cell.resolved ? <span className="text-2xs text-muted-foreground">{cell.resolved} done</span> : null}
                        </>
                      ) : (
                        <span aria-label="cannot supply" className="h-px w-3 bg-line-strong" />
                      )}
                    </span>
                  );
                })}
                <span role="cell" className="text-right text-xs">
                  {unmet ? (
                    <span className="inline-flex items-center gap-1 font-medium text-promise-lapsed" title="Nobody seeded can supply this need">
                      <TriangleAlert aria-hidden className="size-3" /> no supplier
                    </span>
                  ) : waiting ? (
                    <span className="num font-medium text-ink">{waiting} open</span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
        <p className="border-t border-line px-3.5 py-2 text-2xs text-muted-foreground">Filled circle = requests this organization is working on now. Outline = can supply, nothing assigned.</p>
      </Panel>

      <Panel title="Workload" aside={<span>Requests each organization took on, by state</span>} bodyClassName="p-0">
        <ul className="divide-y divide-line">
          {loads.map((org) => {
            const mine = board.requests.filter((r) => r.organization_id === org.id && r.status !== "resolved" && r.status !== "open");
            const acting = org.id === orgId;
            return (
              <li key={org.id} className="space-y-2.5 px-3.5 py-3">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  <div className="flex min-w-48 flex-1 items-center gap-2.5">
                    <Monogram name={org.name} active={acting} className="size-6 text-xs" />
                    <div className="min-w-0 leading-tight">
                      <h2 className="truncate text-sm font-medium text-ink">{org.name}</h2>
                      <p className="truncate text-2xs text-muted-foreground">
                        {org.region} · {org.capabilities.map(categoryLabel).join(", ")}
                      </p>
                    </div>
                  </div>
                  <div className="w-full min-w-40 flex-[2] @3xl:w-auto">
                    <ProportionBar segments={statusSegments(org.counts)} height={8} label={`${org.name}: ${org.total} requests`} />
                    <p className="mt-1 text-2xs text-muted-foreground">
                      <span className="num font-medium text-ink">{org.total}</span> assigned
                      {org.completion === null ? "" : ` · ${Math.round(org.completion * 100)}% confirmed received`}
                    </p>
                  </div>
                  <div className="flex w-24 justify-end">
                    {acting ? (
                      <span className="inline-flex h-7 items-center gap-1.5 rounded-md border border-agent px-2.5 text-xs font-medium text-agent">
                        <span aria-hidden className="size-1.5 rounded-full bg-agent" /> Acting as
                      </span>
                    ) : (
                      <Button variant="outline" size="sm" aria-label={`Act as ${org.name}`} onClick={() => setOrgId(org.id)}>
                        Act as
                      </Button>
                    )}
                  </div>
                </div>
                {mine.length ? (
                  <ul className="ml-8 divide-y divide-line overflow-hidden rounded-md border border-line">
                    {mine.map((r) => (
                      <li key={r.id}>
                        <button className="flex w-full items-center gap-2.5 px-2.5 py-1.5 text-left text-sm outline-none transition-colors hover:bg-hover focus-visible:bg-hover" onClick={() => selectRequest(r.id)}>
                          <StatusGlyph status={r.status} />
                          <span className="font-medium text-ink">{categoryLabel(r.category)}</span>
                          <span className="ml-auto text-xs text-muted-foreground">
                            {r.status === "claimed" ? relTime(r.promised_at, now) : r.status === "awaiting_verification" ? "delivery reported" : "reopened"}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
        <div className="border-t border-line px-3.5 py-2">
          <Legend items={statusSegments(loads[0]?.counts ?? { open: 0, claimed: 0, awaiting_verification: 0, reopened: 0, resolved: 0 }).map((s) => ({ color: s.color, label: s.label }))} />
        </div>
      </Panel>
    </div>
  );
}
