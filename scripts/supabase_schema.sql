-- AquaSense PostgreSQL schema for a new Supabase project.
-- Run in the Supabase SQL Editor as the project owner.
-- The Flask server connects directly to PostgreSQL; RLS blocks the public
-- Supabase API roles, while the table-owning server connection bypasses RLS.

BEGIN;

SET LOCAL search_path = public;

CREATE TABLE IF NOT EXISTS public.rivers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    location_description VARCHAR(255),
    barangay VARCHAR(100),
    municipality VARCHAR(100) NOT NULL,
    latitude FLOAT,
    longitude FLOAT,
    description TEXT,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_rivers_name ON public.rivers (name);

CREATE TABLE IF NOT EXISTS public.threshold_rules (
    id SERIAL PRIMARY KEY,
    parameter VARCHAR(50) NOT NULL,
    rule_name VARCHAR(100) NOT NULL,
    min_value FLOAT,
    max_value FLOAT,
    status VARCHAR(30) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_threshold_rules_parameter
    ON public.threshold_rules (parameter);

CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    username VARCHAR(80) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username
    ON public.users (username);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email
    ON public.users (email);

CREATE TABLE IF NOT EXISTS public.audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users (id),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id INTEGER,
    details TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id
    ON public.audit_logs (user_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at
    ON public.audit_logs (created_at);

CREATE TABLE IF NOT EXISTS public.readings (
    id SERIAL PRIMARY KEY,
    river_id INTEGER NOT NULL REFERENCES public.rivers (id),
    turbidity_ntu FLOAT,
    tss FLOAT,
    particle_level FLOAT,
    clarity FLOAT,
    ph_value FLOAT,
    acidity FLOAT,
    alkalinity FLOAT,
    ph_stability FLOAT,
    temperature_c FLOAT,
    ambient_temperature FLOAT,
    change_rate FLOAT,
    thermal_anomaly FLOAT,
    tds_ppm FLOAT,
    conductivity FLOAT,
    ionic_content FLOAT,
    salinity FLOAT,
    water_quality_index FLOAT,
    quality_status VARCHAR(50),
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
    source VARCHAR(30) NOT NULL,
    device_id VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS ix_readings_recorded_at
    ON public.readings (recorded_at);
CREATE INDEX IF NOT EXISTS ix_readings_river_id
    ON public.readings (river_id);

CREATE TABLE IF NOT EXISTS public.sensors (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(100) NOT NULL,
    name VARCHAR(120) NOT NULL,
    river_id INTEGER NOT NULL REFERENCES public.rivers (id),
    is_active BOOLEAN NOT NULL,
    last_seen_at TIMESTAMP WITH TIME ZONE,
    api_key_hash VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_sensors_device_id
    ON public.sensors (device_id);
CREATE INDEX IF NOT EXISTS ix_sensors_river_id
    ON public.sensors (river_id);

CREATE TABLE IF NOT EXISTS public.stations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    station_code VARCHAR(50) NOT NULL,
    river_id INTEGER NOT NULL REFERENCES public.rivers (id),
    description TEXT,
    latitude FLOAT,
    longitude FLOAT,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_stations_station_code
    ON public.stations (station_code);
CREATE INDEX IF NOT EXISTS ix_stations_river_id
    ON public.stations (river_id);

CREATE TABLE IF NOT EXISTS public.alerts (
    id SERIAL PRIMARY KEY,
    river_id INTEGER NOT NULL REFERENCES public.rivers (id),
    reading_id INTEGER REFERENCES public.readings (id),
    message TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_alerts_reading_id
    ON public.alerts (reading_id);
CREATE INDEX IF NOT EXISTS ix_alerts_status
    ON public.alerts (status);
CREATE INDEX IF NOT EXISTS ix_alerts_river_id
    ON public.alerts (river_id);

CREATE TABLE IF NOT EXISTS public.assessments (
    id SERIAL PRIMARY KEY,
    river_id INTEGER NOT NULL REFERENCES public.rivers (id),
    reading_id INTEGER NOT NULL REFERENCES public.readings (id),
    status VARCHAR(30) NOT NULL,
    remarks TEXT,
    assessed_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_assessments_reading_id
    ON public.assessments (reading_id);
CREATE INDEX IF NOT EXISTS ix_assessments_river_id
    ON public.assessments (river_id);

ALTER TABLE public.rivers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.threshold_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sensors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assessments ENABLE ROW LEVEL SECURITY;

COMMIT;
