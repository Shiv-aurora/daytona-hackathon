import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const sans = Geist({ variable: "--font-ui", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Relay · Disaster recovery workspace",
  description: "Connect survivors with relief organizations, verify that help arrived, and reuse reviewed lessons.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} antialiased`}>
      <body className="min-h-screen font-sans text-sm">
        <a href="#main" className="sr-only z-50 bg-surface px-3 py-2 font-medium text-agent focus:not-sr-only focus:absolute focus:left-2 focus:top-2">
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}
