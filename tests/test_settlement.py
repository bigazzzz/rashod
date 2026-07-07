from decimal import Decimal

from app.settlement import compute_balances, compute_totals, settle_debts


def test_compute_totals_sums_per_person():
    expenses = [("Alice", Decimal("10")), ("Bob", Decimal("5")), ("Alice", Decimal("5"))]
    totals = compute_totals(expenses)
    assert totals == {"Alice": Decimal("15"), "Bob": Decimal("5")}


def test_compute_totals_merges_names_case_insensitively():
    expenses = [
        ("Alice", Decimal("10")),
        ("alice", Decimal("5")),
        ("ALICE", Decimal("1")),
        ("Bob", Decimal("2")),
    ]
    totals = compute_totals(expenses)
    # first-seen spelling ("Alice") is kept as the display name
    assert totals == {"Alice": Decimal("16"), "Bob": Decimal("2")}


def test_three_people_one_payer():
    totals = {"A": Decimal("30"), "B": Decimal("0"), "C": Decimal("0")}
    balances = compute_balances(totals)
    assert balances == {"A": Decimal("20.00"), "B": Decimal("-10.00"), "C": Decimal("-10.00")}

    transfers = settle_debts(balances)
    assert len(transfers) == 2
    assert {(t.from_person, t.to_person, t.amount) for t in transfers} == {
        ("B", "A", Decimal("10.00")),
        ("C", "A", Decimal("10.00")),
    }


def test_no_expenses():
    totals = compute_totals([])
    balances = compute_balances(totals)
    assert balances == {}
    assert settle_debts(balances) == []


def test_single_participant_no_transfers():
    totals = {"A": Decimal("42.00")}
    balances = compute_balances(totals)
    assert balances == {"A": Decimal("0.00")}
    assert settle_debts(balances) == []


def test_already_balanced_no_transfers():
    totals = {"A": Decimal("10.00"), "B": Decimal("10.00")}
    balances = compute_balances(totals)
    assert settle_debts(balances) == []


def test_rounding_residual_sums_to_total():
    # 10 / 3 = 3.33333... ; shares must still sum exactly to 10, and every
    # transfer into A must reconcile with A's overpayment balance.
    totals = {"A": Decimal("10.00"), "B": Decimal("0.00"), "C": Decimal("0.00")}
    balances = compute_balances(totals)
    assert sum(balances.values()) == Decimal("0.00")

    transfers = settle_debts(balances)
    paid_to_a = sum(t.amount for t in transfers if t.to_person == "A")
    assert paid_to_a == balances["A"]
    assert paid_to_a == Decimal("6.67")
