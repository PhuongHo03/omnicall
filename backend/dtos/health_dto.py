from pydantic import BaseModel


class HealthResponse(BaseModel):
    app: str
    status: str
