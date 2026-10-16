"use client";

import { useEffect } from "react";
import { Check } from "lucide-react";

export type ToastMsg = { id: number; text: string };

/** Brief confirmation after a decision. Announced politely; gone after a few seconds. */
export function Toast({ msg, onDone }: { msg: ToastMsg | null; onDone: () => void }) {
  useEffect(() => {
    if (!msg) return;
    const id = setTimeout(onDone, 2500);
    return () => clearTimeout(id);
  }, [msg, onDone]);
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-36 z-50 flex justify-center">
      {msg && (
        <p key={msg.id} className="flex items-center gap-2 rounded-lg bg-ink px-4 py-2.5 text-base font-medium text-bg shadow-lg motion-safe:animate-toast">
          <Check aria-hidden className="size-4" />
          {msg.text}
        </p>
      )}
    </div>
  );
}
