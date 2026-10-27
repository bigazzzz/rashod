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


def test_event_slug_is_hex_without_punctuation(client):
    slug = create_event(client, name="Hex slug")
    assert len(slug) == 18
    assert all(c in "0123456789abcdef" for c in slug)


def test_index_shows_version_and_releases(client):
    from app import __version__

    response = client.get("/")
    assert response.status_code == 200
    assert f"v{__version__}" in response.text
    assert "Обновления" in response.text
    assert "О приложении" in response.text
    assert 'class="btn-secondary" href="/about"' in response.text
    assert 'name="color-scheme" content="dark"' in response.text
    assert 'src="/og/site.jpg"' in response.text
    assert "/static/beach-night.svg" not in response.text
    assert 'id="share-link"' in response.text
    assert 'id="copy-btn"' in response.text
    assert 'id="qr-btn"' in response.text
    assert "/static/share.js" in response.text
    assert 'property="og:image" content="http://testserver/og/site.jpg"' in response.text
    assert 'name="twitter:card" content="summary_large_image"' in response.text
    site_og = client.get("/og/site.jpg")
    assert site_og.status_code == 200
    assert site_og.content[:3] == b"\xff\xd8\xff"
    css = client.get("/static/style.css")
    assert "color-scheme: dark" in css.text


def test_event_page_shows_amount_and_description_chips(client):
    slug = create_event(client, name="Плашки")
    response = client.get(f"/e/{slug}")
    assert response.status_code == 200
    assert 'data-chip-target="amount"' in response.text
    assert 'data-chip-value="000"' in response.text
    assert 'data-chip-value="2000"' in response.text
    assert 'data-chip-value="2500"' not in response.text
    assert 'data-chip-value="3000"' not in response.text
    assert 'data-chip-value="5000"' not in response.text
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

    css = client.get("/static/style.css")
    assert css.status_code == 200
    assert ".chips > button.chip" in css.text
    assert "background-image: none" in css.text
    assert "@media (hover: hover)" in css.text


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


def test_event_page_has_open_graph_preview(client):
    slug = create_event(client, name="Поход в горы")
    response = client.get(f"/e/{slug}")
    assert response.status_code == 200
    assert 'property="og:title" content="Поход в горы · Поровну"' in response.text
    assert "Открой ссылку, добавь траты в «Поход в горы»" in response.text
    assert f'property="og:url" content="http://testserver/e/{slug}"' in response.text
    assert f'property="og:image" content="http://testserver/og/{slug}.jpg"' in response.text
    assert 'property="og:image:type" content="image/jpeg"' in response.text
    assert 'property="og:image:width" content="1200"' in response.text
    assert 'name="twitter:card" content="summary_large_image"' in response.text


