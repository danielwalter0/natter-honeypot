"""Natter report schema, version 1.

This file is the single source of truth for the shape of a call report.
Agents must not change it without asking (see CLAUDE.md).

The types below only describe SHAPE. The rules that make the dossier
trustworthy are NOT expressed here. The schema check must enforce them in
plain code, with tests:

1. Every Evidence.quote appears verbatim (after whitespace normalisation) in
   the turn named by Evidence.turn, and that turn was spoken by the scammer.
2. Stage never moves backwards (compare using STAGE_ORDER).
3. Anything that fails rules 1 or 2 is dropped and logged, never accepted.
4. Dossier.caller_type is a Judgement. It has no quote because "sounds
   synthetic" is not something a caller says. It is exempt from rule 1 and is
   scored separately in the evaluation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    """Reject unknown fields so a model cannot smuggle extra data into a report."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- enums


class ScamType(StrEnum):
    BANK_IMPERSONATION = "bank_impersonation"
    TECH_SUPPORT = "tech_support"
    TAX_AUTHORITY = "tax_authority"
    PARCEL_DELIVERY = "parcel_delivery"
    OTHER = "other"


class Stage(StrEnum):
    HOOK = "hook"
    PRESSURE = "pressure"
    PAYMENT_ASK = "payment_ask"
    CLOSING = "closing"


STAGE_ORDER: dict[Stage, int] = {
    Stage.HOOK: 0,
    Stage.PRESSURE: 1,
    Stage.PAYMENT_ASK: 2,
    Stage.CLOSING: 3,
}


class PaymentMethod(StrEnum):
    BANK_TRANSFER = "bank_transfer"
    GIFT_CARDS = "gift_cards"
    CRYPTO = "crypto"
    CASH_COURIER = "cash_courier"
    CARD_DETAILS = "card_details"
    REMOTE_ACCESS = "remote_access"
    OTHER = "other"


class IdentifierKind(StrEnum):
    PHONE = "phone"
    URL = "url"
    EMAIL = "email"
    ACCOUNT_NUMBER = "account_number"
    ALIAS = "alias"
    CASE_REFERENCE = "case_reference"


class Tactic(StrEnum):
    URGENCY = "urgency"
    AUTHORITY = "authority"
    FEAR = "fear"
    SECRECY = "secrecy"
    ISOLATION = "isolation"


class InfoRequested(StrEnum):
    ONE_TIME_CODE = "one_time_code"
    PIN = "pin"
    FULL_CARD_NUMBER = "full_card_number"
    PASSWORD = "password"  # noqa: S105  enum label for what was asked, not a secret
    REMOTE_ACCESS = "remote_access"
    DATE_OF_BIRTH = "date_of_birth"
    OTHER = "other"


class CallerType(StrEnum):
    HUMAN = "human"
    AI_VOICE = "ai_voice"
    RECORDING = "recording"
    UNCLEAR = "unclear"


# ---------------------------------------------------------------- building blocks


class Evidence(_Strict):
    """Proof for one dossier value: which turn, what was said, how sure."""

    turn: int = Field(ge=0)
    quote: str = Field(min_length=3, max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)


class Sourced[T](_Strict):  # Python 3.12 generic syntax: T is the value's type
    """A value plus the evidence that backs it."""

    value: T
    evidence: Evidence


class Money(_Strict):
    amount: float = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class Identifier(_Strict):
    kind: IdentifierKind
    value: str = Field(min_length=1, max_length=200)
    evidence: Evidence


class Judgement(_Strict):
    """An assessment with no quote. Used only for caller_type."""

    value: CallerType
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=200)


# ---------------------------------------------------------------- the dossier


class Dossier(_Strict):
    claimed_organisation: Sourced[str] | None = None
    scam_type: Sourced[ScamType] | None = None
    stage: Sourced[Stage] | None = None
    payment_method: Sourced[PaymentMethod] | None = None
    amount: Sourced[Money] | None = None
    identifiers: list[Identifier] = Field(default_factory=list)
    pressure_tactics: list[Sourced[Tactic]] = Field(default_factory=list)
    information_requested: list[Sourced[InfoRequested]] = Field(default_factory=list)
    injection_attempt: Sourced[bool] | None = None
    caller_type: Judgement | None = None


# ---------------------------------------------------------------- the report


class Turn(_Strict):
    index: int = Field(ge=0)
    speaker: Literal["scammer", "persona"]
    text: str = Field(max_length=2000)


class Report(_Strict):
    schema_version: Literal["1"] = "1"
    # Restricted pattern doubles as path-traversal protection for /api/reports/{id}.
    call_id: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    scenario_id: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    mode: Literal["replay", "live"]
    turns: list[Turn]
    dossier: Dossier
    # Which model and version produced each part, e.g. {"extractor": "claude-sonnet-5-5"}.
    provenance: dict[str, str] = Field(default_factory=dict)
