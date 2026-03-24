DROP TABLE IF EXISTS ont_status, olt_collect_state;

CREATE TABLE ont_status (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ip VARCHAR(45) NOT NULL,
    slot INT NOT NULL,
    pon INT NOT NULL,
    ont_id INT NOT NULL,
    port VARCHAR(32) NOT NULL,
    sn VARCHAR(32) DEFAULT NULL,
    run_state VARCHAR(32) DEFAULT NULL,
    last_down_cause VARCHAR(64) DEFAULT NULL,
    last_uptime DATETIME DEFAULT NULL,
    last_downtime DATETIME DEFAULT NULL,
    rx_power_dbm DECIMAL(6,2) DEFAULT NULL,
    tx_power_dbm DECIMAL(6,2) DEFAULT NULL,
    distance_m INT DEFAULT NULL,
    ont_type VARCHAR(64) DEFAULT NULL,
    description VARCHAR(255) DEFAULT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
      ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uniq_ont_current (ip, slot, pon, ont_id),
    KEY idx_sn (sn),
    KEY idx_port (ip, slot, pon),
    KEY idx_state (run_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE olt_collect_state (
    ip VARCHAR(45) NOT NULL,
    status ENUM('idle', 'running', 'success', 'error') NOT NULL DEFAULT 'idle',
    last_duration_seconds DECIMAL(10,2) DEFAULT NULL,
    is_locked TINYINT(1) NOT NULL DEFAULT 0,
    lock_token CHAR(36) DEFAULT NULL,
    lock_expires_at DATETIME(3) DEFAULT NULL,
    last_started_at DATETIME(3) DEFAULT NULL,
    last_finished_at DATETIME(3) DEFAULT NULL,
    last_error VARCHAR(1000) DEFAULT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (ip),
    KEY idx_locked (is_locked, lock_expires_at),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;