from flask import Flask, jsonify
import clickhouse_connect
import os

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

@app.route("/domain/<name>")
def domain(name):
    r = ch.query(
        "SELECT * FROM cert_domains WHERE domain=%(d)s ORDER BY ts DESC LIMIT 100",
        parameters={"d": name},
    )
    return jsonify(r.result_rows)

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
  
