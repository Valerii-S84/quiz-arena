from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=6, max_length=256)


class LoginResponse(BaseModel):
    requires_2fa: bool


class Verify2FARequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class SessionResponse(BaseModel):
    email: str
    role: str
    two_factor_verified: bool
