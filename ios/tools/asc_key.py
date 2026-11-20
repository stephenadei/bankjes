#!/usr/bin/env python3
"""Fetch the App Store Connect API key from Infisical for bin/testflight.

Usage: asc_key.py <bootstrap-env> <p8-out>
  - Reads the bootstrap env (INFISICAL_DOMAIN, INFISICAL_PROJECT_ID, INFISICAL_ENV, INFISICAL_PATH,
    INFISICAL_UA_CLIENT_ID, INFISICAL_UA_CLIENT_SECRET, optional CF_ACCESS_CLIENT_ID/SECRET).
  - Logs in with Universal Auth, reads ASC_KEY_ID, ASC_ISSUER_ID and ASC_KEY_P8.
  - Writes the .p8 to <p8-out> with mode 0600 and prints only `ASC_KEY_ID=… ASC_ISSUER_ID=…`
    (neither is secret). Secrets never go on a command line or to stdout/stderr.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

NEEDED = ("INFISICAL_DOMAIN", "INFISICAL_PROJECT_ID", "INFISICAL_ENV", "INFISICAL_PATH",
          "INFISICAL_UA_CLIENT_ID", "INFISICAL_UA_CLIENT_SECRET")


def die(msg):
    print(f"asc_key: {msg}", file=sys.stderr)
    sys.exit(2)


def load_env(path):
    env = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            env[k.strip()] = v
    return env


def request(env, url, body=None, token=None):
    headers = {"Accept": "application/json", "User-Agent": "bankjes-testflight"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if env.get("CF_ACCESS_CLIENT_ID") and env.get("CF_ACCESS_CLIENT_SECRET"):
        headers["CF-Access-Client-Id"] = env["CF_ACCESS_CLIENT_ID"]
        headers["CF-Access-Client-Secret"] = env["CF_ACCESS_CLIENT_SECRET"]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:  # status only: response bodies may echo request data
        die(f"{url.split('?')[0]} -> HTTP {e.code}")
    except urllib.error.URLError as e:
        die(f"cannot reach {env['INFISICAL_DOMAIN']} ({e.reason}); is the tunnel up?")


def main():
    if len(sys.argv) != 3:
        die("usage: asc_key.py <bootstrap-env> <p8-out>")
    env = load_env(sys.argv[1])
    missing = [k for k in NEEDED if not env.get(k)]
    if missing:
        die("bootstrap env missing: " + " ".join(missing))
    base = env["INFISICAL_DOMAIN"].rstrip("/")
    login = request(env, f"{base}/api/v1/auth/universal-auth/login",
                    {"clientId": env["INFISICAL_UA_CLIENT_ID"],
                     "clientSecret": env["INFISICAL_UA_CLIENT_SECRET"]})
    token = login.get("accessToken") or die("login returned no token")
    q = urllib.parse.urlencode({"workspaceId": env["INFISICAL_PROJECT_ID"],
                                "environment": env["INFISICAL_ENV"],
                                "secretPath": env["INFISICAL_PATH"]})
    vals = {}
    for name in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_P8"):
        res = request(env, f"{base}/api/v3/secrets/raw/{name}?{q}", token=token)
        v = ((res or {}).get("secret") or {}).get("secretValue") or ""
        if not v.strip():
            die(f"{name} is empty in Infisical ({env['INFISICAL_PATH']}); fill it in first")
        vals[name] = v.strip()
    if "BEGIN PRIVATE KEY" not in vals["ASC_KEY_P8"]:
        die("ASC_KEY_P8 does not look like a .p8 key (no BEGIN PRIVATE KEY line)")
    fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(vals["ASC_KEY_P8"] + "\n")
    print(f"ASC_KEY_ID={vals['ASC_KEY_ID']} ASC_ISSUER_ID={vals['ASC_ISSUER_ID']}")


if __name__ == "__main__":
    main()
