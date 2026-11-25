from dataclasses import dataclass
from decimal import Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Transfer:
    from_person: str
    to_person: str
    amount: Decimal


def compute_settlement(
    expenses: list[tuple[str, Decimal]],
) -> tuple[Decimal, dict[str, Decimal], list[Transfer]]:
    totals = compute_totals(expenses)
    return sum(totals.values(), Decimal("0")), totals, settle_debts(compute_balances(totals))


def compute_totals(expenses: list[tuple[str, Decimal]]) -> dict[str, Decimal]:
    """Sum amounts paid per person, matching names case-insensitively.

    "Alice" and "alice" are treated as the same person; the display name
    used is whichever spelling appeared first.
    """
    display_names: dict[str, str] = {}
    totals: dict[str, Decimal] = {}
    for payer_name, amount in expenses:
        key = payer_name.casefold()
        display_names.setdefault(key, payer_name)
        totals[key] = totals.get(key, Decimal("0")) + amount
    return {display_names[key]: total for key, total in totals.items()}


def compute_balances(totals: dict[str, Decimal]) -> dict[str, Decimal]:
    """balance[person] = paid[person] - fair_share.

    Positive balance: overpaid, is owed money. Negative: underpaid, owes money.
    Each person pays the base share in cents. The last participants in
    iteration order cover one additional cent each until the remainder is paid.
    """
    people = list(totals.keys())
    n = len(people)
    if n == 0:
        return {}

    total = sum(totals.values(), Decimal("0"))
    base_cents, remainder = divmod(int(total / CENT), n)
    balances = {}
    for index, person in enumerate(people):
        share = base_cents
        if index >= n - remainder:
            share += 1
        balances[person] = totals[person] - CENT * share
    return balances


def settle_debts(balances: dict[str, Decimal]) -> list[Transfer]:
    """Greedy cash-flow minimization: match largest debtor with largest creditor."""
    creditors = sorted(
        ((p, b) for p, b in balances.items() if b > 0), key=lambda x: x[1], reverse=True
    )
    debtors = sorted(
        ((p, -b) for p, b in balances.items() if b < 0), key=lambda x: x[1], reverse=True
    )

    transfers: list[Transfer] = []
    i, j = 0, 0
    creditors = [list(c) for c in creditors]
    debtors = [list(d) for d in debtors]

    while i < len(debtors) and j < len(creditors):
        debtor_name, debt = debtors[i]
        creditor_name, credit = creditors[j]
        amount = min(debt, credit)

        if amount > 0:
            transfers.append(Transfer(debtor_name, creditor_name, amount))

        debtors[i][1] -= amount
        creditors[j][1] -= amount

        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1

    return transfers