def test_event_og_image_is_compact_jpeg(client):
    slug = create_event(client, name="Ужин у костра")
    response = client.get(f"/og/{slug}.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.content[:3] == b"\xff\xd8\xff"
    assert 10_000 < len(response.content) < 300_000

    head = client.head(f"/og/{slug}.jpg")
    assert head.status_code == 200
    assert head.headers["content-type"].startswith("image/jpeg")

    for legacy_url in (f"/og/{slug}.png", f"/e/{slug}/og.png"):
        legacy = client.get(legacy_url)
        assert legacy.status_code == 200
        assert legacy.content[:3] == b"\xff\xd8\xff"


def test_robots_allows_event_pages(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Disallow: /e/" not in response.text
    assert "Allow: /" in response.text


def test_event_page_shows_expiry_date(client):
    from datetime import timedelta

    from app.cleanup import RETENTION_DAYS

    slug = create_event(client, name="Срок хранения")
    response = client.get(f"/e/{slug}")
    assert response.status_code == 200
    assert "Данные будут удалены после" in response.text
    assert 'class="hint expires-hint"' in response.text

    from app import crud
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        event = crud.get_event_by_slug(db, slug)
        expected = (event.created_at + timedelta(days=RETENTION_DAYS)).strftime("%d.%m.%Y")
    finally:
        db.close()
    assert expected in response.text


def test_event_page_has_qr_controls(client):
    slug = create_event(client, name="QR тест")
    response = client.get(f"/e/{slug}")
    assert response.status_code == 200
    assert 'id="qr-btn"' in response.text
    assert 'id="qr-panel"' in response.text
    assert 'id="qr-code"' in response.text
    assert 'aria-label="Показать QR-код"' in response.text
    assert 'class="btn-icon"' in response.text
    assert 'data-event-name="QR тест"' in response.text
    assert "/static/qrcode.min.js" in response.text
    assert client.get("/static/qrcode.min.js").status_code == 200


def test_event_page_has_expense_added_toast(client):
    slug = create_event(client, name="Toast")
    page = client.get(f"/e/{slug}")
    assert 'id="toast"' in page.text
    assert "Трата добавлена" in page.text
    assert "added=1" in page.text


def test_event_page_hero_matches_og_image_meta(client):
    """Hero on the event page must be the same asset as social OG preview."""
    import re
    from io import BytesIO

    from PIL import Image

    from app.og_image import save_generated_background

    slug = create_event(client, name="Hero OG")
    page = client.get(f"/e/{slug}")
    assert "/static/beach-night.svg" not in page.text
    assert f'src="/og/{slug}.jpg"' in page.text
    og = re.search(r'property="og:image" content="([^"]+)"', page.text)
    assert og is not None
    assert og.group(1).endswith(f"/og/{slug}.jpg")

    raw = BytesIO()
    Image.new("RGB", (1200, 630), (0, 200, 80)).save(raw, format="JPEG")
    save_generated_background(slug, raw.getvalue())
    page2 = client.get(f"/e/{slug}")
    assert re.search(rf'src="/og/{re.escape(slug)}\.jpg\?v=\d+"', page2.text)
    og2 = re.search(r'property="og:image" content="([^"]+)"', page2.text)
    assert og2 is not None
    assert f"/og/{slug}.jpg?v=" in og2.group(1)
    # Relative hero path is the absolute OG path without host
    hero = re.search(r'class="hero[^"]*"\s+src="([^"]+)"', page2.text)
    assert hero is not None
    assert og2.group(1).endswith(hero.group(1))

    results = client.get(f"/r/{slug}")
    assert hero.group(1) in results.text


def test_hero_compact_css_shows_full_og_frame():
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "style.css").read_text(
        encoding="utf-8"
    )
    assert "aspect-ratio: 1200 / 630" in css
    assert "height: 100px" not in css.split(".hero--compact")[1].split("}")[0]


def test_empty_name_and_amount_get_defaults(client):
    slug = create_event(client, name="Defaults")
    first = client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "", "description": "", "amount": ""},
        follow_redirects=False,
    )
    assert first.status_code == 303
    assert first.headers["location"] == f"/e/{slug}?added=1"

    second = client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "   ", "description": "чай", "amount": "  "},
        follow_redirects=False,
    )
    assert second.status_code == 303
    assert second.headers["location"].endswith("?added=1")

    page = client.get(f"/e/{slug}")
    assert "User001" in page.text
    assert "User002" in page.text
    results = client.get(f"/r/{slug}")
    assert results.text.count("участник") >= 2


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
    assert "участник без трат" in event_page.text
    assert "Внесённые траты" not in event_page.text
    assert 'class="btn-secondary"' in event_page.text
    assert ">Результаты<" in event_page.text
    assert 'class="btn-export"' in event_page.text
    assert ">Скачать файл<" in event_page.text

    results = client.get(f"/r/{slug}")
    assert results.status_code == 200
    assert "Внесённые траты" in results.text
    assert "Когда (UTC)" in results.text
    assert "участник" in results.text
    assert "Alice" in results.text
    assert "Bob" in results.text
    assert "Carol" in results.text
    # Bob paid 0, so he owes his share
    assert "Bob → Alice" in results.text
    csv_resp = client.get(f"/r/{slug}.csv")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert csv_resp.content.startswith(b"\xef\xbb\xbf")
    assert b"Alice" in csv_resp.content
    assert b"Bob" in csv_resp.content
    assert "filename*=UTF-8''" in csv_resp.headers["content-disposition"]
    assert "porovnu.su-" in csv_resp.headers["content-disposition"]
    body = csv_resp.content.decode("utf-8-sig")
    assert "Кто,Потрачено" in body
    assert body.index("Кто,Кому,Сумма") < body.index("Кто,Потрачено")
    assert body.index("Кто,Потрачено") < body.index("Кто,На что,Сумма,Когда")

    page = client.get(f"/r/{slug}")
    assert "Скачать файл" in page.text
    assert 'class="btn-export"' in page.text
    # settlement block comes before expense log
    assert page.text.index("Кто кому должен") < page.text.index("Кто сколько потратил")
    assert page.text.index("Кто сколько потратил") < page.text.index("Внесённые траты")


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

    response = client.get("/r/does-not-exist")
    assert response.status_code == 404


