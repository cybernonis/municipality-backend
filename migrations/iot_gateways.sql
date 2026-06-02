-- IoT Gateways system
-- Run this in the Supabase SQL Editor before deploying.

CREATE TABLE IF NOT EXISTS iot_gateways (
  id                UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  gateway_id        TEXT      UNIQUE NOT NULL,
  name              TEXT      NOT NULL,
  latitude          DOUBLE PRECISION NOT NULL,
  longitude         DOUBLE PRECISION NOT NULL,
  address           TEXT,
  neighborhood      TEXT,
  coverage_radius_m INTEGER   DEFAULT 2000,
  protocol          TEXT      DEFAULT 'LoRaWAN',
  status            TEXT      DEFAULT 'online',
  last_seen         TIMESTAMP DEFAULT NOW(),
  installed_at      TIMESTAMP DEFAULT NOW(),
  ip_address        TEXT,
  firmware_version  TEXT      DEFAULT '1.0.0',
  signal_strength   INTEGER   DEFAULT -70,
  battery_percent   INTEGER   DEFAULT 100,
  is_virtual        BOOLEAN   DEFAULT TRUE,
  notes             TEXT
);

ALTER TABLE iot_sensors
  ADD COLUMN IF NOT EXISTS gateway_id TEXT REFERENCES iot_gateways(gateway_id);

CREATE INDEX IF NOT EXISTS idx_sensors_gateway      ON iot_sensors (gateway_id);
CREATE INDEX IF NOT EXISTS idx_gateways_status      ON iot_gateways (status);
CREATE INDEX IF NOT EXISTS idx_gateways_last_seen   ON iot_gateways (last_seen DESC);

-- Seed: 7 gateways Ηρακλείου
INSERT INTO iot_gateways (gateway_id, name, latitude, longitude, address, neighborhood, coverage_radius_m, protocol)
VALUES
  ('GW_HER_CENTER',  'Κέντρο Ηρακλείου',    35.3387, 25.1442, 'Πλατεία Ελευθερίας',  'Κέντρο',           2000, 'LoRaWAN'),
  ('GW_HER_COAST',   'Λιμάνι',              35.3447, 25.1521, 'Λιμάνι Ηρακλείου',    'Λιμάνι',           3000, 'LoRaWAN'),
  ('GW_HER_WEST',    'Αμμουδάρα',           35.3389, 25.0589, 'Παραλία Αμμουδάρας',  'Αμμουδάρα',        2500, 'LoRaWAN'),
  ('GW_HER_EAST',    'Καρτερός',            35.3294, 25.2076, 'Παραλία Καρτερού',    'Καρτερός',         2500, 'NB-IoT'),
  ('GW_HER_SOUTH',   'Ν. Αλικαρνασσός',     35.3050, 25.1700, 'Πλ. Αλικαρνασσού',   'Αλικαρνασσός',     2000, 'LoRaWAN'),
  ('GW_HER_AIRPORT', 'Αεροδρόμιο',          35.3397, 25.1803, 'Αεροδρόμιο',          'Ν. Αλικαρνασσός',  2000, 'NB-IoT'),
  ('GW_HER_UNIV',    'Πανεπιστήμιο',        35.3050, 25.0830, 'Πανεπιστήμιο Κρήτης', 'Βούτες',           1500, 'WiFi-Mesh')
ON CONFLICT (gateway_id) DO NOTHING;
