from decimal import Decimal

from pydantic import BaseModel, field_validator


class EventCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Название события не может быть пустым")
        return v


class ExpenseCreate(BaseModel):
    payer_name: str
    description: str = ""
    amount: Decimal

    @field_validator("payer_name")
    @classmethod
    def strip_payer_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: str) -> str:
        return v.strip()

    @field_validator("amount")
    @classmethod
    def amount_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Сумма не может быть отрицательной")
        if v > Decimal("99999999.99"):
            raise ValueError("Максимальная сумма — 99 999 999,99")
        rounded = v.quantize(Decimal("0.01"))
        if v != rounded:
            raise ValueError("Укажите сумму с точностью до копейки")
        return rounded
