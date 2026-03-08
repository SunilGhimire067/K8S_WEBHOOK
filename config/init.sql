-- MySQL initialization script for Sentinel K8s
-- Mounted into the MySQL container as /docker-entrypoint-initdb.d/init.sql

CREATE DATABASE IF NOT EXISTS sentinel_k8s;

CREATE USER IF NOT EXISTS 'sentinel'@'%' IDENTIFIED BY 'sentinel_pass';
GRANT ALL PRIVILEGES ON sentinel_k8s.* TO 'sentinel'@'%';
FLUSH PRIVILEGES;

USE sentinel_k8s;

CREATE TABLE IF NOT EXISTS k8s_events (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    event_id    VARCHAR(64) NOT NULL UNIQUE,
    event_type  VARCHAR(32) NOT NULL,
    kind        VARCHAR(64),
    name        VARCHAR(253),
    namespace   VARCHAR(253),
    reason      VARCHAR(128),
    message     TEXT,
    severity    VARCHAR(16) DEFAULT 'info',
    raw_payload LONGTEXT NOT NULL,
    status      VARCHAR(16) DEFAULT 'new',
    analysis    TEXT,
    created_at  VARCHAR(64) NOT NULL,
    updated_at  VARCHAR(64) NOT NULL
);

CREATE INDEX idx_status ON k8s_events(status);
CREATE INDEX idx_severity ON k8s_events(severity);
CREATE INDEX idx_created ON k8s_events(created_at);

-- Application configuration (LLM credentials, etc.)
CREATE TABLE IF NOT EXISTS app_config (
    config_key   VARCHAR(128) PRIMARY KEY,
    config_value TEXT NOT NULL,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- User accounts with bcrypt-hashed passwords and TOTP secrets
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(128) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    totp_secret   VARCHAR(64),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Persistent sessions with TTL expiration
CREATE TABLE IF NOT EXISTS sessions (
    token      VARCHAR(128) PRIMARY KEY,
    username   VARCHAR(128) NOT NULL,
    is_temp    BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    INDEX idx_expires (expires_at)
);
