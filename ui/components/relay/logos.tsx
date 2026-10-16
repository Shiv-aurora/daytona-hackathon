// Brand marks for the services Relay plugs into, inlined so the graph renders offline and themes cleanly.
// Sources: ElevenLabs and SurrealDB from Simple Icons (CC0); Groq, Daytona and Arize from each company's own site.
// Used only to show which service runs each step.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;

export function ElevenLabsLogo(props: P) {
  return (
    <svg viewBox="0 0 24 24" role="img" aria-label="ElevenLabs" {...props}>
      <path fill="currentColor" d="M4.6035 0v24h4.9317V0zm9.8613 0v24h4.9317V0z" />
    </svg>
  );
}

export function GroqLogo(props: P) {
  return (
    <svg viewBox="0.54 0.39 32 32" role="img" aria-label="Groq" {...props}>
      <rect x="0.54" y="0.39" width="32" height="32" rx="7" fill="#F43E01" />
      <path fill="#fff" d="m18.445 4.406-9.468 13.74 7.341.665-1.69 9.578 9.469-13.74-7.342-.664 1.69-9.579Z" />
    </svg>
  );
}

export function DaytonaLogo(props: P) {
  return (
    <svg viewBox="0 0 275 287" role="img" aria-label="Daytona" {...props}>
      <path fill="currentColor" d="M14.5584 193.736H114.275V227.925H14.5584V193.736Z" />
      <path fill="currentColor" d="M148.464 74.076H262.426V108.265H148.464V74.076Z" />
      <path fill="currentColor" d="M88.6338 84.6127L173.246 0L197.422 24.175L112.809 108.788L88.6338 84.6127Z" />
      <path fill="currentColor" d="M89.157 170.084L24.175 105.102L0 129.277L64.9819 194.259L89.157 170.084Z" />
      <path fill="currentColor" d="M174.629 217.911L106.133 286.407L81.9577 262.232L150.454 193.736L174.629 217.911Z" />
      <path fill="currentColor" d="M174.106 132.44L250.66 208.994L274.835 184.819L198.281 108.265L174.106 132.44Z" />
      <path fill="currentColor" d="M88.6338 48.434V131.057H54.4451L54.4451 48.434H88.6338Z" />
      <path fill="currentColor" d="M208.294 168.094V270.66H174.106V168.094H208.294Z" />
    </svg>
  );
}

export function SurrealDBLogo(props: P) {
  return (
    <svg viewBox="0 0 24 24" role="img" aria-label="SurrealDB" {...props}>
      <path fill="#FF00A0" d="m12 6.314 5.714 3.165v-1.27L12 5.054c-.85.47-4.957 2.74-5.714 3.157.703.39 8.085 4.467 12.572 6.946v1.264L12 20.209c-1.71-.943-5.15-2.844-6.858-3.79v-3.788L12 16.42l1.144-.632-9.146-5.05v6.316L12 21.472l8-4.42v-2.526L8.57 8.21Zm-8.002.632v2.528l11.428 6.316-3.428 1.896-5.714-3.165v1.27l5.714 3.156c.85-.47 4.957-2.74 5.714-3.157-.703-.39-8.083-4.467-12.57-6.948V7.578L12 3.789c1.707.945 5.148 2.846 6.858 3.789v3.789L12 7.577l-1.144.633L20 13.263V6.946L12 2.526c-.791.438-7.416 4.1-8.002 4.42zM12 0 1.713 5.685v12.63L12 24l10.287-5.682V5.685Zm9.14 17.683L12 22.736l-9.143-5.053V6.317L12 1.264l9.143 5.053z" />
    </svg>
  );
}

export function ArizeLogo(props: P) {
  return (
    <svg viewBox="0 2.8 22.4 17.4" role="img" aria-label="Arize" {...props}>
      <path fill="#EA338A" d="M11.2118 3.34019C11.7889 3.30973 12.2955 3.59127 12.6629 4.1165C15.6246 8.35804 18.5853 12.5996 21.5367 16.8476C22.1463 17.7254 21.9515 18.7759 21.1183 19.3537C20.2981 19.9214 19.2005 19.6953 18.5732 18.7999C16.532 15.8848 14.5 12.9623 12.4644 10.0427C12.4273 9.98727 12.3901 9.93281 12.3512 9.87834C11.544 8.74296 10.746 8.74111 9.95365 9.8765C7.89757 12.823 5.84056 15.7685 3.79097 18.7196C3.45231 19.207 3.03943 19.5688 2.42984 19.6334C1.682 19.7137 1.08169 19.4516 0.687364 18.8026C0.283756 18.138 0.318086 17.4707 0.756952 16.8365C1.74231 15.415 2.73695 13.9999 3.72881 12.583C5.68376 9.78973 7.64334 6.99834 9.59272 4.20142C9.97035 3.65865 10.4463 3.32911 11.2118 3.34019Z" />
    </svg>
  );
}
