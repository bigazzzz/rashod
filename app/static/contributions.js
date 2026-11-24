(() => {
  const figure = document.getElementById("contribution-circles");
  if (!figure) return;

  const circles = figure.querySelectorAll("[data-contribution-circle]");
  for (const label of figure.querySelectorAll("[data-contribution-label]")) {
    const circle = circles[Number(label.dataset.contributionLabel)];
    label.addEventListener("pointerenter", () => circle.classList.add("is-hovered"));
    label.addEventListener("pointerleave", () => circle.classList.remove("is-hovered"));
    label.addEventListener("focus", () => circle.classList.add("is-focused"));
    label.addEventListener("blur", () => circle.classList.remove("is-focused"));
  }
})();
