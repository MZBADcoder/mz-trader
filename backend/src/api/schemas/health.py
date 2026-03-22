"""Health endpoint DTOs."""

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Response for application health probes."""

    status: str
    request_id: str

    model_config = ConfigDict(from_attributes=True)
