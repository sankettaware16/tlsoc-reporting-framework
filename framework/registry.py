"""
Registry: discovers and validates datasources, signature packs and report
definitions from the config/ tree.

Datasource (config/datasources/<name>.yaml)
-------------------------------------------
    name / label / profile / index
    fields:   logical field  ->  concrete ES field  (aggregatable form)
    params:   overrides merged over the report's default params

Signature pack (config/signatures/<name>.yaml)
----------------------------------------------
    target_field: logical field the patterns match against
    categories:   {key: {title, severity, why, patterns: [wildcards]}}

Report definition (config/reports/<name>.yaml)
----------------------------------------------
    profile, title, params, queries, computed, sections,
    insights, actions, badges

Compatibility rule: a report runs against a datasource when their `profile`
strings match, OR the datasource lists the report profile in
`extra_profiles`. No other coupling exists.
"""
import os

import yaml

from .settings import CONFIG_DIR

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class ConfigError(Exception):
    pass


def _load_yaml_dir(path):
    out = {}
    if not os.path.isdir(path):
        return out
    for fn in sorted(os.listdir(path)):
        if not fn.endswith((".yaml", ".yml")):
            continue
        full = os.path.join(path, fn)
        with open(full, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        name = doc.get("name") or os.path.splitext(fn)[0]
        doc["name"] = name
        doc["_file"] = full
        out[name] = doc
    return out


class Datasource:
    def __init__(self, doc):
        self.name = doc["name"]
        self.doc = doc
        self.label = doc.get("label", self.name)
        self.profile = doc.get("profile")
        self.index = doc.get("index")
        self.fields = doc.get("fields") or {}
        self.params = doc.get("params") or {}
        self.extra_profiles = doc.get("extra_profiles") or []
        if not self.profile:
            raise ConfigError(f"datasource {self.name}: missing 'profile'")
        if not self.index:
            raise ConfigError(f"datasource {self.name}: missing 'index'")

    def supports(self, profile):
        return profile == self.profile or profile in self.extra_profiles

    def resolve(self, logical_field):
        """Logical -> concrete ES field, or None when unmapped."""
        return self.fields.get(logical_field)


class SignaturePack:
    def __init__(self, doc):
        self.name = doc["name"]
        self.doc = doc
        self.target_field = doc.get("target_field")
        self.categories = doc.get("categories") or {}
        if not self.target_field:
            raise ConfigError(f"signature pack {self.name}: "
                              f"missing 'target_field'")
        for key, cat in self.categories.items():
            if not cat.get("patterns"):
                raise ConfigError(f"signature pack {self.name}: category "
                                  f"{key} has no patterns")
            cat.setdefault("title", key)
            cat.setdefault("severity", "medium")
            cat.setdefault("why", "")

    def patterns(self, severities=None, category=None):
        cats = self.categories
        if category:
            if category not in cats:
                raise ConfigError(f"signature pack {self.name}: "
                                  f"unknown category '{category}'")
            cats = {category: cats[category]}
        out = []
        for cat in cats.values():
            if severities and cat["severity"] not in severities:
                continue
            out.extend(cat["patterns"])
        return out


class ReportDef:
    def __init__(self, doc):
        self.name = doc["name"]
        self.doc = doc
        self.profile = doc.get("profile")
        self.title = doc.get("title", self.name)
        self.description = doc.get("description", "")
        self.params = doc.get("params") or {}
        self.queries = doc.get("queries") or {}
        self.computed = doc.get("computed") or []
        self.sections = doc.get("sections") or []
        self.insights = doc.get("insights") or []
        self.actions = doc.get("actions") or []
        self.badges = doc.get("badges") or []
        if not self.profile:
            raise ConfigError(f"report {self.name}: missing 'profile'")
        if not self.sections:
            raise ConfigError(f"report {self.name}: no sections defined")


class Registry:
    def __init__(self, config_dir=None):
        config_dir = config_dir or CONFIG_DIR
        self.datasources = {
            n: Datasource(d)
            for n, d in _load_yaml_dir(
                os.path.join(config_dir, "datasources")).items()}
        self.signatures = {
            n: SignaturePack(d)
            for n, d in _load_yaml_dir(
                os.path.join(config_dir, "signatures")).items()}
        self.reports = {
            n: ReportDef(d)
            for n, d in _load_yaml_dir(
                os.path.join(config_dir, "reports")).items()}

    def pairs(self):
        """All runnable (report, datasource) combinations."""
        out = []
        for rep in self.reports.values():
            for ds in self.datasources.values():
                if ds.supports(rep.profile):
                    out.append((rep, ds))
        return out

    def merged_params(self, report, datasource, cli_params=None):
        """report defaults <- datasource overrides <- CLI overrides."""
        out = dict(report.params)
        for k, v in datasource.params.items():
            if isinstance(v, list) and k.startswith("extra_"):
                base_key = k[len("extra_"):]
                out[base_key] = list(out.get(base_key, [])) + v
            else:
                out[k] = v
        for k, v in (cli_params or {}).items():
            out[k] = v
        return out
