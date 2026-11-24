(() => {
  const root = document.getElementById("transfer-metro");
  if (!root) return;

  const list = root.querySelector(".metro-list");
  const map = root.querySelector(".metro-map");
  const track = root.querySelector(".metro-track");
  const lines = root.querySelector(".metro-lines");
  const fares = root.querySelector(".metro-fares");
  const stations = root.querySelector(".metro-stations");
  const select = root.querySelector("[data-person]");
  const switches = root.querySelectorAll("[data-view]");
  const payments = Array.from(list.children, item => ({
    from: item.dataset.from, to: item.dataset.to, cents: Number(item.dataset.kopecks), item,
  }));
  const money = new Intl.NumberFormat("ru-RU", {
    style: "currency", currency: "RUB", minimumFractionDigits: 0, maximumFractionDigits: 2,
  });
  const plural = new Intl.PluralRules("ru");
  const counts = {one: "перевод", few: "перевода", many: "переводов", other: "перевода"};
  const colors = ["#007f7a", "#c3512e", "#6850a3", "#37729c", "#9b4370", "#577424"];
  const rowHeight = 58;
  const height = payments.length * rowHeight;
  const people = new Map();
  let view = "map";

  // Settlement emits each person's transfers consecutively on their side of the map.
  function register(name, side, y) {
    if (!people.has(name)) people.set(name, {name, side, first: y, last: y});
    people.get(name).last = y;
  }

  payments.forEach((payment, i) => {
    payment.y = i * rowHeight + rowHeight / 2;
    register(payment.from, "from", payment.y);
    register(payment.to, "to", payment.y);
  });

  track.style.height = height + "px";
  lines.setAttribute("viewBox", "0 0 400 " + height);
  let colorIndex = 0;
  for (const person of people.values()) {
    person.y = (person.first + person.last) / 2;
    if (person.side === "from") person.color = colors[colorIndex++ % colors.length];
    const station = document.createElement("button");
    station.type = "button";
    station.className = "metro-station metro-" + person.side;
    station.style.top = person.y + "px";
    if (person.color) station.style.setProperty("--rail", person.color);
    station.title = person.name;
    const label = document.createElement("span");
    label.textContent = person.name;
    station.append(label);
    station.addEventListener("click", () => {
      select.value = select.value === person.name ? "" : person.name;
      update();
    });
    stations.append(station);
    person.station = station;
  }

  for (const payment of payments) {
    const from = people.get(payment.from);
    const to = people.get(payment.to);
    const y = payment.y;
    // Fixed-width bevels keep the middle lane clear for its price and arrow.
    const left = Math.sign(y - from.y) * Math.min(22, Math.abs(y - from.y) / 2);
    const right = Math.sign(to.y - y) * Math.min(22, Math.abs(to.y - y) / 2);
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", [
      `M 0 ${from.y} H 22 L ${22 + Math.abs(left)} ${from.y + left}`,
      `V ${y - left} l ${Math.abs(left)} ${left} H ${378 - 2 * Math.abs(right)}`,
      `l ${Math.abs(right)} ${right} V ${to.y - right} L 378 ${to.y} H 400`,
    ].join(" "));
    path.setAttribute("stroke", from.color);
    lines.append(path);
    payment.path = path;

    const fare = document.createElement("span");
    fare.className = "metro-fare";
    fare.style.top = y + "px";
    fare.style.setProperty("--rail", from.color);
    fare.textContent = money.format(payment.cents / 100);
    fares.append(fare);
    payment.fare = fare;
  }

  function update() {
    const name = select.value;
    const related = new Set();
    let total = 0;
    let count = 0;
    for (const payment of payments) {
      const active = !name || payment.from === name || payment.to === name;
      payment.path.classList.toggle("is-muted", !active);
      payment.fare.classList.toggle("is-muted", !active);
      payment.item.hidden = !active;
      if (active) {
        total += payment.cents;
        count++;
        related.add(payment.from);
        related.add(payment.to);
      }
    }
    for (const person of people.values()) {
      person.station.classList.toggle("is-muted", !related.has(person.name));
      person.station.setAttribute("aria-pressed", String(person.name === name));
    }
    const side = people.get(name)?.side;
    const label = side === "from" ? "Перевести" : "Получить";
    root.querySelector("[data-total-label]").textContent = name && side ? label + " · " + name : "Сумма переводов";
    root.querySelector("[data-total]").textContent = name && !count ? "Все квиты" : money.format(total / 100);
    root.querySelector(".metro-count").textContent = count + " " + counts[plural.select(count)];
    map.hidden = view !== "map" || !count;
    list.hidden = !count;
    for (const button of switches) button.setAttribute("aria-pressed", String(button.dataset.view === view));
  }

  select.addEventListener("change", update);
  for (const button of switches) button.addEventListener("click", () => {
    view = button.dataset.view;
    update();
  });
  update();
  root.querySelector(".metro-interactive").hidden = false;
})();
