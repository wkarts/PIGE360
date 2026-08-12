from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

StrategyType = Literal["withholding","difal","presumed_credit","return","transfer","adjustment","reversal","import","export","specific_regime"]
RtcMode = Literal["disabled","simulation_only","optional_emit","required_emit"]

class FiscalStrategyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class FiscalLegalSourceCreate(FiscalStrategyModel):
    kind: Literal["act","technical_note","schema","official_table","legal_basis"]
    title: str = Field(min_length=2,max_length=255)
    version_label: str = Field(min_length=1,max_length=120)
    valid_from: date
    valid_until: date|None=None
    source_reference: str|None=Field(default=None,max_length=2000)
    source_sha256: str=Field(pattern=r"^[a-fA-F0-9]{64}$")
    metadata: dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def period(self):
        if self.valid_until and self.valid_until < self.valid_from: raise ValueError("valid_until não pode ser anterior a valid_from")
        return self

class FiscalStrategyRuleCreate(FiscalStrategyModel):
    fiscal_context_id: str
    establishment_code: str|None=Field(default=None,max_length=80)
    strategy_type: StrategyType
    operation_type: str=Field(default="any",min_length=1,max_length=80)
    tax_regime: str=Field(default="any",min_length=1,max_length=80)
    rtc_mode: str=Field(default="any",min_length=1,max_length=40)
    origin_uf: str|None=Field(default=None,min_length=2,max_length=2)
    destination_uf: str|None=Field(default=None,min_length=2,max_length=2)
    valid_from: date
    valid_until: date|None=None
    priority: int=Field(default=100,ge=0,le=100000)
    parameters: dict[str,Any]=Field(default_factory=dict)
    legal_source_id: str|None=None
    @model_validator(mode="after")
    def validate_rule(self):
        if self.valid_until and self.valid_until < self.valid_from: raise ValueError("valid_until não pode ser anterior a valid_from")
        if self.strategy_type=="difal" and (not self.origin_uf or not self.destination_uf): raise ValueError("DIFAL exige origin_uf e destination_uf")
        return self

class FiscalRtcScheduleCreate(FiscalStrategyModel):
    fiscal_context_id: str
    establishment_code: str|None=Field(default=None,max_length=80)
    tax_regime: str=Field(default="any",min_length=1,max_length=80)
    mode: RtcMode
    valid_from: date
    valid_until: date|None=None
    legal_source_id: str|None=None
    notes: str|None=Field(default=None,max_length=4000)
    @model_validator(mode="after")
    def period(self):
        if self.valid_until and self.valid_until < self.valid_from: raise ValueError("valid_until não pode ser anterior a valid_from")
        return self
