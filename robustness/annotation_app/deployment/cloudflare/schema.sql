CREATE TABLE IF NOT EXISTS responses (
  paper_id TEXT NOT NULL,
  annotator TEXT NOT NULL,
  analysis_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (paper_id, annotator, analysis_id)
);

-- Papers each annotator may open; enforced only when ENFORCE_ASSIGNMENTS = "true".
CREATE TABLE IF NOT EXISTS assignments (
  annotator TEXT NOT NULL,
  paper_id TEXT NOT NULL,
  PRIMARY KEY (annotator, paper_id)
);

-- First and last time each annotator loaded each paper's review page (packet requests); answers are not touched.
CREATE TABLE IF NOT EXISTS visits (
  annotator TEXT NOT NULL,
  paper_id TEXT NOT NULL,
  first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  loads INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (annotator, paper_id)
);
