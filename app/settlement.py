from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Transfer:
    from_person: str
    to_person: str
    amount: Decimal


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
    Fair shares are rounded to the cent, with any rounding residue folded into
    the last person (by iteration order) so balances always sum to zero.
    """
    people = list(totals.keys())
    n = len(people)
    if n == 0:
        return {}

    total = sum(totals.values(), Decimal("0"))
    raw_share = (total / n).quantize(CENT, rounding=ROUND_HALF_UP)

    shares = {person: raw_share for person in people}
    residual = total - (raw_share * n)
    if residual != 0:
        last_person = people[-1]
        shares[last_person] = shares[last_person] + residual

    return {person: totals[person] - shares[person] for person in people}


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
