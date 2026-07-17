"""
Query backends.

Both backends execute CompiledQuery objects and return identical normalized
shapes, so reports render the same whether the data came from the live
cluster or from an offline sample file:

    count/cardinality/sum/avg/min/max  -> number
    terms                 -> [{"key", "count", <sub-agg values>...}, ...]
    date_histogram        -> [{"ts", "label", "count", <sub-aggs>...}, ...]
    range_buckets         -> {"<range key>": count, ...}
    signature_categories  -> [{"key","title","severity","why","count",...}]
    samples               -> [{<logical field>: value, ...}, ...]
"""

from .es import ESBackend               # noqa: F401
from .local import LocalBackend         # noqa: F401
