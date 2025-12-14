# ct-clickhouse
Auto-discovers CT logs, stores them in a ClickHouse database and optionally exposes a REST API



## Usage

```bash
git clone https://github.com/stefanpejcic/ct-clickhouse
cd ct-clickhouse
```

without api:
```bash
docker compose up --build
```

with api:
```bash
docker compose --profile api up --build
```



## API

example:

```bash
curl http://localhost:5000/domain/example.com
curl http://localhost:5000/subdomains/example.com
curl http://localhost:5000/recent_subdomains/example.com
```
