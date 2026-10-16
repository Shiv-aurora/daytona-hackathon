"use client";

import { Pause, Play, SkipForward } from "lucide-react";
import { cn } from "@/lib/utils";

const btn = "inline-flex h-8 items-center gap-1 rounded-md border bg-surface px-2 text-sm font-medium hover:border-agent hover:text-agent disabled:pointer-events-none disabled:opacity-40";

/** Presenter controls for the playback clock. Everything on screen follows the clock. */
export function SimControls({ playing, atHead, canNeedle, onPlay, onStep, onNeedle }: {
  playing: boolean;
  atHead: boolean;
  canNeedle: boolean;
  onPlay: (play: boolean) => void;
  onStep: (hours: number) => void;
  onNeedle: () => void;
}) {
  return (
    <div role="group" aria-label="Simulated time controls" className="flex items-center gap-1">
      <button
        className={cn(btn, "w-8 justify-center px-0", playing && "border-agent bg-agent text-primary-foreground hover:text-primary-foreground")}
        onClick={() => onPlay(!playing)}
        disabled={atHead && !playing}
        aria-label={playing ? "Pause" : "Play"}
        aria-keyshortcuts="P"
        title={playing ? "Pause (P)" : "Play (P)"}
      >
        {playing ? <Pause aria-hidden className="size-4" /> : <Play aria-hidden className="size-4" />}
      </button>
      <button className={btn} onClick={() => onStep(24)} disabled={atHead}>
        +1 day
      </button>
      <button className={btn} onClick={() => onStep(24 * 7)} disabled={atHead}>
        +1 week
      </button>
      <button className={btn} onClick={onNeedle} disabled={!canNeedle} aria-keyshortcuts="N" title="Jump to the next planted situation (N)">
        <SkipForward aria-hidden className="size-4" /> Next needle
      </button>
    </div>
  );
}