def test_single_person_no_transfers_needed(client):
    slug = create_event(client, name="Соло")
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Alice", "description": "Всё", "amount": "50"},
        follow_redirects=False,
    )
    results = client.get(f"/r/{slug}")
    assert "Все квиты" in results.text


def test_expense_without_description_is_accepted(client):
    slug = create_event(client, name="Без описания")
    response = client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Alice", "description": "", "amount": "15"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    results = client.get(f"/r/{slug}")
    assert "Alice" in results.text
    assert "—" in results.text


def test_results_page_shows_total(client):
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
    results = client.get(f"/r/{slug}")
    assert "Всего потрачено" in results.text
    assert "50.00" in results.text


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
    assert response.headers["location"] == f"/r/{slug}"

    results = client.get(f"/r/{slug}")
    assert "Alice" not in results.text
    assert "Пока никто ничего не добавил" in results.text


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

    results = client.get(f"/r/{slug_a}")
    assert "Alice" in results.text


def test_index_uses_event_wording(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Название события" in response.text
    assert "мероприятие" not in response.text.lower()


def test_create_event_rate_limited_after_threshold(client):
    responses = [
        client.post("/events", data={"name": f"Событие {i}"}, follow_redirects=False)
        for i in range(11)
    ]
    assert responses[-1].status_code == 429


def test_results_live_at_short_path_with_legacy_redirect(client):
    slug = create_event(client, name="Short results")
    page = client.get(f"/r/{slug}")
    assert page.status_code == 200
    assert "Результаты" in page.text
    assert 'id="copy-btn"' in page.text
    assert f'value="http://testserver/r/{slug}"' in page.text
    assert "/static/share.js" in page.text

    legacy = client.get(f"/e/{slug}/results", follow_redirects=False)
    assert legacy.status_code == 302
    assert legacy.headers["location"] == f"/r/{slug}"

    legacy_csv = client.get(f"/e/{slug}/results.csv", follow_redirects=False)
    assert legacy_csv.status_code == 302
    assert legacy_csv.headers["location"] == f"/r/{slug}.csv"


def test_zero_amount_ignores_description(client):
    slug = create_event(client, name="Zero desc")
    client.post(
        f"/e/{slug}/expenses",
        data={"payer_name": "Алиса", "description": "не должно сохраниться", "amount": "0"},
        follow_redirects=False,
    )
    results = client.get(f"/r/{slug}")
    assert "Алиса" in results.text
    assert "не должно сохраниться" not in results.text
    assert "участник" in results.text


def test_event_page_has_copy_button(client):
    slug = create_event(client, name="Copy")
    response = client.get(f"/e/{slug}")
    assert 'id="copy-btn"' in response.text
    assert 'aria-label="Копировать ссылку"' in response.text
    assert "/static/share.js" in response.text


def test_about_page_lists_all_releases_and_privacy(client):
    from app.versions import load_releases

    response = client.get("/about")
    assert response.status_code == 200
    assert "О приложении" in response.text
    assert "Аккаунтов" in response.text
    assert "удаляются автоматически" in response.text
    assert 'src="/og/site.jpg"' in response.text
    assert "/static/beach-night.svg" not in response.text
    releases = load_releases(limit=None)
    assert len(releases) >= 4
    for release in releases:
        assert f"v{release['version']}" in response.text

    index = client.get("/")
    assert 'href="/about"' in index.text
