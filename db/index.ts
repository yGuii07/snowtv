import { drizzle } from "drizzle-orm/d1";
import type { AnyD1Database } from "drizzle-orm/d1";
import * as schema from "./schema";

export function getDb() {
  const env = (globalThis as typeof globalThis & { __SNOW_ENV__?: { DB?: AnyD1Database } }).__SNOW_ENV__;
  if (!env?.DB) {
    throw new Error(
      "Cloudflare D1 binding `DB` is unavailable. Set the `d1` field in .openai/hosting.json to `DB` or provide the binding through the local/runtime environment."
    );
  }

  return drizzle(env.DB, { schema });
}
