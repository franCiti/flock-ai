-- Schema "core" of the Core API (plan 3.4), owned by the role core_api and migrated by Flyway at
-- start-up. The schema itself and its owner are created by infra/postgres/initdb; its tables come
-- with the features that use them (users T32, read copies T33, sources T47).
COMMENT ON SCHEMA core IS 'Core API: users, external sources and read copies of the agent data';
