-- Tuya integration migration (new objects only)

CREATE TABLE IF NOT EXISTS tuya_devices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_id VARCHAR(120) NOT NULL UNIQUE,
  name VARCHAR(255) NULL,
  product_id VARCHAR(120) NULL,
  category VARCHAR(80) NULL,
  is_online BOOLEAN NOT NULL DEFAULT FALSE,
  last_seen_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tuya_device_status (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_id VARCHAR(120) NOT NULL,
  code VARCHAR(120) NOT NULL,
  value_text VARCHAR(255) NULL,
  value_bool BOOLEAN NULL,
  value_number DOUBLE NULL,
  last_updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_tuya_status_device_code UNIQUE (device_id, code),
  FOREIGN KEY (device_id) REFERENCES tuya_devices(device_id)
);

CREATE TABLE IF NOT EXISTS tuya_command_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_id VARCHAR(120) NOT NULL,
  session_id INT NULL,
  user_id INT NULL,
  request_id VARCHAR(120) NOT NULL UNIQUE,
  station VARCHAR(30) NULL,
  command_json TEXT NOT NULL,
  success BOOLEAN NOT NULL DEFAULT FALSE,
  response_json TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (session_id) REFERENCES gaming_sessions(id),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tuya_event_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_id VARCHAR(120) NOT NULL,
  event_type VARCHAR(80) NOT NULL,
  event_id VARCHAR(120) NULL,
  payload_json TEXT NOT NULL,
  received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  actor_user_id INT NULL,
  action VARCHAR(120) NOT NULL,
  entity_type VARCHAR(80) NOT NULL,
  entity_id VARCHAR(120) NULL,
  metadata_json TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (actor_user_id) REFERENCES users(id)
);
