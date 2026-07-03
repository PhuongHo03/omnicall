from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str


class DeleteResponse(BaseModel):
    id: str
    deleted: bool
