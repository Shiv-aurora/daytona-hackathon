import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

// Plex: a civic, engineered grotesque with tabular figures by default. It reads like an instrument, not a landing page.
const sans = IBM_Plex_Sans({ variable: "--font-ui", subsets: ["latin"], weight: ["400", "500", "600"] });
const mono = IBM_Plex_Mono({ variable: "--font-data", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "Relay · Disaster recovery workspace",
  description: "Connect survivors with relief organizations, verify that help arrived, and reuse reviewed lessons.",
};

// Apply the saved theme before first paint so there is no light flash in dark mode.
const THEME_INIT = `try{var t=localStorage.getItem("relay-theme");if(t==="dark"||t==="light")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className={`${sans.variable} ${mono.variable} antialiased`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className="min-h-screen font-sans text-sm">
        <a href="#main" className="sr-only z-50 bg-panel px-3 py-2 font-medium text-agent focus:not-sr-only focus:absolute focus:left-2 focus:top-2">
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}
