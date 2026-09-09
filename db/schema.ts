import { sql } from "drizzle-orm";
import { index, text, sqliteTable } from "drizzle-orm/sqlite-core";

export const projects = sqliteTable(
  "projects",
  {
    id: text("id").primaryKey(),
    ownerEmail: text("owner_email").notNull(),
    engineJobId: text("engine_job_id").notNull(),
    sourceUrl: text("source_url").notNull(),
    title: text("title").notNull().default("Novo projeto"),
    status: text("status").notNull().default("queued"),
    optionsJson: text("options_json").notNull().default("{}"),
    resultJson: text("result_json"),
    errorMessage: text("error_message"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    index("projects_owner_created_idx").on(table.ownerEmail, table.createdAt),
    index("projects_engine_job_idx").on(table.engineJobId),
  ],
);
