"""
Instance settings: config/settings.yaml + environment variable overrides.

Secrets never live in code. Precedence (highest wins):
  1. environment variables (TLSOC_ES_HOST, TLSOC_ES_USER, TLSOC_ES_PASS,
     TLSOC_ES_CA_CERT, TLSOC_OUTPUT_DIR)
  2. config/settings.yaml
  3. auto-detected co-located TLSOC docker deployment (see below)
  4. built-in defaults (safe, non-secret)

Zero-config on TLSOC hosts
--------------------------
This framework is the reporting companion of the TLSOC docker stack. When
that stack lives on the same host (default /opt/TLSOCDockerDeploy), its
own .env and certs already contain everything needed to talk to
Elasticsearch - so any connection value NOT set explicitly is filled from
the deployment automatically:

    host      <- https://<HOST_IP>:9200        (deployment .env)
    password  <- ELASTIC_PASSWORD              (deployment .env)
    ca_cert   <- <deploy dir>/certs/ca/ca.crt

Explicit values (env var or settings.yaml) always win, and hosts without
the stack simply fall back to manual configuration.
"""
import os
import sys

import yaml

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates", "framework")

DEFAULTS = {
    "elasticsearch": {
        "host": "",
        "user": "elastic",
        "password": "",
        "ca_cert": None,
        "verify_certs": True,
        "request_timeout": 120,
    },
    "tlsoc_deploy": {
        "autodetect": True,
        "dir": "/opt/TLSOCDockerDeploy",
    },
    "org": {
        "name": "Organisation",
        "department": "",
        "classification": "Internal / Restricted",
    },
    "locale": {
        "timezone": "UTC",
        "tz_label": "UTC",
    },
    "output": {
        "html_dir": os.path.join(BASE_DIR, "output", "html"),
        "pdf_dir": os.path.join(BASE_DIR, "output", "pdf"),
        "formats": ["html", "pdf"],
    },
    "pdf": {
        # Engines are tried in order; first available wins.
        "engines": ["wkhtmltopdf", "chrome", "weasyprint"],
        "wkhtmltopdf_path": None,   # autodetect from PATH when null
        "chrome_path": None,        # autodetect when null
    },
}

ENV_OVERRIDES = {
    ("elasticsearch", "host"): "TLSOC_ES_HOST",
    ("elasticsearch", "user"): "TLSOC_ES_USER",
    ("elasticsearch", "password"): "TLSOC_ES_PASS",
    ("elasticsearch", "ca_cert"): "TLSOC_ES_CA_CERT",
    ("output", "html_dir"): "TLSOC_OUTPUT_HTML_DIR",
    ("output", "pdf_dir"): "TLSOC_OUTPUT_PDF_DIR",
}


def _deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _parse_env_file(path):
    """Minimal KEY=VALUE parser for the deployment's docker .env file."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                out[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        return {}
    return out


# Host values that mean "nothing was configured explicitly".
_PLACEHOLDER_HOSTS = {"", "https://localhost:9200",
                      "https://YOUR-ELK-HOST:9200"}


def _autodetect_tlsoc(cfg):
    """Fill missing ES connection values from a co-located TLSOC stack."""
    deploy = cfg.get("tlsoc_deploy") or {}
    if not deploy.get("autodetect", True):
        return
    deploy_dir = deploy.get("dir") or "/opt/TLSOCDockerDeploy"
    env = _parse_env_file(os.path.join(deploy_dir, ".env"))
    if not env:
        return
    es = cfg["elasticsearch"]
    found = []
    if (es.get("host") or "") in _PLACEHOLDER_HOSTS and env.get("HOST_IP"):
        es["host"] = f"https://{env['HOST_IP']}:9200"
        found.append(f"host={es['host']}")
    if not es.get("password") and env.get("ELASTIC_PASSWORD"):
        es["password"] = env["ELASTIC_PASSWORD"]
        found.append("password")
    ca_path = os.path.join(deploy_dir, "certs", "ca", "ca.crt")
    if not es.get("ca_cert") and os.path.exists(ca_path):
        es["ca_cert"] = ca_path
        found.append("ca_cert")
    if found:
        print(f"[settings] auto-detected TLSOC deployment in {deploy_dir}: "
              + ", ".join(found), file=sys.stderr)


def load_settings(path=None):
    path = path or os.path.join(CONFIG_DIR, "settings.yaml")
    file_cfg = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            file_cfg = yaml.safe_load(f) or {}
    cfg = _deep_merge(DEFAULTS, file_cfg)
    for (section, key), env in ENV_OVERRIDES.items():
        if os.environ.get(env):
            cfg.setdefault(section, {})[key] = os.environ[env]
    _autodetect_tlsoc(cfg)
    return cfg
