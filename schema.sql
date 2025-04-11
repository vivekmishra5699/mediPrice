-- schema.sql

-- Drop existing tables if they exist (in reverse order of dependencies)
DROP TABLE IF EXISTS notifications;
DROP TABLE IF EXISTS medicine_doses;
DROP TABLE IF EXISTS medicine_routines;
DROP TABLE IF EXISTS search_history;
DROP TABLE IF EXISTS users;

-- Create users table
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create search history table to track user searches
CREATE TABLE search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    query TEXT NOT NULL,
    search_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    results_count INTEGER,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Medicine routine tables

CREATE TABLE IF NOT EXISTS medicine_routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    medicine_name TEXT NOT NULL,
    description TEXT,
    priority TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active BOOLEAN NOT NULL DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS medicine_doses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL,
    time_of_day TEXT NOT NULL,
    frequency_hours INTEGER NOT NULL,
    dosage TEXT NOT NULL,
    instructions TEXT,
    FOREIGN KEY (routine_id) REFERENCES medicine_routines (id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    routine_id INTEGER NOT NULL,
    dose_id INTEGER NOT NULL,
    scheduled_time TIMESTAMP NOT NULL,
    sent_at TIMESTAMP,
    updated_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (routine_id) REFERENCES medicine_routines (id),
    FOREIGN KEY (dose_id) REFERENCES medicine_doses (id)
);


-- Create indices for faster queries
CREATE INDEX idx_search_history_user_id ON search_history(user_id);
CREATE INDEX idx_medicine_routines_user_id ON medicine_routines(user_id);
CREATE INDEX idx_medicine_doses_routine_id ON medicine_doses(routine_id);
CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_scheduled_time ON notifications(scheduled_time);
CREATE INDEX idx_notifications_status ON notifications(status);