CREATE TABLE `projects` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_email` text NOT NULL,
	`engine_job_id` text NOT NULL,
	`source_url` text NOT NULL,
	`title` text DEFAULT 'Novo projeto' NOT NULL,
	`status` text DEFAULT 'queued' NOT NULL,
	`options_json` text DEFAULT '{}' NOT NULL,
	`result_json` text,
	`error_message` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE INDEX `projects_owner_created_idx` ON `projects` (`owner_email`,`created_at`);--> statement-breakpoint
CREATE INDEX `projects_engine_job_idx` ON `projects` (`engine_job_id`);