from prometheus_client import Counter, Histogram

# ---- Counters ----
MEMORY_EXTRACTION_TOTAL = Counter(
    "memory_extraction_total",
    "Total memory extraction attempts"
)

MEMORY_EXTRACTION_FAILURES = Counter(
    "memory_extraction_failures_total",
    "Total memory extraction failures"
)

MEMORY_EXTRACTED_TOTAL = Counter(
    "memory_extracted_total",
    "Extracted memories by type",
    ["type"]
)

PII_ENCRYPTED_TOTAL = Counter(
    "memory_pii_encrypted_total",
    "Total semantic facts encrypted",
    ["type"]
)

SEMANTIC_SAVE_TOTAL = Counter(
    "semantic_save_total",
    "Total semantic memory saves",
    ["encrypted"]
)

SEMANTIC_VERSIONED_TOTAL = Counter(
    "semantic_versioned_total",
    "Number of semantic memories superseded by newer versions"
)

# ---- Histograms ----
MEMORY_EXTRACTION_LATENCY = Histogram(
    "memory_extraction_latency_seconds",
    "Latency of memory extraction"
)

SUMMARY_LATENCY = Histogram(
    "memory_summary_latency_seconds",
    "Latency of conversation summarization"
)
