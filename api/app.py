from flask import Flask, jsonify, Response, stream_with_context, request
import clickhouse_connect
import os
import time
from datetime import datetime


# ---------------- CONFIG ----------------

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
RATE_LIMIT = os.getenv("RATE_LIMIT", "100/minute")

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", 8123))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "ct")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "defaultuser")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "defaultpassword")


app = Flask(__name__)

IPS_FILE = "ips.txt"
allowed_ips = None

def load_allowed_ips():
    global allowed_ips
    if os.path.exists(IPS_FILE):
        with open(IPS_FILE, "r") as f:
            allowed_ips = {
                line.strip()
                for line in f
                if line.strip() and not line.startswith("#")
            }
    else:
        allowed_ips = None


load_allowed_ips()

@app.before_request
def restrict_by_ip():
    if allowed_ips is None:
        return

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    if client_ip not in allowed_ips:
        return jsonify({"error": "Access denied"}), 403



if RATE_LIMIT_ENABLED:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[RATE_LIMIT],
    )

ch = clickhouse_connect.get_client(
    host=CLICKHOUSE_HOST,
    port=CLICKHOUSE_PORT,
    database=CLICKHOUSE_DB,
    username=CLICKHOUSE_USER,
    password=CLICKHOUSE_PASSWORD,
)


@app.route("/")
def index():
    endpoints = []
    for rule in app.url_map.iter_rules():
        if "GET" in rule.methods and not rule.rule.startswith("/static"):
            endpoints.append({
                "endpoint": rule.endpoint,
                "url": rule.rule,
                "methods": list(rule.methods)
            })
    return jsonify(endpoints)


@app.route("/domain/<name>")
def domain(name):
    r = ch.query(
        "SELECT * FROM cert_domains WHERE domain=%(d)s ORDER BY ts DESC LIMIT 100",
        parameters={"d": name},
    )

    def decode_row(row):
        return [
            col.decode() if isinstance(col, bytes) else col
            for col in row
        ]

    decoded_rows = [decode_row(row) for row in r.result_rows]
    return jsonify(decoded_rows)

@app.route("/subdomains/<base>")
def subdomains(base):
    r = ch.query(
        "SELECT domain, max(ts) last_seen "
        "FROM cert_domains WHERE base_domain=%(b)s "
        "GROUP BY domain ORDER BY domain",
        parameters={"b": base},
    )
    return jsonify(r.result_rows)

@app.route("/recent/<base>")
def recent(base):
    r = ch.query(
        "SELECT domain FROM cert_domains "
        "WHERE base_domain=%(b)s "
        "AND ts > now() - INTERVAL 1 DAY "
        "GROUP BY domain",
        parameters={"b": base},
    )
    return jsonify(r.result_rows)



# /tld/rs?limit=500
@app.route("/tld/<tld>")
def tld(tld):
    # Default + max limits
    DEFAULT_LIMIT = 100
    MAX_LIMIT = 1000

    try:
        limit = int(request.args.get("limit", DEFAULT_LIMIT))
    except ValueError:
        limit = DEFAULT_LIMIT

    limit = max(1, min(limit, MAX_LIMIT))

    tld = tld.lower().lstrip(".")
    pattern = f"%.{tld}"

    query = f"""
        SELECT domain, max(ts) AS last_seen
        FROM cert_domains
        WHERE domain LIKE %(pattern)s
        GROUP BY domain
        ORDER BY last_seen DESC
        LIMIT {limit}
    """

    r = ch.query(query, parameters={"pattern": pattern})

    def decode_row(row):
        return [
            col.decode() if isinstance(col, bytes) else col
            for col in row
        ]

    decoded_rows = [decode_row(row) for row in r.result_rows]
    return jsonify(decoded_rows)




@app.route("/stats")
def stats():
    date_str = request.args.get("date")

    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            where_clause = "toDate(ts) = %(d)s"
            params = {"d": target_date}
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    else:
        where_clause = "toDate(ts) = today()"
        params = {}

    query = f"""
        SELECT
            count() AS total,
            countDistinct(domain) AS subdomains,
            countDistinct(base_domain) AS domains,
            min(ts) AS first_seen,
            max(ts) AS last_seen
        FROM cert_domains
        WHERE {where_clause}
    """

    r = ch.query(query, parameters=params)

    if not r.result_rows:
        return jsonify({})

    row = r.result_rows[0]
    data = dict(zip(r.column_names, row))

    for k, v in data.items():
        if isinstance(v, bytes):
            data[k] = v.decode()

    data["date"] = date_str or "today"

    return jsonify(data)



last_ts = None

@app.route("/stream")
def stream():
    def event_stream():
        global last_ts
        while True:
            query = "SELECT * FROM cert_domains "
            if last_ts:
                query += f"WHERE ts > '{last_ts}' "
            query += "ORDER BY ts ASC LIMIT 100"

            result = ch.query(query)
            rows = result.result_rows

            if rows:
                for row in rows:
                    yield f"data: {row}\n\n"
                last_ts = rows[-1][result.column_names.index("ts")]

            time.sleep(2)

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")






if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
  
