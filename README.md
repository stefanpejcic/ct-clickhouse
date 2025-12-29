# CT ingestion with ClickHouse and REST API

**Certificate Transparency ingestion platform** with:

* Automatic CT log discovery (daily)
* Horizontal scaling (one worker per log)
* Deduplication and metrics
* ClickHouse backend for fast querying
* Optional REST API for domain/subdomain search
* Optional rate and IP limiting
* Docker Compose deployment with resource limits

---

## Features

* Polls **all usable CT logs** automatically
* Horizontal scaling: one Python process per log
* Deduplicates certificates by SHA256 fingerprint
* Stores domain/subdomain data in **ClickHouse** database
* Optional REST API for easy queries

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

## API Endpoints

This API provides access to domain-related data, including subdomains, recent activity, top-level domains (TLDs), statistics, and streaming updates. All endpoints support `HEAD`, `OPTIONS`, and `GET` HTTP methods.

### 1. **Index**

* **URL:** `/`
* **Methods:** `HEAD`, `OPTIONS`, `GET`
* **Description:** Provides basic information about the API or confirms service availability.

### 2. **Domain**

* **URL:** `/domain/<name>`
* **Methods:** `HEAD`, `OPTIONS`, `GET`
* **Description:** Retrieve information about a specific domain.
* **Parameters:**

  * `name` (string, required): The domain name to query.

### 3. **Subdomains**

* **URL:** `/subdomains/<base>`
* **Methods:** `HEAD`, `OPTIONS`, `GET`
* **Description:** Fetch all known subdomains for a given base domain.
* **Parameters:**

  * `base` (string, required): The base domain to search for subdomains.

### 4. **Recent**

* **URL:** `/recent/<base>`
* **Methods:** `HEAD`, `OPTIONS`, `GET`
* **Description:** List recently discovered subdomains or related activity for a base domain.
* **Parameters:**

  * `base` (string, required): The base domain to query recent activity for.

### 5. **TLD**

* **URL:** `/tld/<tld>`
* **Methods:** `HEAD`, `OPTIONS`, `GET`
* **Description:** Fetch information about a specific top-level domain (TLD).
* **Parameters:**

  * `tld` (string, required): The top-level domain (e.g., `com`, `org`) to query.

### 6. **Stats**

* **URL:** `/stats`
* **Methods:** `HEAD`, `OPTIONS`, `GET`
* **Description:** Retrieve overall statistics from the API, such as the number of domains, subdomains, or other relevant metrics.


### 7. **Size**

* **URL:** `/size`
* **Methods:** `HEAD`, `OPTIONS`, `GET`
* **Description:** Returns the current size or count of records in the database.

### 8. **Stream**

* **URL:** `/stream`
* **Methods:** `HEAD`, `OPTIONS`, `GET`
* **Description:** Provides a real-time stream of domain-related events or updates.

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

Configured in `.env` file.

---

## Contributing

* Fork the repo
* Make feature branches
* Test thoroughly with Docker Compose
* Submit PRs with clear description

---

## License

MIT License - free to use, modify, and distribute.
