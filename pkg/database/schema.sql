CREATE DATABASE IF NOT EXISTS gameswitchos_demo;
USE gameswitchos_demo;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(120) NOT NULL,
  email VARCHAR(120) NOT NULL UNIQUE,
  phone VARCHAR(40) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('user', 'admin1', 'admin2', 'superadmin') NOT NULL DEFAULT 'user',
  branch ENUM('branch1', 'branch2') NOT NULL DEFAULT 'branch1',
  avatar_url VARCHAR(255) NULL,
  total_spent DECIMAL(10,2) NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS games (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(120) NOT NULL,
  slug VARCHAR(120) NULL UNIQUE,
  description TEXT NULL,
  price_per_hour DECIMAL(10,2) NOT NULL,
  category VARCHAR(80) NOT NULL DEFAULT 'action',
  console_type VARCHAR(80) NOT NULL DEFAULT 'console',
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  display_order INT NOT NULL DEFAULT 0,
  cover_image_path VARCHAR(255) NULL,
  banner_image_path VARCHAR(255) NULL,
  image_path VARCHAR(255) NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  archived_at DATETIME NULL,
  deleted_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  created_by INT NULL,
  updated_by INT NULL,
  FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
  FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS payments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  game_id INT NOT NULL,
  branch ENUM('branch1', 'branch2') NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  status ENUM('pending', 'successful', 'declined') NOT NULL DEFAULT 'pending',
  provider_ref VARCHAR(120) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (game_id) REFERENCES games(id)
);

CREATE TABLE IF NOT EXISTS gaming_sessions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  game_id INT NOT NULL,
  branch ENUM('branch1', 'branch2') NOT NULL,
  plug_id VARCHAR(100) NOT NULL,
  duration_seconds INT NOT NULL,
  remaining_seconds INT NOT NULL,
  status ENUM('pending', 'active', 'ended') NOT NULL DEFAULT 'pending',
  payment_id INT NULL,
  started_at DATETIME NULL,
  ended_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (game_id) REFERENCES games(id),
  FOREIGN KEY (payment_id) REFERENCES payments(id)
);

CREATE TABLE IF NOT EXISTS login_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  login_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ip_address VARCHAR(60) NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS notifications (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  branch ENUM('branch1', 'branch2') NULL,
  message VARCHAR(255) NOT NULL,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

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
