# CT ingestion with ClickHouse and REST API

**Certificate Transparency ingestion platform** with:

* Automatic CT log discovery
* Horizontal scaling (one worker per log)
* Deduplication and metrics
* ClickHouse backend for fast querying
* Optional REST API for domain/subdomain search
* Optional rate limiting
* Docker Compose deployment with resource limits

---

## Features

* Polls **all usable CT logs** automatically
* Horizontal scaling: one Python process per log
* Deduplicates certificates by SHA256 fingerprint
* Stores domain/subdomain data in **ClickHouse** database
* Optional REST API for easy queries
* Materialized views for fast “recent subdomains” queries
* Rate limiting optional via environment variables

---

## Requirements

* Docker & Docker Compose >= 1.29
* Python 3.11 (for building images)
* Minimum system resources: 3 GB RAM (1 per service recommended)

---

## Setup

1. Clone the repository:

```bash
git clone https://github.com/stefanpejcic/ct-clickhouse/
cd ct-clickhouse
```

2. Build Docker images:

```bash
docker compose build && docker compose --profile api build
```

3. ClickHouse will automatically initialize the database and tables using `clickhouse/init.sql`.

---

## Running the Platform

### 1. Ingestion + ClickHouse (default)

```bash
docker compose up -d
```

This starts:

* ClickHouse
* CT ingestion service (horizontal scaling, auto-discovery, deduplication)

---

### 2. Enable Optional REST API

```bash
docker compose --profile api up -d
```

* API exposed at: `http://localhost:5000`
* Endpoints:

```text
GET /domain/<name>           # Latest certificates for a domain
GET /subdomains/<base>       # All subdomains of a base domain
GET /recent/<base>           # New subdomains in last 24h
```

---

### 3. Enable API + Rate Limiting

```bash
RATE_LIMIT_ENABLED=true RATE_LIMIT=60/minute docker compose --profile api up
```

* `RATE_LIMIT` defaults to `100/minute` if enabled
* Rate limiting optional; off by default

---

## ClickHouse Queries

### Total records

```sql
SELECT count() FROM ct.cert_domains;
```

### Search a domain

```sql
SELECT *
FROM ct.cert_domains
WHERE domain = 'example.com'
ORDER BY ts DESC;
```

### Enumerate subdomains

```sql
SELECT domain
FROM ct.cert_domains
WHERE base_domain = 'example.com'
GROUP BY domain
ORDER BY domain;
```

### Recent subdomains (last 24h)

```sql
SELECT domain
FROM ct.cert_domains
WHERE base_domain = 'example.com'
  AND ts > now() - INTERVAL 1 DAY
GROUP BY domain;
```

---

## Resource Limits

* **ClickHouse**: 1 CPU, 1GB RAM
* **Ingestion service**: 1 CPU, 1GB RAM
* **API service**: 1 CPU, 1GB RAM

Configured in `docker-compose.yml` under `deploy.resources.limits`.

---

## Contributing

* Fork the repo
* Make feature branches
* Test thoroughly with Docker Compose
* Submit PRs with clear description

---

## License

MIT License - free to use, modify, and distribute.
