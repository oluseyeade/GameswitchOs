-- Paystack payment module schema migration
-- Created: 2026-07-19

CREATE TABLE IF NOT EXISTS payment_users (
    id VARCHAR(36) PRIMARY KEY,
    legacy_user_id INTEGER NOT NULL UNIQUE,
    email VARCHAR(180) NOT NULL UNIQUE,
    full_name VARCHAR(180) NOT NULL,
    phone VARCHAR(40) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    deleted_at TIMESTAMP NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_payment_users_is_active ON payment_users (is_active);
CREATE INDEX IF NOT EXISTS ix_payment_users_is_deleted ON payment_users (is_deleted);
CREATE INDEX IF NOT EXISTS ix_payment_users_legacy_user_id ON payment_users (legacy_user_id);

CREATE TABLE IF NOT EXISTS gaming_stations (
    id VARCHAR(36) PRIMARY KEY,
    code VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    branch VARCHAR(40) NOT NULL,
    tuya_switch_code VARCHAR(40) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    deleted_at TIMESTAMP NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_gaming_stations_branch ON gaming_stations (branch);
CREATE INDEX IF NOT EXISTS ix_gaming_stations_is_active ON gaming_stations (is_active);
CREATE INDEX IF NOT EXISTS ix_gaming_stations_is_deleted ON gaming_stations (is_deleted);

CREATE TABLE IF NOT EXISTS payment_gaming_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    station_id VARCHAR(36) NOT NULL,
    game_id INTEGER NOT NULL,
    branch VARCHAR(40) NOT NULL,
    duration_minutes INTEGER NOT NULL,
    amount_kobo INTEGER NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'NGN',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    payment_reference VARCHAR(64) NULL UNIQUE,
    legacy_session_id INTEGER NULL UNIQUE,
    started_at TIMESTAMP NULL,
    ended_at TIMESTAMP NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    deleted_at TIMESTAMP NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT fk_payment_session_user FOREIGN KEY (user_id) REFERENCES payment_users (id),
    CONSTRAINT fk_payment_session_station FOREIGN KEY (station_id) REFERENCES gaming_stations (id),
    CONSTRAINT ck_payment_session_duration_min CHECK (duration_minutes >= 10),
    CONSTRAINT ck_payment_session_amount_kobo CHECK (amount_kobo >= 100),
    CONSTRAINT ck_payment_session_status CHECK (status IN ('pending','active','ended','cancelled','failed'))
);

CREATE INDEX IF NOT EXISTS ix_payment_session_user_id ON payment_gaming_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_payment_session_station_id ON payment_gaming_sessions (station_id);
CREATE INDEX IF NOT EXISTS ix_payment_session_game_id ON payment_gaming_sessions (game_id);
CREATE INDEX IF NOT EXISTS ix_payment_session_status ON payment_gaming_sessions (status);
CREATE INDEX IF NOT EXISTS ix_payment_session_branch_status ON payment_gaming_sessions (branch, status);
CREATE INDEX IF NOT EXISTS ix_payment_session_is_deleted ON payment_gaming_sessions (is_deleted);

CREATE TABLE IF NOT EXISTS payment_transactions (
    id VARCHAR(36) PRIMARY KEY,
    reference VARCHAR(64) NOT NULL UNIQUE,
    provider VARCHAR(30) NOT NULL DEFAULT 'paystack',
    user_id VARCHAR(36) NOT NULL,
    payment_session_id VARCHAR(36) NULL,
    amount_kobo INTEGER NOT NULL,
    expected_amount_kobo INTEGER NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'NGN',
    status VARCHAR(32) NOT NULL DEFAULT 'initialized',
    gateway_status VARCHAR(40) NULL,
    access_code VARCHAR(120) NULL,
    authorization_url VARCHAR(255) NULL,
    provider_transaction_id VARCHAR(80) NULL,
    paid_at TIMESTAMP NULL,
    verified_at TIMESTAMP NULL,
    verify_attempts INTEGER NOT NULL DEFAULT 0,
    callback_payload_json TEXT NULL,
    webhook_payload_json TEXT NULL,
    metadata_json TEXT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT fk_payment_user FOREIGN KEY (user_id) REFERENCES payment_users (id),
    CONSTRAINT fk_payment_session FOREIGN KEY (payment_session_id) REFERENCES payment_gaming_sessions (id),
    CONSTRAINT ck_payment_amount_kobo CHECK (amount_kobo >= 100),
    CONSTRAINT ck_payment_expected_amount_kobo CHECK (expected_amount_kobo >= 100),
    CONSTRAINT ck_payment_status CHECK (
        status IN ('initialized','pending','success_pending_webhook','completed','success','failed','abandoned','refunded')
    )
);

CREATE INDEX IF NOT EXISTS ix_payment_reference ON payment_transactions (reference);
CREATE INDEX IF NOT EXISTS ix_payment_status ON payment_transactions (status);
CREATE INDEX IF NOT EXISTS ix_payment_user_status ON payment_transactions (user_id, status);
CREATE INDEX IF NOT EXISTS ix_payment_session_id ON payment_transactions (payment_session_id);
CREATE INDEX IF NOT EXISTS ix_payment_is_deleted ON payment_transactions (is_deleted);

CREATE TABLE IF NOT EXISTS payment_logs (
    id VARCHAR(36) PRIMARY KEY,
    payment_id VARCHAR(36) NOT NULL,
    reference VARCHAR(64) NOT NULL,
    event_type VARCHAR(60) NOT NULL,
    message VARCHAR(255) NOT NULL,
    severity VARCHAR(16) NOT NULL DEFAULT 'info',
    request_id VARCHAR(120) NULL,
    remote_ip VARCHAR(80) NULL,
    user_agent VARCHAR(255) NULL,
    payload_json TEXT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_payment_log_payment FOREIGN KEY (payment_id) REFERENCES payment_transactions (id)
);

CREATE INDEX IF NOT EXISTS ix_payment_log_payment_id ON payment_logs (payment_id);
CREATE INDEX IF NOT EXISTS ix_payment_log_reference ON payment_logs (reference);
CREATE INDEX IF NOT EXISTS ix_payment_log_event_type ON payment_logs (event_type);
CREATE INDEX IF NOT EXISTS ix_payment_log_severity ON payment_logs (severity);
CREATE INDEX IF NOT EXISTS ix_payment_log_request_id ON payment_logs (request_id);
