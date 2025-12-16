#!/usr/bin/env python3
"""
  pip install clickhouse-connect cryptography requests publicsuffix2
"""

import base64
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import List

import requests
import clickhouse_connect
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from publicsuffix2 import PublicSuffixList

# ---------------- CONFIG ----------------

LOG_LIST_URL = "https://www.gstatic.com/ct/log_list/v3/log_list.json"
POLL_INTERVAL = 5
BATCH_SIZE = 512
OFFSET_DIR = "offsets"

CLICKHOUSE_HOST = "clickhouse"
CLICKHOUSE_PORT = 8123
CLICKHOUSE_DB = "ct"
CLICKHOUSE_TABLE = "cert_domains"

VERBOSE = True

# ---------------------------------------

os.makedirs(OFFSET_DIR, exist_ok=True)
psl = PublicSuffixList()

logging.basicConfig(
    level=logging.DEBUG if VERBOSE else logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
)
log = logging.getLogger("ct")

# ---------------- DISCOVERY ----------------

def discover_logs():
    r = requests.get(LOG_LIST_URL, timeout=20)
    r.raise_for_status()
    data = r.json()

    logs = []
    now = datetime.now(timezone.utc)

    for operator in data["operators"]:
        for l in operator["logs"]:
            state = l.get("state", {})
            if "retired" in state:
                continue
            if not ("usable" in state or "frozen" in state):
                continue

            interval = l["temporal_interval"]
            start = datetime.fromisoformat(interval["start_inclusive"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(interval["end_exclusive"].replace("Z", "+00:00"))
            if not (start <= now < end):
                continue

            logs.append({
                "name": l["description"],
                "url": l["url"].rstrip("/"),
                "state": "usable" if "usable" in state else "frozen",
            })

    return logs

# ---------------- CT HELPERS ----------------

def get_tree_size(log_url):
    r = requests.get(f"{log_url}/ct/v1/get-sth", timeout=10)
    r.raise_for_status()
    return r.json()["tree_size"]


def fetch_entries(log_url, start, end):
    r = requests.get(
        f"{log_url}/ct/v1/get-entries?start={start}&end={end}", timeout=30
    )
    r.raise_for_status()
    return r.json()["entries"]


def parse_cert(leaf_input: bytes):
    try:
        # Leaf type (first byte)
        leaf_type = leaf_input[0]
        if leaf_type not in (0, 1):  # 0 = cert, 1 = precert
            return None, [], None
        if leaf_type != 0:  # 0 = timestamped entry, 1 = precert
            log.debug(f"Skipping non-certificate leaf (type={leaf_type})")
            return None, [], None

        # TimestampedEntry structure: skip 12 bytes header (1 type + 8 timestamp + 3 algo)
        offset = 12
        cert_len = int.from_bytes(leaf_input[offset:offset+3], "big")
        cert_der = leaf_input[offset+3 : offset+3+cert_len]
      try:
          cert = x509.load_der_x509_certificate(cert_der, default_backend())
      except Exception as e:
          log.debug(f"Skipping invalid DER cert: {e}, len={len(cert_der)}")
          return None, [], None

        domains = set()
        for attr in cert.subject:
            if attr.oid._name == "commonName":
                domains.add(attr.value.lower())

        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            for d in san.value.get_values_for_type(x509.DNSName):
                domains.add(d.lower())
        except Exception:
            pass

        fingerprint = hashlib.sha256(cert_der).hexdigest()
        return cert, list(domains), fingerprint

    except Exception as e:
        log.debug(f"Failed to parse leaf: {e}, leaf len={len(leaf_input)}")
        return None, [], None


def base_domain(d):
    return psl.get_public_suffix(d)

# ---------------- HORIZONTAL SCALING MODEL ----------------
# One process per CT log using multiprocessing

from multiprocessing import Process

# ---------------- WORKER ----------------

def log_worker(lg):
    name = lg["name"].replace(" ", "_")
    offset_file = f"{OFFSET_DIR}/{name}.offset"

    ch = clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        database=CLICKHOUSE_DB,
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "mysecretpassword"),
    )

    log.info(f"Worker started for {name} ({lg['state']})")

    metrics = {"certs": 0, "domains": 0}

    while True:
        try:
            idx = int(open(offset_file).read()) if os.path.exists(offset_file) else 0
            size = get_tree_size(lg["url"])

            if idx >= size:
                if lg["state"] == "frozen":
                    log.info(f"{name} fully ingested (frozen)")
                    return
                time.sleep(POLL_INTERVAL)
                continue

            end = min(idx + BATCH_SIZE, size - 1)
            entries = fetch_entries(lg["url"], idx, end)
            rows = []

            for i, e in enumerate(entries):
                leaf = base64.b64decode(e["leaf_input"])
                cert, domains, fp = parse_cert(leaf)
                if cert is None:
                    continue
                if not domains:
                    log.debug(f"No domains found for cert {fp}")
                    continue

                for d in domains:
                    rows.append([
                        datetime.utcnow(),
                        d,
                        base_domain(d),
                        fp,
                        cert.issuer.rfc4514_string(),
                        cert.subject.rfc4514_string(),
                        domains,
                        cert.not_valid_before,
                        cert.not_valid_after,
                        name,
                    ])

            if rows:
                ch.insert(
                    CLICKHOUSE_TABLE,
                    rows,
                    column_names=[
                        "ts",
                        "domain",
                        "base_domain",
                        "fingerprint",
                        "issuer",
                        "subject",
                        "san",
                        "not_before",
                        "not_after",
                        "log_name",
                    ],
                )

                metrics["domains"] += len(rows)
                metrics["certs"] += len(set(r[3] for r in rows))
                log.info(f"[{name}] domains={metrics['domains']} certs={metrics['certs']}")

            idx = end + 1
            open(offset_file, "w").write(str(idx))

        except Exception as e:
            log.error(f"[{name}] error: {e}")
            time.sleep(5)


# ---------------- MAIN ----------------

def main():
    log.info("Starting CT ingestion (horizontal scaling enabled)")

    logs = discover_logs()
    log.info(f"Discovered {len(logs)} CT logs")

    procs = []
    for lg in logs:
        p = Process(target=log_worker, args=(lg,), daemon=True)
        p.start()
        procs.append(p)

    for p in procs:
        p.join()


if __name__ == "__main__":
    main()
