import { Shell } from "@/components/relay/Shell";
import { RelayProvider } from "@/lib/relay/context";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <RelayProvider>
      <Shell>{children}</Shell>
    </RelayProvider>
  );
}
