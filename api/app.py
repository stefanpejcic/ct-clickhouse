from flask import Flask, jsonify, request
import clickhouse_connect


import os


CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "ct")


ch = clickhouse_connect.get_client(host=CLICKHOUSE_HOST, database=CLICKHOUSE_DB)
app = Flask(__name__)


@app.route('/domain/<name>')
def domain_search(name):
  result = ch.query(f"SELECT * FROM cert_domains WHERE domain = '{name}' ORDER BY ts DESC LIMIT 100")
  return jsonify(result.result_rows)


@app.route('/subdomains/<base>')
def subdomains(base):
  result = ch.query(f"SELECT domain, max(ts) as last_seen FROM cert_domains WHERE base_domain = '{base}' GROUP BY domain ORDER BY domain")
  return jsonify(result.result_rows)


@app.route('/recent_subdomains/<base>')
def recent_subdomains(base):
  result = ch.query(f"SELECT domain FROM cert_domains WHERE base_domain='{base}' AND ts > now() - INTERVAL 1 DAY GROUP BY domain")
  return jsonify(result.result_rows)


if __name__ == '__main__':
  app.run(host='0.0.0.0', port=5000)
