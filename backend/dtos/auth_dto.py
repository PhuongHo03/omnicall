from datetime import datetime

from pydantic import BaseModel, Field


class AuthRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=160)


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class AccountResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str


class AuthSessionResponse(BaseModel):
    token: str
    expires_at: datetime
    account: AccountResponse


class MeResponse(BaseModel):
    account: AccountResponse
