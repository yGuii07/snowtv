import { drizzle } from "drizzle-orm/d1";
import type { AnyD1Database } from "drizzle-orm/d1";
import * as schema from "./schema";

type SnowRuntimeEnv = {
  DB?: AnyD1Database;
};

function getD1Database(): AnyD1Database {
  const env = (globalThis as typeof globalThis & { __SNOW_ENV__?: SnowRuntimeEnv }).__SNOW_ENV__;

  if (!env?.DB) {
    throw new Error(
      "Cloudflare D1 binding `DB` is unavailable. Start the interface through the SnowTV launcher or provide the `DB` binding in the runtime environment.",
    );
  }

  return env.DB;
}

export function getDb() {
  return drizzle(getD1Database(), { schema });
}

/**
 * Ensures the lightweight UI persistence schema exists.
 *
 * The local Vite/Cloudflare runtime starts with an empty D1 database on a
 * fresh clone. Creating the table and indexes here makes the project list
 * work on first run without requiring a separate migration command.
 */
export async function ensureDbSchema() {
  const d1 = getD1Database();

  await d1
    .prepare(`
      CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY NOT NULL,
        owner_email TEXT NOT NULL,
        engine_job_id TEXT NOT NULL,
        source_url TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT 'Novo projeto',
        status TEXT NOT NULL DEFAULT 'queued',
        options_json TEXT NOT NULL DEFAULT '{}',
        result_json TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    `)
    .run();

  await d1
    .prepare(
      "CREATE INDEX IF NOT EXISTS projects_owner_created_idx ON projects (owner_email, created_at)",
    )
    .run();

  await d1
    .prepare(
      "CREATE INDEX IF NOT EXISTS projects_engine_job_idx ON projects (engine_job_id)",
    )
    .run();
}
