"""
System configuration for immutable deployment versions.
Provides static definitions for component release versions.
"""

APP_VERSION = "v1.10.0"
GATEWAY_VERSION = "v8.1.0"
SCHEMA_VERSION = "v3.0.0"
STAT_ENGINE_VERSION = "v2.0.0"

def get_system_versions() -> dict:
    return {
        "app_version": APP_VERSION,
        "gateway_version": GATEWAY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "stat_engine_version": STAT_ENGINE_VERSION
    }
