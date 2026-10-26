(function () {
  const shareBtn = document.getElementById("share-btn");
  const shareLink = document.getElementById("share-link");
  const copyBtn = document.getElementById("copy-btn");
  const qrBtn = document.getElementById("qr-btn");
  const qrPanel = document.getElementById("qr-panel");
  const qrCodeEl = document.getElementById("qr-code");
  if (!shareBtn || !shareLink) {
    return;
  }

  let qrInstance = null;

  async function copyUrl() {
    const url = shareLink.value;
    let copied = false;
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(url);
        copied = true;
      }
    } catch (err) {
      copied = false;
    }
    if (!copied) {
      try {
        shareLink.select();
        copied = document.execCommand("copy");
      } catch (err) {
        copied = false;
      }
    }
    return copied;
  }

  function flashButton(btn, okText, failText) {
    const original = btn.getAttribute("data-label") || btn.textContent;
    btn.setAttribute("data-label", original);
    if (btn.querySelector(".copy-icon")) {
      btn.setAttribute("aria-label", okText === "Скопировано!" ? "Ссылка скопирована" : "Не удалось скопировать");
      btn.title = okText === "Скопировано!" ? "Скопировано!" : "Не удалось";
      setTimeout(function () {
        btn.setAttribute("aria-label", "Копировать ссылку");
        btn.title = "Копировать ссылку";
      }, 1500);
      return;
    }
    btn.textContent = okText;
    setTimeout(function () {
      btn.textContent = original;
    }, 1500);
  }

  shareBtn.addEventListener("click", async function () {
    const url = shareLink.value;
    const title = shareBtn.getAttribute("data-event-name") || "Поровну";

    if (navigator.share) {
      try {
        await navigator.share({ title: title, text: title, url: url });
        return;
      } catch (err) {
        if (err && err.name === "AbortError") {
          return;
        }
      }
    }

    const copied = await copyUrl();
    flashButton(shareBtn, copied ? "Скопировано!" : "Скопируйте вручную");
  });

  if (copyBtn) {
    copyBtn.addEventListener("click", async function () {
      const copied = await copyUrl();
      flashButton(copyBtn, copied ? "Скопировано!" : "Ошибка");
    });
  }

  if (!qrBtn || !qrPanel || !qrCodeEl) {
    return;
  }

  function closeQr() {
    qrPanel.hidden = true;
    qrBtn.setAttribute("aria-expanded", "false");
  }

  function openQr() {
    if (typeof QRCode === "undefined") {
      return;
    }
    if (!qrInstance) {
      qrCodeEl.innerHTML = "";
      qrInstance = new QRCode(qrCodeEl, {
        text: shareLink.value,
        width: 200,
        height: 200,
        colorDark: "#0a0816",
        colorLight: "#f8ecd9",
        correctLevel: QRCode.CorrectLevel.M,
      });
    }
    qrPanel.hidden = false;
    qrBtn.setAttribute("aria-expanded", "true");
  }

  qrBtn.addEventListener("click", function (event) {
    event.stopPropagation();
    if (qrPanel.hidden) {
      openQr();
    } else {
      closeQr();
    }
  });

  document.addEventListener("click", function (event) {
    if (qrPanel.hidden) {
      return;
    }
    if (qrPanel.contains(event.target) || qrBtn.contains(event.target)) {
      return;
    }
    closeQr();
  });
})();
