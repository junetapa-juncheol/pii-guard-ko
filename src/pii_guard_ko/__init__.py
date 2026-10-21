"""Korean personal data scanner."""

__version__ = "0.1.0"

from .detect import Finding, LABELS, scan_text  # noqa: E402

__all__ = ["Finding", "LABELS", "scan_text", "__version__"]
