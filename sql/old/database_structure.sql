-- 1. Master Outlets Table (permanent outlet info, channel, and division)
CREATE TABLE IF NOT EXISTS outlets (
    outlet_id SERIAL PRIMARY KEY,
    ke_number VARCHAR(50),
    outlet_name VARCHAR(255) UNIQUE NOT NULL,
    physical_location VARCHAR(255),
    channel VARCHAR(100),
    division VARCHAR(100)
);

-- 2. TMR Assignments Table (tracks TMR name, contact, outlet location, and division)
CREATE TABLE IF NOT EXISTS tmr_assignments (
    tmr_id SERIAL PRIMARY KEY,
    outlet_id INT REFERENCES outlets(outlet_id),
    tmr_name VARCHAR(255),
    tmr_phone VARCHAR(50),
    physical_location VARCHAR(255),
    division VARCHAR(100)
);

-- 3. Dedicated KDM Contacts Table (tracks Key Decision Makers like managers or accounts office)
CREATE TABLE IF NOT EXISTS kdm_contacts (
    kdm_id SERIAL PRIMARY KEY,
    outlet_id INT REFERENCES outlets(outlet_id),
    kdm_name VARCHAR(255),
    kdm_phone VARCHAR(50),
    location VARCHAR(255)
);

-- 4. Transactional Recce Visits Table (tracks visits over time, team leads, stock, and feedback)
CREATE TABLE IF NOT EXISTS recce_visits (
    visit_id SERIAL PRIMARY KEY,
    outlet_id INT REFERENCES outlets(outlet_id),
    team_lead_name VARCHAR(255),
    team_lead_phone VARCHAR(50),
    date_of_recce DATE,
    date_of_activation DATE,
    kick_off_time VARCHAR(50),
    raspberry_stock VARCHAR(100),
    raspberry_price VARCHAR(50),
    comments TEXT,
    source_file VARCHAR(255),
    CONSTRAINT unique_visit UNIQUE (outlet_id, date_of_recce)
);