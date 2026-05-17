CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    profile_image TEXT,
    wallet_balance NUMERIC(12,2) DEFAULT 0.00,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_phone ON users(phone_number);

CREATE TABLE drivers (
    driver_id SERIAL PRIMARY KEY,
    driver_name VARCHAR(100) NOT NULL,
    vehicle_type VARCHAR(50) NOT NULL,
    vehicle_number VARCHAR(30) NOT NULL UNIQUE,
    license_number VARCHAR(50) NOT NULL UNIQUE,
    driver_status VARCHAR(20) DEFAULT 'offline'
        CHECK (driver_status IN ('online','offline','on_trip','suspended')),
    earnings NUMERIC(14,2) DEFAULT 0.00,
    rating NUMERIC(3,2) DEFAULT 5.00
        CHECK (rating >= 0 AND rating <= 5)
);

CREATE TABLE bookings (
    booking_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    driver_id INTEGER REFERENCES drivers(driver_id) ON DELETE SET NULL,
    pickup_location TEXT NOT NULL,
    drop_location TEXT NOT NULL,
    ride_type VARCHAR(30) DEFAULT 'standard'
        CHECK (ride_type IN ('standard','premium','shared','auto','bike')),
    fare_amount NUMERIC(10,2) DEFAULT 0.00,
    booking_status VARCHAR(20) DEFAULT 'pending'
        CHECK (booking_status IN ('pending','accepted','ongoing','completed','cancelled'))
);

CREATE TABLE payments (
    payment_id SERIAL PRIMARY KEY,
    booking_id INTEGER NOT NULL REFERENCES bookings(booking_id) ON DELETE CASCADE,
    payment_method VARCHAR(30) NOT NULL
        CHECK (payment_method IN ('cash','wallet','upi','credit_card','debit_card','net_banking')),
    amount NUMERIC(10,2) NOT NULL,
    payment_status VARCHAR(20) DEFAULT 'pending'
        CHECK (payment_status IN ('pending','success','failed','refunded')),
    transaction_date TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE delivery_orders (
    delivery_id SERIAL PRIMARY KEY,
    sender_name VARCHAR(100) NOT NULL,
    receiver_name VARCHAR(100) NOT NULL,
    pickup_address TEXT NOT NULL,
    delivery_address TEXT NOT NULL,
    parcel_type VARCHAR(50) NOT NULL
        CHECK (parcel_type IN ('document','small_package','medium_package','large_package','fragile')),
    delivery_status VARCHAR(20) DEFAULT 'pending'
        CHECK (delivery_status IN ('pending','picked_up','in_transit','delivered','failed','returned'))
);

CREATE TABLE support_tickets (
    ticket_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    issue_type VARCHAR(50) NOT NULL
        CHECK (issue_type IN ('payment','driver_behaviour','app_bug','account','delivery','other')),
    description TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'open'
        CHECK (status IN ('open','in_progress','resolved','closed')),
    created_date TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_bookings_user_id ON bookings(user_id);
CREATE INDEX idx_bookings_driver_id ON bookings(driver_id);
CREATE INDEX idx_bookings_status ON bookings(booking_status);
CREATE INDEX idx_payments_booking_id ON payments(booking_id);
CREATE INDEX idx_support_user_id ON support_tickets(user_id);
CREATE INDEX idx_support_status ON support_tickets(status);
CREATE INDEX idx_delivery_status ON delivery_orders(delivery_status);