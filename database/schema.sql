-- Civic Complaint Analyzer Database Schema

DROP DATABASE IF EXISTS civic_complaints;
CREATE DATABASE civic_complaints;
USE civic_complaints;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    role ENUM('admin', 'citizen') DEFAULT 'citizen',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS complaints (
    complaint_id INT AUTO_INCREMENT PRIMARY KEY,
    citizen_name VARCHAR(100) NOT NULL,
    citizen_email VARCHAR(100) NOT NULL,
    area VARCHAR(100) NOT NULL,
    issue_type ENUM('Road', 'Water', 'Electricity', 'Garbage', 'Other') NOT NULL,
    description TEXT NOT NULL,
    date_submitted TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('Pending', 'In Progress', 'Resolved', 'Rejected') DEFAULT 'Pending'
);

CREATE TABLE IF NOT EXISTS departments (
    dept_id INT AUTO_INCREMENT PRIMARY KEY,
    dept_name VARCHAR(100) NOT NULL,
    issue_type ENUM('Road', 'Water', 'Electricity', 'Garbage', 'Other') NOT NULL,
    UNIQUE(issue_type)
);

CREATE TABLE IF NOT EXISTS resolution (
    resolution_id INT AUTO_INCREMENT PRIMARY KEY,
    complaint_id INT NOT NULL,
    action_taken TEXT NOT NULL,
    resolved_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id) ON DELETE CASCADE
);

-- Insert sample admin user
INSERT INTO users (name, email, role) VALUES ('Admin', 'admin@example.com', 'admin') ON DUPLICATE KEY UPDATE id=id;

-- Insert target departments
INSERT INTO departments (dept_name, issue_type) VALUES 
('Roads & Transport', 'Road'),
('Water Supply', 'Water'),
('Electricity Board', 'Electricity'),
('Sanitation & Solid Waste', 'Garbage'),
('General Municipal', 'Other')
ON DUPLICATE KEY UPDATE dept_name=VALUES(dept_name);
