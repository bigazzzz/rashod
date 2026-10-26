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


def test_index_shows_version_and_releases(client):
    from app import __version__

    response = client.get("/")
    assert response.status_code == 200
    assert f"v{__version__}" in response.text
    assert "Обновления" in response.text
    assert "Исправлен QR" in response.text


def test_event_page_shows_amount_and_description_chips(client):
    slug = create_event(client, name="Плашки")
    response = client.get(f"/e/{slug}")
    assert response.status_code == 200
    assert 'data-chip-target="amount"' in response.text
    assert 'data-chip-value="000"' in response.text
    assert 'data-chip-value="2000"' in response.text
    assert 'data-chip-value="2500"' not in response.text
    assert 'data-chip-value="5000"' in response.text
    assert 'data-chip-mode="append"' in response.text
    # 000 is the first amount chip
    amount_pos = response.text.find('data-chip-target="amount"')
    first_chip = response.text.find("data-chip-value=", amount_pos)
    assert response.text.startswith('data-chip-value="000"', first_chip)
    assert 'data-chip-target="description"' in response.text
    assert 'data-chip-value="продукты"' in response.text
    assert 'data-chip-value="концерт"' in response.text
    assert 'data-chip-value="прочее"' in response.text
    assert 'data-chip-target="payer_name"' not in response.text


def test_event_page_shows_frequent_description_chips(client):
    slug = create_event(client, name="Частые")
    for amount in ("10", "20"):
        client.post(
            f"/e/{slug}/expenses",
            data={"payer_name": "Алиса", "description": "сувениры", "amount": amount},
            follow_redirects=False,
        )
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Боб", "description": "разовое", "amount": "5"},
        follow_redirects=False,
    )
    # default category repeated should not be duplicated as frequent chip
    for amount in ("1", "2"):
        client.post(
            f"/e/{slug}/expenses",
            data={"payer_name": "Карл", "description": "продукты", "amount": amount},
            follow_redirects=False,
        )

    response = client.get(f"/e/{slug}")
    assert response.status_code == 200
    assert 'class="chip chip--frequent" data-chip-value="сувениры"' in response.text
    assert 'data-chip-value="разовое"' not in response.text
    assert response.text.count('data-chip-value="продукты"') == 1


def test_event_page_has_qr_controls(client):
    slug = create_event(client, name="QR тест")
    response = client.get(f"/e/{slug}")
    assert response.status_code == 200
    assert 'id="qr-btn"' in response.text
    assert 'id="qr-panel"' in response.text
    assert 'id="qr-code"' in response.text
    assert 'aria-label="Показать QR-код"' in response.text
    assert 'data-event-name="QR тест"' in response.text
    assert "/static/qrcode.min.js" in response.text
    assert client.get("/static/qrcode.min.js").status_code == 200


def test_empty_name_and_amount_get_defaults(client):
    slug = create_event(client, name="Defaults")
    first = client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "", "description": "", "amount": ""},
        follow_redirects=False,
    )
    assert first.status_code == 303

    second = client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "   ", "description": "чай", "amount": "  "},
        follow_redirects=False,
    )
    assert second.status_code == 303

    page = client.get(f"/e/{slug}")
    assert "User001" in page.text
    assert "User002" in page.text
    assert page.text.count("участник") >= 2


def test_auto_payer_name_continues_after_existing_user(client):
    slug = create_event(client, name="UserSeq")
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "User003", "description": "", "amount": "0"},
        follow_redirects=False,
    )
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "", "description": "", "amount": "0"},
        follow_redirects=False,
    )
    page = client.get(f"/e/{slug}")
    assert "User004" in page.text


def test_event_page_shows_known_name_chips(client):
    slug = create_event(client, name="Имена")
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Алиса", "description": "Еда", "amount": "100"},
        follow_redirects=False,
    )
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Алиса", "description": "Ещё", "amount": "50"},
        follow_redirects=False,
    )
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Боб", "description": "", "amount": "0"},
        follow_redirects=False,
    )

    response = client.get(f"/e/{slug}")
    assert response.status_code == 200
    assert 'data-chip-target="payer_name"' in response.text
    assert response.text.count('data-chip-value="Алиса"') == 1
    assert 'data-chip-value="Боб"' in response.text


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
        data={"payer_name": "Bob", "description": "", "amount": "0"},
        follow_redirects=False,
    )
    # zero amount registers a participant who paid nothing
    assert r2.status_code == 303

    r3 = client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Carol", "description": "Напитки", "amount": "0.01"},
        follow_redirects=False,
    )
    assert r3.status_code == 303

    event_page = client.get(f"/e/{slug}")
    assert event_page.status_code == 200
    assert "участник" in event_page.text
    assert "участник без трат" in event_page.text

    results = client.get(f"/e/{slug}/results")
    assert results.status_code == 200
    assert "Alice" in results.text
    assert "Bob" in results.text
    assert "Carol" in results.text
    # Bob paid 0, so he owes his share
    assert "Bob → Alice" in results.text


def test_negative_amount_rejected(client):
    slug = create_event(client, name="Минус")
    response = client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Alice", "description": "Ошибка", "amount": "-1"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "отрицательной" in response.text


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
