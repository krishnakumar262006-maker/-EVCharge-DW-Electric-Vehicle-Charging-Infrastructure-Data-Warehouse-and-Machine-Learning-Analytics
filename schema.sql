-- EVCharge DW : Galaxy schema (3 fact tables sharing dim_time / dim_station / dim_charger)
DROP VIEW IF EXISTS vw_fact_clean;
DROP TABLE IF EXISTS station_clusters;
DROP TABLE IF EXISTS cluster_summary;
DROP TABLE IF EXISTS fact_station_maintenance;
DROP TABLE IF EXISTS fact_energy_consumption;
DROP TABLE IF EXISTS fact_charging_transaction;
DROP TABLE IF EXISTS dim_payment;
DROP TABLE IF EXISTS dim_user;
DROP TABLE IF EXISTS dim_vehicle;
DROP TABLE IF EXISTS dim_station;
DROP TABLE IF EXISTS dim_charger;
DROP TABLE IF EXISTS dim_location;
DROP TABLE IF EXISTS dim_time;

CREATE TABLE dim_time (
  time_key BIGINT PRIMARY KEY, full_date DATE, day INT, month INT, quarter INT,
  year INT, hour INT, day_of_week INT, weekend_flag SMALLINT);
CREATE TABLE dim_location (
  location_key INT PRIMARY KEY, city VARCHAR(80), state VARCHAR(80), country VARCHAR(10),
  latitude DECIMAL(9,6), longitude DECIMAL(9,6));
CREATE TABLE dim_charger (
  charger_key INT PRIMARY KEY, charger_type VARCHAR(20), power_class VARCHAR(30),
  power_kw DECIMAL(8,2), ports INT, fast_dc_flag SMALLINT);
CREATE TABLE dim_station (
  station_key INT PRIMARY KEY, station_id VARCHAR(60), station_name VARCHAR(150),
  location_key INT REFERENCES dim_location(location_key),
  charger_key INT REFERENCES dim_charger(charger_key));
CREATE TABLE dim_vehicle (
  vehicle_key INT PRIMARY KEY, make VARCHAR(60), model VARCHAR(80),
  powertrain VARCHAR(20), segment VARCHAR(30));
CREATE TABLE dim_user (
  user_key INT PRIMARY KEY, user_id VARCHAR(60), user_type VARCHAR(20));
CREATE TABLE dim_payment (
  payment_key INT PRIMARY KEY, payment_type VARCHAR(30));

CREATE TABLE fact_charging_transaction (
  transaction_key BIGINT PRIMARY KEY, session_id VARCHAR(40),
  time_key BIGINT REFERENCES dim_time(time_key),
  vehicle_key INT REFERENCES dim_vehicle(vehicle_key),
  station_key INT REFERENCES dim_station(station_key),
  charger_key INT REFERENCES dim_charger(charger_key),
  user_key INT REFERENCES dim_user(user_key),
  payment_key INT REFERENCES dim_payment(payment_key),
  energy_kwh DECIMAL(10,3), duration_minutes DECIMAL(10,2), amount DECIMAL(12,2),
  outlier_flag SMALLINT);
CREATE TABLE fact_energy_consumption (
  energy_key BIGINT PRIMARY KEY,
  time_key BIGINT REFERENCES dim_time(time_key),
  station_key INT REFERENCES dim_station(station_key),
  energy_kwh DECIMAL(12,3), session_count INT, avg_power_kw DECIMAL(10,3));
CREATE TABLE fact_station_maintenance (
  maintenance_key BIGINT PRIMARY KEY,
  time_key BIGINT REFERENCES dim_time(time_key),
  station_key INT REFERENCES dim_station(station_key),
  issue_type VARCHAR(60), downtime_hours DECIMAL(8,2), maintenance_cost DECIMAL(12,2));

CREATE INDEX ix_fct_time ON fact_charging_transaction(time_key);
CREATE INDEX ix_fct_station ON fact_charging_transaction(station_key);
CREATE INDEX ix_fec_station ON fact_energy_consumption(station_key);
CREATE INDEX ix_fsm_station ON fact_station_maintenance(station_key);
-- analysis view: outliers are FLAGGED in the fact table (not dropped) and excluded here
CREATE VIEW vw_fact_clean AS SELECT * FROM fact_charging_transaction WHERE outlier_flag = 0;
