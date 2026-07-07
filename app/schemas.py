from decimal import Decimal

from pydantic import BaseModel, field_validator


class EventCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Название мероприятия не может быть пустым")
        return v


class ExpenseCreate(BaseModel):
    payer_name: str
    description: str = ""
    amount: Decimal

    @field_validator("payer_name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Поле не может быть пустым")
        return v

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: str) -> str:
        return v.strip()

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Сумма должна быть больше нуля")
        return v
