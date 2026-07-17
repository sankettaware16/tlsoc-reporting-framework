"""
TLSOC declarative reporting framework.

Nothing report-specific lives in Python. The moving parts are:

  config/settings.yaml        instance settings (ES endpoint, org, output dirs)
  config/datasources/*.yaml   one file per log source: index pattern + a map
                              from LOGICAL field names to concrete ES fields
  config/signatures/*.yaml    shared, categorised signature packs (threats,
                              bot user-agents, ...)
  config/reports/*.yaml       report definitions: queries, computed metrics,
                              sections, insights, actions, badges
  templates/framework/        Jinja2 layout + one partial per widget type

A report definition is written once against logical fields ("client_ip",
"url_path", "status_code"). Any datasource that maps those fields can render
that report - that is what lets a single web_daily definition serve nginx,
moodle/apache, or any future web-ish source without code changes.
"""

__version__ = "1.0.0"
