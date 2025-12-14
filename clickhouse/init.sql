CREATE DATABASE IF NOT EXISTS ct;

CREATE TABLE IF NOT EXISTS ct.cert_domains
(
    ts DateTime,
    domain String,
    base_domain String,
    fingerprint FixedString(64),
    issuer String,
    subject String,
    san Array(String),
    not_before DateTime,
    not_after DateTime,
    log_name String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY (base_domain, domain, fingerprint);
