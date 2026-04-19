"""Database schema definition for DeltaCodeCube."""

SCHEMA_SQL = """
-- =============================================================================
-- DeltaCodeCube Tables
-- =============================================================================

-- Code points: Representation of code files in 63D feature space
CREATE TABLE IF NOT EXISTS code_points (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL UNIQUE,
    function_name TEXT,

    -- Features stored as JSON arrays
    lexical_features TEXT NOT NULL,      -- JSON array [50 floats]
    structural_features TEXT NOT NULL,   -- JSON array [8 floats]
    semantic_features TEXT NOT NULL,     -- JSON array [5 floats]

    -- Metadata
    content_hash TEXT NOT NULL,
    line_count INTEGER NOT NULL DEFAULT 0,
    dominant_domain TEXT,

    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Contracts: Dependencies between code points
CREATE TABLE IF NOT EXISTS contracts (
    id TEXT PRIMARY KEY,
    caller_id TEXT NOT NULL REFERENCES code_points(id) ON DELETE CASCADE,
    callee_id TEXT NOT NULL REFERENCES code_points(id) ON DELETE CASCADE,
    contract_type TEXT NOT NULL CHECK (contract_type IN ('import', 'call', 'inherit')),

    baseline_distance REAL NOT NULL,

    created_at TEXT DEFAULT (datetime('now')),

    UNIQUE(caller_id, callee_id)
);

-- Deltas: History of code point movements
CREATE TABLE IF NOT EXISTS deltas (
    id TEXT PRIMARY KEY,
    code_point_id TEXT NOT NULL REFERENCES code_points(id) ON DELETE CASCADE,

    old_position TEXT NOT NULL,          -- JSON array [63 floats]
    new_position TEXT NOT NULL,          -- JSON array [63 floats]

    movement_magnitude REAL NOT NULL,
    lexical_change REAL NOT NULL,
    structural_change REAL NOT NULL,
    semantic_change REAL NOT NULL,
    dominant_change TEXT NOT NULL,

    created_at TEXT DEFAULT (datetime('now'))
);

-- Tensions: Detected contract violations
CREATE TABLE IF NOT EXISTS tensions (
    id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    delta_id TEXT NOT NULL REFERENCES deltas(id) ON DELETE CASCADE,

    tension_magnitude REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'detected'
        CHECK (status IN ('detected', 'reviewed', 'resolved', 'ignored')),

    suggested_action TEXT,

    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_code_points_path ON code_points(file_path);
CREATE INDEX IF NOT EXISTS idx_code_points_domain ON code_points(dominant_domain);
CREATE INDEX IF NOT EXISTS idx_contracts_caller ON contracts(caller_id);
CREATE INDEX IF NOT EXISTS idx_contracts_callee ON contracts(callee_id);
CREATE INDEX IF NOT EXISTS idx_deltas_code_point ON deltas(code_point_id);
CREATE INDEX IF NOT EXISTS idx_tensions_status ON tensions(status);
CREATE INDEX IF NOT EXISTS idx_tensions_contract ON tensions(contract_id);
"""
