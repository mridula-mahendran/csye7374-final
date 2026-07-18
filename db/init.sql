-- Created automatically by the Postgres container on first start.
-- Gives us a dedicated database for the test suite so local test runs never
-- touch development data.
CREATE DATABASE appdb_test;
