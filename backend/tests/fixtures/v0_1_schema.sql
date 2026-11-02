-- Frozen SQLite schema generated once from commit 53bf275.

-- Tests must not regenerate this fixture from current models or migration metadata.

CREATE TABLE goals (
	id VARCHAR(36) NOT NULL,
	title VARCHAR(200) NOT NULL,
	motivation TEXT NOT NULL,
	level VARCHAR(20) NOT NULL,
	daily_minutes INTEGER NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE units (
	id VARCHAR(36) NOT NULL,
	goal_id VARCHAR(36) NOT NULL,
	title VARCHAR(200) NOT NULL,
	objective TEXT NOT NULL,
	position INTEGER NOT NULL,
	stage VARCHAR(20) NOT NULL,
	mastery INTEGER NOT NULL,
	material JSON NOT NULL,
	review_due_at DATETIME,
	review_count INTEGER NOT NULL,
	review_streak INTEGER NOT NULL,
	version INTEGER NOT NULL,
	updated_at DATETIME NOT NULL,
	completed_at DATETIME,
	PRIMARY KEY (id),
	FOREIGN KEY(goal_id) REFERENCES goals (id) ON DELETE CASCADE
);

CREATE INDEX ix_units_goal_id ON units (goal_id);

CREATE INDEX ix_units_review_due_at ON units (review_due_at);

CREATE INDEX ix_units_stage ON units (stage);

CREATE TABLE knowledge_entries (
	id VARCHAR(36) NOT NULL,
	title VARCHAR(200) NOT NULL,
	content TEXT NOT NULL,
	source VARCHAR(255) NOT NULL,
	unit_id VARCHAR(36),
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(unit_id) REFERENCES units (id) ON DELETE SET NULL
);

CREATE INDEX ix_knowledge_entries_unit_id ON knowledge_entries (unit_id);

CREATE TABLE learning_sessions (
	id VARCHAR(36) NOT NULL,
	unit_id VARCHAR(36) NOT NULL,
	kind VARCHAR(20) NOT NULL,
	content TEXT NOT NULL,
	feedback TEXT NOT NULL,
	score INTEGER,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(unit_id) REFERENCES units (id) ON DELETE CASCADE
);

CREATE INDEX ix_learning_sessions_created_at ON learning_sessions (created_at);

CREATE INDEX ix_learning_sessions_unit_id ON learning_sessions (unit_id);
