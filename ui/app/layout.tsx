import type { Metadata } from "next";
import { Figtree, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { DATA_LABEL } from "@/lib/labels";

// OpenAI's site uses OpenAI Sans, a proprietary face licensed only to OpenAI. Figtree (SIL OFL) is the
// closest open match to its geometric-but-rounded character.
const sans = Figtree({ variable: "--font-ui", subsets: ["latin"] });
const mono = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Relay · Recovery Console",
  description: "Long-horizon recovery agent for the six weeks after a storm.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} antialiased`}>
      <body className="flex min-h-screen flex-col font-sans text-sm lg:h-screen lg:overflow-hidden">
        <a href="#main" className="sr-only z-50 bg-surface px-3 py-2 font-medium text-agent focus:not-sr-only focus:absolute focus:left-2 focus:top-2">
          Skip to main content
        </a>
        <p role="note" className="shrink-0 bg-ink px-4 py-1 text-center text-xs text-bg">
          {DATA_LABEL}
        </p>
        {children}
      </body>
    </html>
  );
}
