"""Typed API models for browser-side error reports."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClientErrorReport(BaseModel):
    """A compact error report emitted by the frontend error boundary."""

    message: str = Field(max_length=2000)
    name: str | None = Field(default=None, max_length=200)
    stack: str | None = Field(default=None, max_length=12000)
    component_stack: str | None = Field(default=None, max_length=12000)
    route_name: str | None = Field(default=None, max_length=200)
    href: str | None = Field(default=None, max_length=2000)
    user_agent: str | None = Field(default=None, max_length=1000)

    model_config = ConfigDict(extra="forbid")


class ClientErrorReportResponse(BaseModel):
    """Acknowledgement for browser-side error reports."""

    status: str = "ok"
