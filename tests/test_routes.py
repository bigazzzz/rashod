def create_event(client, name="Поездка на дачу"):
    response = client.post("/events", data={"name": name}, follow_redirects=False)
    assert response.status_code == 303
    slug = response.headers["location"].split("/e/")[1]
    return slug


def test_create_event_redirects_to_event_page(client):
    slug = create_event(client)
    response = client.get(f"/e/{slug}")
    assert response.status_code == 200
    assert "Поездка на дачу" in response.text


def test_full_flow_totals_and_settlement(client):
    slug = create_event(client, name="Ужин")

    r1 = client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Alice", "description": "Ужин", "amount": "30"},
        follow_redirects=False,
    )
    assert r1.status_code == 303

    r2 = client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Bob", "description": "Такси", "amount": "0"},
        follow_redirects=False,
    )
    # amount must be > 0, expect validation error re-rendering the event page
    assert r2.status_code == 400

    r3 = client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Carol", "description": "Напитки", "amount": "0.01"},
        follow_redirects=False,
    )
    assert r3.status_code == 303

    results = client.get(f"/e/{slug}/results")
    assert results.status_code == 200
    assert "Alice" in results.text
    assert "Carol" in results.text
    # Bob never successfully added an expense, so he shouldn't appear in totals
    assert "Bob" not in results.text


def test_unknown_slug_returns_404(client):
    response = client.get("/e/does-not-exist")
    assert response.status_code == 404

    response = client.get("/e/does-not-exist/results")
    assert response.status_code == 404


def test_single_person_no_transfers_needed(client):
    slug = create_event(client, name="Соло")
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Alice", "description": "Всё", "amount": "50"},
        follow_redirects=False,
    )
    results = client.get(f"/e/{slug}/results")
    assert "Все квиты" in results.text


def test_expense_without_description_is_accepted(client):
    slug = create_event(client, name="Без описания")
    response = client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Alice", "description": "", "amount": "15"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    event_page = client.get(f"/e/{slug}")
    assert "Alice" in event_page.text
    assert "—" in event_page.text


def test_event_page_shows_total(client):
    slug = create_event(client, name="Итоги")
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Alice", "description": "Еда", "amount": "40"},
        follow_redirects=False,
    )
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Bob", "description": "Вода", "amount": "10"},
        follow_redirects=False,
    )
    event_page = client.get(f"/e/{slug}")
    assert "Всего потрачено" in event_page.text
    assert "50.00" in event_page.text


def _get_expense_id(slug, payer_name):
    from app import crud
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        event = crud.get_event_by_slug(db, slug)
        expense = next(e for e in crud.get_expenses(db, event) if e.payer_name == payer_name)
        return expense.id
    finally:
        db.close()


def test_delete_expense_removes_it(client):
    slug = create_event(client, name="Удаление")
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Alice", "description": "Еда", "amount": "40"},
        follow_redirects=False,
    )

    expense_id = _get_expense_id(slug, "Alice")

    response = client.post(
        f"/e/{slug}/expenses/{expense_id}/delete", follow_redirects=False
    )
    assert response.status_code == 303

    event_page = client.get(f"/e/{slug}")
    assert "Alice" not in event_page.text
    assert "Пока никто ничего не добавил" in event_page.text


def test_delete_expense_from_other_event_is_ignored(client):
    slug_a = create_event(client, name="Событие А")
    slug_b = create_event(client, name="Событие Б")
    client.post(
        f"/e/{slug_a}/expenses",
        data={"payer_name": "Alice", "description": "Еда", "amount": "40"},
        follow_redirects=False,
    )

    expense_id = _get_expense_id(slug_a, "Alice")

    # trying to delete event A's expense through event B's URL must not remove it
    client.post(f"/e/{slug_b}/expenses/{expense_id}/delete", follow_redirects=False)

    event_page = client.get(f"/e/{slug_a}")
    assert "Alice" in event_page.text


def test_create_event_rate_limited_after_threshold(client):
    responses = [
        client.post("/events", data={"name": f"Событие {i}"}, follow_redirects=False)
        for i in range(11)
    ]
    assert responses[-1].status_code == 429
