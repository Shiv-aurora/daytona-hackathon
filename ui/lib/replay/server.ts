import "server-only";
import type { ReadDb } from "./snapshot";

// Direct database access from the UI was retired. The new UI will use the backend API.
export const replayConfigured = () => false;

export async function replayDb(): Promise<ReadDb> {
  throw new Error("Direct database replay is disabled; use the Relay backend API");
}
