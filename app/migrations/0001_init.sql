CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS users_email_idx ON users(email);

CREATE TABLE IF NOT EXISTS spots (
    id              TEXT PRIMARY KEY,
    owner_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    label           TEXT NOT NULL,
    description     TEXT,
    category        TEXT NOT NULL DEFAULT 'anders',
    visibility      TEXT NOT NULL DEFAULT 'private'
                    CHECK (visibility IN ('private', 'friends', 'public')),
    public_status   TEXT NOT NULL DEFAULT 'none'
                    CHECK (public_status IN ('none', 'requested', 'approved', 'denied', 'revoked')),
    denial_reason   TEXT,
    decided_by      TEXT REFERENCES users(id),
    decided_at      TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS spots_owner_idx ON spots(owner_id);
CREATE INDEX IF NOT EXISTS spots_visibility_idx ON spots(visibility);
CREATE INDEX IF NOT EXISTS spots_public_status_idx ON spots(public_status);

CREATE TABLE IF NOT EXISTS magic_link_tokens (
    token         TEXT PRIMARY KEY,
    email         TEXT NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    consumed_at   TIMESTAMP,
    expires_at    TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS magic_link_email_idx ON magic_link_tokens(email);
