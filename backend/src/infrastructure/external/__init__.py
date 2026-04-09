"""Infrastructure external adapters."""

from infrastructure.external.massive_reference_client import MassiveReferenceClient
from infrastructure.external.massive_snapshot_client import (
    MassiveSnapshotBatchResponse,
    MassiveSnapshotClient,
)

__all__ = [
    "MassiveReferenceClient",
    "MassiveSnapshotBatchResponse",
    "MassiveSnapshotClient",
]
