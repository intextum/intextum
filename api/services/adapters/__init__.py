"""Data source adapters — pluggable file-operation backends."""

from .base import ContentEntry, DataConnectorAdapter

__all__ = ["DataConnectorAdapter", "ContentEntry"]
