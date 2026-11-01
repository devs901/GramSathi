"""Pydantic request models (validation lives here, not scattered in handlers)."""
from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_MOBILE = re.compile(r"^[6-9]\d{9}$")  # Indian mobile numbers


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=120)
    mobile: str
    age: int = Field(ge=1, le=120)
    password: str = Field(min_length=8, max_length=128)
    address: str = Field(default="", max_length=250)
    village: str = Field(default="", max_length=80)

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, v: str) -> str:
        v = re.sub(r"[\s-]", "", v).removeprefix("+91")
        if not _MOBILE.match(v):
            raise ValueError("must be a valid 10-digit Indian mobile number")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("must contain letters and numbers")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    address: str | None = Field(default=None, max_length=250)
    village: str | None = Field(default=None, max_length=80)
    mobile: str | None = None

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = re.sub(r"[\s-]", "", v).removeprefix("+91")
        if not _MOBILE.match(v):
            raise ValueError("must be a valid 10-digit Indian mobile number")
        return v


class UserAdminUpdateIn(BaseModel):
    is_active: bool | None = None
    role: Literal["citizen", "admin"] | None = None


class DocumentIn(BaseModel):
    doc_type: Literal["birth_certificate", "bonafide_certificate"]
    full_name: str = Field(min_length=2, max_length=80)
    date_of_birth: date
    father_name: str = Field(min_length=2, max_length=80)
    mother_name: str = Field(default="", max_length=80)
    address: str = Field(min_length=5, max_length=250)
    place_of_birth: str = Field(default="", max_length=120)
    purpose: str = Field(default="", max_length=200)
    school_name: str = Field(default="", max_length=150)

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("cannot be in the future")
        return v


class ReviewIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=500)


class NewsIn(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=5, max_length=2000)
    category: Literal["scheme", "deadline", "alert", "health", "general"] = "general"
    priority: int = Field(default=3, ge=1, le=5)
    active: bool = True
    title_hi: str = ""
    description_hi: str = ""
    title_mr: str = ""
    description_mr: str = ""


class NewsDraftIn(BaseModel):
    points: str = Field(min_length=5, max_length=1500, description="Rough bullet points from the admin")


class RationItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    quantity: float = Field(ge=0)
    unit: str = Field(default="kg", max_length=10)


class RationIn(BaseModel):
    user_id: int
    card_no: str = Field(min_length=4, max_length=30)
    card_type: Literal["APL", "BPL", "AAY"]
    validity_start: date
    validity_end: date
    distribution_point: str = Field(default="", max_length=150)
    status: Literal["active", "inactive", "expired"] = "active"
    items: list[RationItemIn] = []

    @field_validator("validity_end")
    @classmethod
    def _order(cls, v: date, info):
        start = info.data.get("validity_start")
        if start and v < start:
            raise ValueError("must be on or after validity_start")
        return v


class CenterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=3, max_length=250)
    phone: str = Field(default="", max_length=20)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    services: list[str] = []
    open_time: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    close_time: str = Field(default="16:00", pattern=r"^\d{2}:\d{2}$")


class WaterBillIn(BaseModel):
    user_id: int
    connection_no: str = Field(min_length=3, max_length=30)
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount: float = Field(ge=0)
    due_date: date


class PropertyIn(BaseModel):
    user_id: int
    property_no: str = Field(min_length=3, max_length=30)
    address: str = Field(min_length=3, max_length=250)
    area_sqft: float = Field(gt=0)
    value: float = Field(ge=0)
    tax_rate: float = Field(ge=0, le=100)
    due_date: date


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    language: Literal["en", "hi", "mr"] = "en"


class BeneficiaryIn(BaseModel):
    user_id: int
    center_id: int
    child_name: str = Field(min_length=2, max_length=80)
    age_group: Literal["0-6", "6-14"]
    status: Literal["active", "inactive"] = "active"
    enrollment_date: date
