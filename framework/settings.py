"""
Instance settings: config/settings.yaml + environment variable overrides.

Secrets never live in code. Precedence (highest wins):
  1. environment variables (TLSOC_ES_HOST, TLSOC_ES_USER, TLSOC_ES_PASS,
     TLSOC_ES_CA_CERT, TLSOC_OUTPUT_DIR)
  2. config/settings.yaml
  3. built-in defaults (safe, non-secret)
"""
import os

import yaml

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates", "framework")

DEFAULTS = {
    "elasticsearch": {
        "host": "https://localhost:9200",
        "user": "elastic",
        "password": "",
        "ca_cert": None,
        "verify_certs": True,
        "request_timeout": 120,
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
    return cfg
