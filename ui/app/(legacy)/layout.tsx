import { DATA_LABEL } from "@/lib/labels";

// The previous offline recovery console (/console, /call/*). Kept intact: its safety, isolation and replay
// tests still guard shared behavior. The demo workspace lives under (workspace).
export default function LegacyLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col lg:h-screen lg:overflow-hidden">
      <p role="note" className="shrink-0 bg-ink px-4 py-1 text-center text-xs text-bg">
        {DATA_LABEL}
      </p>
      {children}
    </div>
  );
}
