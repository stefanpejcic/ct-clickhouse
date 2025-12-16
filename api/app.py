from flask import Flask, jsonify, Response, stream_with_context
import clickhouse_connect
import os
import time

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
RATE_LIMIT = os.getenv("RATE_LIMIT", "100/minute")

app = Flask(__name__)

if RATE_LIMIT_ENABLED:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[RATE_LIMIT],
    )

ch = clickhouse_connect.get_client(
    host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
    database=os.getenv("CLICKHOUSE_DB", "ct"),
    username=os.getenv("CLICKHOUSE_USER", "default"),
    password=os.getenv("CLICKHOUSE_PASSWORD", "mysecretpassword")
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
  
