CREATE MATERIALIZED VIEW IF NOT EXISTS new_subdomains_mv
ENGINE = MergeTree
ORDER BY (base_domain, domain)
AS SELECT domain, base_domain, max(ts) as last_seen
FROM cert_domains
WHERE ts > now() - INTERVAL 7 DAY
GROUP BY domain, base_domain;
