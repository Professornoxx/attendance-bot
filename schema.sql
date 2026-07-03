-- Database Schema for Employee Attendance and Time Tracking System
-- Compatible with SQLite and MySQL

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username VARCHAR(255),
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'employee',
    shift_start VARCHAR(50),
    shift_end VARCHAR(50),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Attendance Sessions Table (Login/Logout)
CREATE TABLE IF NOT EXISTS attendance_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    username VARCHAR(255),
    name VARCHAR(255) NOT NULL,
    date VARCHAR(10) NOT NULL, -- Format: YYYY-MM-DD
    login_time VARCHAR(8) NOT NULL, -- Format: HH:MM:SS
    logout_time VARCHAR(8), -- Format: HH:MM:SS
    duration INTEGER DEFAULT 0, -- Duration in seconds
    status VARCHAR(20) NOT NULL DEFAULT 'active', -- 'active' or 'completed'
    is_half_day INTEGER DEFAULT 0, -- 0 for normal, 1 for half day
    fine_applied INTEGER DEFAULT 0, -- 0 for no, 1 for yes
    fine_amount REAL DEFAULT 0.0,
    fine_reason VARCHAR(255),
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- 3. Break Sessions Table (Break In/Break Out)
CREATE TABLE IF NOT EXISTS break_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    username VARCHAR(255),
    name VARCHAR(255) NOT NULL,
    date VARCHAR(10) NOT NULL, -- Format: YYYY-MM-DD
    break_in_time VARCHAR(8) NOT NULL, -- Format: HH:MM:SS
    break_out_time VARCHAR(8), -- Format: HH:MM:SS
    duration INTEGER DEFAULT 0, -- Duration in seconds
    status VARCHAR(20) NOT NULL DEFAULT 'active', -- 'active' or 'completed'
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- 4. Movements Table (In/Out Sessions)
CREATE TABLE IF NOT EXISTS in_out_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    username VARCHAR(255),
    name VARCHAR(255) NOT NULL,
    date VARCHAR(10) NOT NULL, -- Format: YYYY-MM-DD
    in_time VARCHAR(8) NOT NULL, -- Format: HH:MM:SS
    out_time VARCHAR(8), -- Format: HH:MM:SS
    duration INTEGER DEFAULT 0, -- Duration in seconds
    status VARCHAR(20) NOT NULL DEFAULT 'active', -- 'active' or 'completed'
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- 5. Early Logout Requests Table
CREATE TABLE IF NOT EXISTS early_logout_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    username VARCHAR(255),
    name VARCHAR(255) NOT NULL,
    date VARCHAR(10) NOT NULL,
    logout_time VARCHAR(8) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
    reviewed_at TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- 6. Fines Table (Audit and independent logs)
CREATE TABLE IF NOT EXISTS fines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    date VARCHAR(10) NOT NULL,
    amount REAL NOT NULL,
    reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
    UNIQUE(telegram_id, date)
);

-- 7. Permission Requests Table
CREATE TABLE IF NOT EXISTS permission_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    username VARCHAR(255),
    name VARCHAR(255) NOT NULL,
    date VARCHAR(10) NOT NULL,           -- YYYY-MM-DD (the work date affected)
    request_type VARCHAR(50) NOT NULL,   -- 'short_leave', 'late_arrival', 'early_departure', 'medical_leave', 'other'
    start_time VARCHAR(8) NOT NULL,      -- HH:MM:SS
    end_time VARCHAR(8) NOT NULL,        -- HH:MM:SS
    duration_seconds INTEGER DEFAULT 0,  -- pre-calculated for attendance credit
    reason VARCHAR(1000) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
    approver_id INTEGER,
    approver_name VARCHAR(255),
    decided_at TIMESTAMP,
    notification_status VARCHAR(50) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- Create Indices for Optimized Lookup Queries
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_att_lookup ON attendance_sessions(telegram_id, date, status);
CREATE INDEX IF NOT EXISTS idx_brk_lookup ON break_sessions(telegram_id, date, status);
CREATE INDEX IF NOT EXISTS idx_move_lookup ON in_out_sessions(telegram_id, date, status);
CREATE INDEX IF NOT EXISTS idx_fines_lookup ON fines(telegram_id, date);
CREATE INDEX IF NOT EXISTS idx_elr_lookup ON early_logout_requests(telegram_id, date);
CREATE INDEX IF NOT EXISTS idx_perm_lookup ON permission_requests(telegram_id, date);
CREATE INDEX IF NOT EXISTS idx_perm_status ON permission_requests(status);
