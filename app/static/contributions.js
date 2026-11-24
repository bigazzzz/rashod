(() => {
  const figure = document.getElementById("contribution-circles");
  if (!figure) return;

  const circles = figure.querySelectorAll("[data-contribution-circle]");
  for (const row of figure.querySelectorAll("[data-contribution-row]")) {
    const circle = circles[Number(row.dataset.contributionRow)];
    function setHovered(hovered) {
      row.classList.toggle("is-hovered", hovered);
      circle.classList.toggle("is-hovered", hovered);
    }
    for (const target of [row, circle]) {
      target.addEventListener("pointerenter", () => setHovered(true));
      target.addEventListener("pointerleave", () => setHovered(false));
    }
    row.addEventListener("focus", () => circle.classList.add("is-focused"));
    row.addEventListener("blur", () => circle.classList.remove("is-focused"));
  }
})();
