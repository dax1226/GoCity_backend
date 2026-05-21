-- GoCity Database Schema  (PostgreSQL 14+ with PostGIS 3.x)
--
-- Mirrors the SQLAlchemy models in GoCity_backend/app/models.py.
-- The live database is built automatically by `Base.metadata.create_all`,
-- this file is the human-readable reference + bootstrap script.
--
-- Quick setup:
--   psql -U postgres -c "CREATE DATABASE gocity;"
--   psql -U postgres -d gocity -f schema.sql
--
-- Or just start the FastAPI app — `database.py` runs
-- `CREATE EXTENSION IF NOT EXISTS postgis;` automatically.

CREATE EXTENSION IF NOT EXISTS postgis;

-- ─────────────────────────────────────────────
-- Users (riders + customers)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(150) NOT NULL UNIQUE,
    phone           VARCHAR(20),
    hashed_password TEXT NOT NULL,
    role            VARCHAR(10) NOT NULL DEFAULT 'USER'
                    CHECK (role IN ('USER','RIDER'))
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ─────────────────────────────────────────────
-- Drivers / Riders
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS drivers (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    phone            VARCHAR(20),
    vehicle_type     VARCHAR(40) NOT NULL,
    vehicle_number   VARCHAR(30) NOT NULL UNIQUE,
    rating           REAL DEFAULT 5.0,
    status           VARCHAR(20) DEFAULT 'online'
                     CHECK (status IN ('online','offline','on_trip','suspended')),
    -- PostGIS: WGS84 point storing the driver's last known location
    current_location GEOGRAPHY(POINT, 4326)
);

CREATE INDEX IF NOT EXISTS idx_drivers_location
    ON drivers USING GIST (current_location);

-- ─────────────────────────────────────────────
-- Bookings (RIDE, CAB and PARCEL all share this table)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bookings (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    driver_id        INTEGER REFERENCES drivers(id) ON DELETE SET NULL,
    booking_type     VARCHAR(10) NOT NULL
                     CHECK (booking_type IN ('RIDE','CAB','PARCEL')),
    pickup_location  TEXT NOT NULL,
    drop_location    TEXT NOT NULL,
    -- PostGIS coordinates for real geo queries (ST_Distance, ST_DWithin)
    pickup_point     GEOGRAPHY(POINT, 4326),
    drop_point       GEOGRAPHY(POINT, 4326),
    vehicle_type     VARCHAR(40),
    fare             REAL DEFAULT 0.0,
    status           VARCHAR(20) DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','ACCEPTED','ONGOING','COMPLETED','CANCELLED')),
    payment_method   VARCHAR(20) DEFAULT 'wallet',
    -- Parcel-only fields
    sender_name      VARCHAR(100),
    receiver_name    VARCHAR(100),
    receiver_phone   VARCHAR(20),
    parcel_size      VARCHAR(20),
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bookings_user_id   ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_driver_id ON bookings(driver_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status    ON bookings(status);
CREATE INDEX IF NOT EXISTS idx_bookings_type      ON bookings(booking_type);
CREATE INDEX IF NOT EXISTS idx_bookings_pickup
    ON bookings USING GIST (pickup_point);

-- ─────────────────────────────────────────────
-- Seed drivers (Bengaluru coordinates)
-- ─────────────────────────────────────────────
INSERT INTO drivers (name, phone, vehicle_type, vehicle_number, rating, status, current_location)
VALUES
    ('Ramesh Kumar', '+91 98765 43210', 'bike',  'KA01JK1234', 4.8, 'online',
     ST_GeogFromText('SRID=4326;POINT(77.5946 12.9716)')),
    ('Suresh Rao',   '+91 98765 11111', 'auto',  'KA03AB5678', 4.6, 'online',
     ST_GeogFromText('SRID=4326;POINT(77.6245 12.9352)')),
    ('Vijay Singh',  '+91 98765 22222', 'sedan', 'KA05CD9012', 4.9, 'online',
     ST_GeogFromText('SRID=4326;POINT(77.6408 12.9784)')),
    ('Anil Kumar',   '+91 98765 33333', 'suv',   'KA02EF3456', 4.7, 'online',
     ST_GeogFromText('SRID=4326;POINT(77.7500 12.9698)')),
    ('Praveen Das',  '+91 98765 44444', 'mini',  'KA09GH7788', 4.5, 'online',
     ST_GeogFromText('SRID=4326;POINT(77.6271 12.9279)'))
ON CONFLICT (vehicle_number) DO NOTHING;

-- ─────────────────────────────────────────────
-- Example geo queries you now get for free
-- ─────────────────────────────────────────────
-- 1) Find 5 nearest online drivers to MG Road (in meters):
--    SELECT id, name, vehicle_type,
--           ST_Distance(current_location,
--                       ST_GeogFromText('SRID=4326;POINT(77.5946 12.9716)')) AS meters
--    FROM drivers
--    WHERE status = 'online' AND current_location IS NOT NULL
--    ORDER BY current_location <-> ST_GeogFromText('SRID=4326;POINT(77.5946 12.9716)')
--    LIMIT 5;
--
-- 2) All bookings whose pickup is within 2 km of a point:
--    SELECT * FROM bookings
--    WHERE ST_DWithin(pickup_point,
--                     ST_GeogFromText('SRID=4326;POINT(77.5946 12.9716)'),
--                     2000);
