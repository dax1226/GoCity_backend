CREATE DATABASE gocity_admin1;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =========================
-- ENUM TYPES
-- =========================

CREATE TYPE user_role AS ENUM ('customer', 'admin', 'support');
CREATE TYPE user_status AS ENUM ('active', 'inactive', 'blocked');

CREATE TYPE driver_status AS ENUM ('pending', 'approved', 'rejected', 'suspended');
CREATE TYPE vehicle_status AS ENUM ('active', 'inactive', 'maintenance');

CREATE TYPE ride_status AS ENUM ('requested', 'accepted', 'started', 'completed', 'cancelled');
CREATE TYPE delivery_status AS ENUM ('pending', 'picked_up', 'in_transit', 'delivered', 'cancelled');

CREATE TYPE complaint_status AS ENUM ('open', 'in_progress', 'resolved', 'closed');
CREATE TYPE notification_type AS ENUM ('sms', 'email', 'push', 'system');

-- =========================
-- USERS
-- =========================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE,
    phone VARCHAR(30) UNIQUE NOT NULL,
    password_hash TEXT,
    role user_role DEFAULT 'customer',
    status user_status DEFAULT 'active',
    profile_image TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- DRIVERS
-- =========================

CREATE TABLE drivers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    license_number VARCHAR(100) UNIQUE NOT NULL,
    license_expiry DATE,
    status driver_status DEFAULT 'pending',
    rating NUMERIC(3,2) DEFAULT 0,
    total_rides INT DEFAULT 0,
    total_deliveries INT DEFAULT 0,
    is_online BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- VEHICLES
-- =========================

CREATE TABLE vehicles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID REFERENCES drivers(id) ON DELETE SET NULL,
    vehicle_type VARCHAR(50) NOT NULL,
    brand VARCHAR(100),
    model VARCHAR(100),
    registration_number VARCHAR(100) UNIQUE NOT NULL,
    color VARCHAR(50),
    capacity INT,
    status vehicle_status DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- LIVE MAP MONITORING
-- =========================

CREATE TABLE driver_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID REFERENCES drivers(id) ON DELETE CASCADE,
    latitude NUMERIC(10,7) NOT NULL,
    longitude NUMERIC(10,7) NOT NULL,
    heading NUMERIC(6,2),
    speed NUMERIC(6,2),
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- RIDES
-- =========================

CREATE TABLE rides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES users(id) ON DELETE SET NULL,
    driver_id UUID REFERENCES drivers(id) ON DELETE SET NULL,
    vehicle_id UUID REFERENCES vehicles(id) ON DELETE SET NULL,

    pickup_address TEXT NOT NULL,
    pickup_latitude NUMERIC(10,7),
    pickup_longitude NUMERIC(10,7),

    dropoff_address TEXT NOT NULL,
    dropoff_latitude NUMERIC(10,7),
    dropoff_longitude NUMERIC(10,7),

    distance_km NUMERIC(10,2),
    fare_amount NUMERIC(12,2) DEFAULT 0,
    commission_amount NUMERIC(12,2) DEFAULT 0,
    driver_earning NUMERIC(12,2) DEFAULT 0,

    status ride_status DEFAULT 'requested',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    cancelled_at TIMESTAMP
);

-- =========================
-- DELIVERIES
-- =========================

CREATE TABLE deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES users(id) ON DELETE SET NULL,
    driver_id UUID REFERENCES drivers(id) ON DELETE SET NULL,

    pickup_address TEXT NOT NULL,
    pickup_latitude NUMERIC(10,7),
    pickup_longitude NUMERIC(10,7),

    delivery_address TEXT NOT NULL,
    delivery_latitude NUMERIC(10,7),
    delivery_longitude NUMERIC(10,7),

    package_description TEXT,
    delivery_fee NUMERIC(12,2) DEFAULT 0,
    commission_amount NUMERIC(12,2) DEFAULT 0,
    driver_earning NUMERIC(12,2) DEFAULT 0,

    status delivery_status DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    picked_up_at TIMESTAMP,
    delivered_at TIMESTAMP,
    cancelled_at TIMESTAMP
);

-- =========================
-- COMMISSION MANAGEMENT
-- =========================

CREATE TABLE commission_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_type VARCHAR(50) NOT NULL, -- ride, delivery
    commission_percentage NUMERIC(5,2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE commission_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID REFERENCES drivers(id) ON DELETE SET NULL,
    ride_id UUID REFERENCES rides(id) ON DELETE SET NULL,
    delivery_id UUID REFERENCES deliveries(id) ON DELETE SET NULL,
    gross_amount NUMERIC(12,2) NOT NULL,
    commission_amount NUMERIC(12,2) NOT NULL,
    driver_earning NUMERIC(12,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- CUSTOMER COMPLAINTS
-- =========================

CREATE TABLE complaints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    driver_id UUID REFERENCES drivers(id) ON DELETE SET NULL,
    ride_id UUID REFERENCES rides(id) ON DELETE SET NULL,
    delivery_id UUID REFERENCES deliveries(id) ON DELETE SET NULL,
    subject VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    status complaint_status DEFAULT 'open',
    admin_response TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

-- =========================
-- NOTIFICATION MANAGEMENT
-- =========================

CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    type notification_type DEFAULT 'system',
    is_read BOOLEAN DEFAULT FALSE,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- REPORTS & ANALYTICS VIEWS
-- =========================

CREATE VIEW ride_analytics AS
SELECT
    COUNT(*) AS total_rides,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed_rides,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_rides,
    COALESCE(SUM(fare_amount), 0) AS total_revenue,
    COALESCE(SUM(commission_amount), 0) AS total_commission
FROM rides;

CREATE VIEW delivery_analytics AS
SELECT
    COUNT(*) AS total_deliveries,
    COUNT(*) FILTER (WHERE status = 'delivered') AS completed_deliveries,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_deliveries,
    COALESCE(SUM(delivery_fee), 0) AS total_revenue,
    COALESCE(SUM(commission_amount), 0) AS total_commission
FROM deliveries;

CREATE VIEW driver_performance AS
SELECT
    d.id AS driver_id,
    u.full_name AS driver_name,
    d.rating,
    d.is_online,
    COUNT(DISTINCT r.id) AS total_rides,
    COUNT(DISTINCT de.id) AS total_deliveries
FROM drivers d
LEFT JOIN users u ON u.id = d.user_id
LEFT JOIN rides r ON r.driver_id = d.id
LEFT JOIN deliveries de ON de.driver_id = d.id
GROUP BY d.id, u.full_name, d.rating, d.is_online;

-- =========================
-- SAMPLE COMMISSION SETTINGS
-- =========================

INSERT INTO commission_settings (service_type, commission_percentage)
VALUES
('ride', 15.00),
('delivery', 10.00);

-- example --

INSERT INTO public.users (full_name , email, phone, hashed_password, role)
VALUES (
    'Test User',
    'testuser@example.com',
    '9876543210',
    'test_password_hash',
    'USER'
);
 select * from public.users
 select * from public.drivers