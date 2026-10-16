"use client";

import { Info, Radio } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRelay } from "@/lib/relay/context";
import { categoryLabel, relTime } from "@/lib/relay/selectors";
import { CategoryIcon } from "./ResponseView";
import { Card, LoadingBlock, Pill } from "./ui";

export function OrganizationsView() {
  const { board, orgId, setOrgId, selectRequest, now, connection } = useRelay();
  if (!board) return connection === "error" ? null : <LoadingBlock label="Loading organizations…" />;

  return (
    <div className="@container space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold text-ink">Organizations</h1>
        <span title="Choosing an organization only changes who the demo acts as. Not production authorization.">
          <Pill tone="neutral" icon={Info}>
            Simulated access
          </Pill>
        </span>
      </div>

      <div className="grid gap-3 @3xl:grid-cols-3">
        {board.organizations.map((org) => {
          const mine = board.requests.filter((r) => r.organization_id === org.id);
          const active = mine.filter((r) => r.status === "claimed" || r.status === "awaiting_verification" || r.status === "reopened");
          const resolved = mine.filter((r) => r.status === "resolved").length;
          const acting = org.id === orgId;
          return (
            <Card key={org.id} className={acting ? "space-y-3 rounded-lg border-agent p-4 ring-2 ring-agent/30" : "space-y-3 rounded-lg p-4"}>
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-sm font-semibold text-ink">{org.name}</h2>
                  <p className="text-xs text-muted-foreground">{org.region}</p>
                </div>
                {acting ? <Pill tone="teal">Acting as</Pill> : null}
              </div>

              <div className="flex flex-wrap gap-1.5">
                {org.capabilities.map((c) => (
                  <span
                    key={c}
                    role="img"
                    title={categoryLabel(c)}
                    aria-label={categoryLabel(c)}
                    className="inline-flex size-7 items-center justify-center rounded-md border border-line text-agent"
                  >
                    <CategoryIcon category={c} className="size-3.5" />
                  </span>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-md bg-muted/60 px-3 py-2">
                  <p className="text-2xl font-semibold tabular-nums text-ink">{active.length}</p>
                  <p className="text-xs text-muted-foreground">active</p>
                </div>
                <div className="rounded-md bg-muted/60 px-3 py-2">
                  <p className="text-2xl font-semibold tabular-nums text-ink">{resolved}</p>
                  <p className="text-xs text-muted-foreground">resolved</p>
                </div>
              </div>

              {active.length ? (
                <ul className="divide-y divide-line rounded-md border border-line">
                  {active.map((r) => (
                    <li key={r.id}>
                      <button
                        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                        onClick={() => selectRequest(r.id)}
                      >
                        <span className="font-medium text-ink">{categoryLabel(r.category)}</span>
                        <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                          {r.status === "claimed" ? relTime(r.promised_at, now) : r.status === "awaiting_verification" ? "delivery reported" : "reopened"}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}

              {!acting ? (
                <Button variant="outline" size="sm" className="w-full" aria-label={`Act as ${org.name}`} onClick={() => setOrgId(org.id)}>
                  Act as
                </Button>
              ) : null}
            </Card>
          );
        })}
      </div>

      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Radio aria-hidden className="size-3.5" />
        Dispatch, radio, 211 feeds: out of scope, not connected
      </p>
    </div>
  );
}
