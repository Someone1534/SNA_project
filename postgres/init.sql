CREATE TABLE IF NOT EXISTS app_users (
    id SERIAL PRIMARY KEY,
    telegram_username VARCHAR(64) NOT NULL UNIQUE,
    full_name VARCHAR(120) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backup_events (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    dump_filename VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL,
    size_mb NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO app_users (id, telegram_username, full_name, role)
VALUES
    (1, 'alice_admin', 'Alice Morgan', 'admin'),
    (2, 'bob_devops', 'Bob Smith', 'operator'),
    (3, 'carol_reader', 'Carol Lee', 'viewer')
ON CONFLICT (id) DO NOTHING;

INSERT INTO projects (id, owner_id, name, description, status)
VALUES
    (1, 1, 'Customer Portal', 'Demo web application database for backup tests.', 'active'),
    (2, 2, 'Analytics Service', 'Internal reporting service with PostgreSQL storage.', 'active'),
    (3, 1, 'Archive API', 'Legacy service kept for restore demonstrations.', 'maintenance')
ON CONFLICT (id) DO NOTHING;

INSERT INTO backup_events (id, project_id, dump_filename, status, size_mb)
VALUES
    (1, 1, 'backup_2026-05-12_10-00-00.dump', 'completed', 12.40),
    (2, 2, 'backup_2026-05-12_12-30-00.dump', 'completed', 18.75),
    (3, 3, 'backup_2026-05-12_15-15-00.dump', 'failed', 0.00)
ON CONFLICT (id) DO NOTHING;

SELECT setval(pg_get_serial_sequence('app_users', 'id'), COALESCE((SELECT MAX(id) FROM app_users), 1));
SELECT setval(pg_get_serial_sequence('projects', 'id'), COALESCE((SELECT MAX(id) FROM projects), 1));
SELECT setval(pg_get_serial_sequence('backup_events', 'id'), COALESCE((SELECT MAX(id) FROM backup_events), 1));
