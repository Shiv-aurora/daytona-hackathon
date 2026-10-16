-- Small demo aggregates: a request transition, evidence, replay ledger and events
-- commit together in one conditional write to its run/disaster record.
DEFINE TABLE IF NOT EXISTS relay_demo_config SCHEMALESS;
DEFINE TABLE IF NOT EXISTS relay_demo_run SCHEMALESS;
DEFINE INDEX IF NOT EXISTS relay_run_identity ON TABLE relay_demo_run COLUMNS run_id UNIQUE;
DEFINE TABLE IF NOT EXISTS relay_demo_lesson SCHEMALESS;
DEFINE INDEX IF NOT EXISTS relay_lesson_identity ON TABLE relay_demo_lesson COLUMNS lesson_id UNIQUE;
