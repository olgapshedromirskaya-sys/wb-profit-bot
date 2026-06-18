/* global Telegram */
(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = tg ? tg.initData : "";

  if (tg) {
    tg.ready();
    tg.expand();
    applyTheme();
    tg.onEvent("themeChanged", applyTheme);
  }

  function applyTheme() {
    const isDark = tg && tg.colorScheme === "dark";
    document.documentElement.classList.toggle("dark", !!isDark);
  }

  const content = document.getElementById("content");
  const sheet = document.getElementById("sheet");
  const overlay = document.getElementById("overlay");
  const settingsBtn = document.getElementById("settingsBtn");

  let lastData = null;

  // ---------- helpers ----------

  function money(n) {
    const v = Number(n) || 0;
    const sign = v > 0 ? "+" : "";
    return sign + new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(v) + " ₽";
  }

  function plainMoney(n) {
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(Number(n) || 0) + " ₽";
  }

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function marginColor(pct) {
    if (pct < 0) return "var(--loss)";
    if (pct < 15) return "var(--warn)";
    return "var(--profit)";
  }

  function ringSvg(pct, size = 56, stroke = 7) {
    const clamped = Math.max(0, Math.min(100, pct));
    const r = (size - stroke) / 2;
    const c = 2 * Math.PI * r;
    const offset = c * (1 - clamped / 100);
    const color = marginColor(pct);
    const mid = size / 2;
    return `<svg class="ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <circle class="ring__track" cx="${mid}" cy="${mid}" r="${r}" stroke-width="${stroke}" fill="none"/>
      <circle cx="${mid}" cy="${mid}" r="${r}" stroke-width="${stroke}" fill="none"
        stroke="${color}" stroke-linecap="round"
        stroke-dasharray="${c}" stroke-dashoffset="${offset}"
        transform="rotate(-90 ${mid} ${mid})"/>
    </svg>`;
  }

  function toast(msg) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    document.body.appendChild(el);
    requestAnimationFrame(() => el.classList.add("is-visible"));
    setTimeout(() => {
      el.classList.remove("is-visible");
      setTimeout(() => el.remove(), 250);
    }, 2600);
  }

  // ---------- API ----------

  async function apiCall(path, { method = "GET", body } = {}) {
    const headers = {};
    if (initData) headers["X-Telegram-Init-Data"] = initData;
    if (body) headers["Content-Type"] = "application/json";
    const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    if (!res.ok) {
      let detail = `Ошибка ${res.status}`;
      try {
        const data = await res.json();
        detail = data.detail || detail;
      } catch (_) {}
      const err = new Error(typeof detail === "string" ? detail : detail.message || "Ошибка доступа");
      err.status = res.status;
      err.detail = detail;
      throw err;
    }
    return res.status === 204 ? null : res.json();
  }

  // ---------- render: states ----------

  function renderLoading() {
    content.innerHTML = `
      <div class="skeleton skeleton--hero"></div>
      <div class="skeleton skeleton--row"></div>
      <div class="skeleton skeleton--row"></div>
      <div class="skeleton skeleton--row"></div>
    `;
  }

  function renderError(message) {
    content.innerHTML = `
      <section class="empty">
        <div class="empty__title">Не получилось загрузить данные</div>
        <p class="empty__text">${escapeHtml(message)}</p>
        <button class="btn btn--primary btn--block" data-action="reload">Попробовать снова</button>
      </section>
    `;
  }

  function renderSubscribeGate(detail) {
    const channelUrl = (detail && detail.channel_url) || "";
    const channelLabel = (detail && detail.channel) || "канал";
    content.innerHTML = `
      <section class="empty">
        <div class="empty__title">Доступ только для подписчиков</div>
        <p class="empty__text">
          Это приложение бесплатно для тех, кто подписан на ${escapeHtml(channelLabel)}.
          Подпишитесь — и сразу увидите свою реальную прибыль и диагностику карточек.
          Отписка автоматически закрывает доступ.
        </p>
        ${channelUrl ? `<button class="btn btn--primary btn--block" data-action="open-channel" data-url="${escapeHtml(channelUrl)}" style="margin-bottom:10px">Подписаться на канал</button>` : ""}
        <button class="btn btn--ghost btn--block" data-action="recheck-subscription">Я подписался, проверить</button>
      </section>
    `;
  }

  function renderConnectPrompt() {
    content.innerHTML = `
      <section class="empty">
        <div class="empty__title">Подключите кабинет Wildberries</div>
        <p class="empty__text">
          Личный кабинет WB → Настройки → Доступ к API → создайте токен с правами
          «Статистика» и «Аналитика» (только чтение) → вставьте его сюда.
          Токен не даёт доступа к управлению ценами, остатками или выводу денег.
        </p>
        <form id="tokenForm" class="token-form">
          <textarea name="token" placeholder="Вставьте токен API Wildberries" required></textarea>
          <button type="submit" class="btn btn--primary">Подключить</button>
        </form>
        <button class="btn btn--ghost" data-action="show-demo">Сначала посмотреть на примере</button>
      </section>
    `;
    document.getElementById("tokenForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const token = new FormData(e.target).get("token").trim();
      if (!token) return;
      try {
        await apiCall("/api/token", { method: "POST", body: { token } });
        toast("Кабинет подключён");
        loadDashboard();
      } catch (err) {
        toast(err.message);
      }
    });
  }

  function renderRow(s) {
    const profitClass = s.net_profit < 0 ? "is-loss" : "is-profit";
    const funnel = s.views != null ? `${s.views} → ${s.add_to_cart} → ${s.orders}` : "нет данных за период";
    return `
      <article class="row" data-nm="${s.nm_id}">
        <div class="row__main" data-action="toggle-row">
          ${ringSvg(s.margin_pct, 40, 5)}
          <div class="row__info">
            <div class="row__title">${escapeHtml(s.sa_name || "Без названия")}</div>
            <div class="row__nm">арт. ${escapeHtml(s.nm_id)} · ${s.quantity_sold} шт</div>
          </div>
          <div class="row__amount ${profitClass}">${money(s.net_profit)}</div>
        </div>
        ${s.diagnosis ? `<div class="row__diagnosis">${escapeHtml(s.diagnosis)}</div>` : ""}
        <div class="row__details">
          <dl>
            <div><dt>Выручка</dt><dd>${plainMoney(s.revenue)}</dd></div>
            <div><dt>Логистика + хранение + штрафы</dt><dd>${plainMoney(s.logistics_cost + s.storage_cost + s.penalties)}</dd></div>
            <div><dt>Себестоимость</dt><dd>${s.has_cost_price ? plainMoney(s.cost_price_total) : "не задана"}</dd></div>
            <div><dt>Реклама / ДРР</dt><dd>${plainMoney(s.ad_spend)} · ${s.drr_pct}%</dd></div>
            <div><dt>Воронка (показы → корзина → заказы)</dt><dd>${funnel}</dd></div>
          </dl>
          ${!s.has_cost_price ? `
            <form class="cost-form" data-action="save-cost" data-nm="${s.nm_id}">
              <input type="number" step="0.01" min="0" name="cost_price" placeholder="Себестоимость, ₽/шт" required>
              <button type="submit" class="btn btn--primary btn--small">Сохранить</button>
            </form>` : ""}
        </div>
      </article>
    `;
  }

  function renderDashboard(data) {
    lastData = data;
    const t = data.total;
    let banner = "";
    if (data.previewMode) {
      banner = `<div class="banner">Это пример на демо-данных — открой приложение из Telegram, чтобы увидеть свои реальные цифры.</div>`;
    } else if (data.demo) {
      banner = `<div class="banner">Сейчас показаны демо-данные. Подключи свой кабинет в настройках ⚙, чтобы увидеть реальную прибыль.</div>`;
    }

    content.innerHTML = `
      ${banner}
      <section class="hero">
        <div class="hero__ring">
          ${ringSvg(t.margin_pct, 84, 9)}
          <div class="hero__ring-label mono">${t.margin_pct.toFixed(1)}%</div>
        </div>
        <div class="hero__main">
          <div class="hero__eyebrow">Чистая прибыль · 30 дней</div>
          <div class="hero__amount ${t.net_profit < 0 ? "is-loss" : "is-profit"}">${money(t.net_profit)}</div>
          <div class="hero__sub">
            <span>выручка ${plainMoney(t.revenue)}</span>
            <span>реклама ${plainMoney(t.ad_spend)}</span>
            <span>ДРР ${t.drr_pct}%</span>
          </div>
        </div>
      </section>
      <section class="list">
        <div class="list__header"><span>Артикулы</span><span>${data.skus.length}</span></div>
        ${data.skus.map(renderRow).join("")}
      </section>
    `;
  }

  // ---------- settings sheet ----------

  function openSheet(html) {
    sheet.innerHTML = html;
    sheet.classList.remove("hidden");
    overlay.classList.remove("hidden");
    requestAnimationFrame(() => {
      sheet.classList.add("is-visible");
      overlay.classList.add("is-visible");
    });
  }

  function closeSheet() {
    sheet.classList.remove("is-visible");
    overlay.classList.remove("is-visible");
    setTimeout(() => {
      sheet.classList.add("hidden");
      overlay.classList.add("hidden");
    }, 200);
  }

  function openSettings() {
    const connected = lastData && lastData.connected && !lastData.previewMode;
    openSheet(`
      <div class="sheet__title">Настройки</div>
      <div class="sheet__row">
        <span>Кабинет WB</span>
        <span>${connected ? "подключён" : "не подключён"}</span>
      </div>
      ${connected ? `<button id="disconnectBtn" class="btn btn--danger btn--block" style="margin-top:14px">Отключить кабинет</button>` : `<p class="empty__text" style="margin-top:14px">Открой приложение и вставь токен, чтобы подключить кабинет.</p>`}
    `);
    if (connected) {
      document.getElementById("disconnectBtn").addEventListener("click", async () => {
        try {
          await apiCall("/api/token", { method: "DELETE" });
          closeSheet();
          toast("Кабинет отключён");
          loadDashboard();
        } catch (err) {
          toast(err.message);
        }
      });
    }
  }

  settingsBtn.addEventListener("click", openSettings);
  overlay.addEventListener("click", closeSheet);

  // ---------- event delegation on content ----------

  content.addEventListener("click", (e) => {
    if (e.target.closest("[data-action='reload']")) {
      loadDashboard();
      return;
    }
    if (e.target.closest("[data-action='show-demo']")) {
      apiCall("/api/demo").then((data) => {
        data.previewMode = false;
        renderDashboard(data);
      }).catch((err) => toast(err.message));
      return;
    }
    const openChannelBtn = e.target.closest("[data-action='open-channel']");
    if (openChannelBtn) {
      const url = openChannelBtn.dataset.url;
      if (tg && tg.openTelegramLink) tg.openTelegramLink(url);
      else window.open(url, "_blank");
      return;
    }
    if (e.target.closest("[data-action='recheck-subscription']")) {
      apiCall("/api/subscription/recheck", { method: "POST" })
        .then((res) => {
          if (res.subscribed) {
            toast("Подписка подтверждена");
            loadDashboard();
          } else {
            toast("Подписку пока не вижу — обычно Telegram обновляет статус за пару секунд");
          }
        })
        .catch((err) => toast(err.message));
      return;
    }
    const toggle = e.target.closest("[data-action='toggle-row']");
    if (toggle) {
      toggle.closest(".row").classList.toggle("is-open");
    }
  });

  content.addEventListener("submit", async (e) => {
    const form = e.target.closest("[data-action='save-cost']");
    if (!form) return;
    e.preventDefault();
    e.stopPropagation();
    const nmId = form.dataset.nm;
    const price = parseFloat(new FormData(form).get("cost_price"));
    if (Number.isNaN(price)) return;
    try {
      await apiCall("/api/cost", { method: "POST", body: { nm_id: nmId, cost_price: price } });
      toast("Себестоимость сохранена");
      loadDashboard();
    } catch (err) {
      toast(err.message);
    }
  });

  // ---------- bootstrap ----------

  async function loadDashboard() {
    renderLoading();
    try {
      let data;
      if (initData) {
        data = await apiCall("/api/dashboard");
      } else {
        // Открыто не из Telegram (например, для разработки в браузере) —
        // показываем демо-данные без авторизации.
        data = await apiCall("/api/demo");
        data.previewMode = true;
      }
      if (data.connected === false) {
        renderConnectPrompt();
      } else {
        renderDashboard(data);
      }
    } catch (err) {
      if (err.status === 403 && err.detail && err.detail.code === "subscription_required") {
        renderSubscribeGate(err.detail);
      } else {
        renderError(err.message);
      }
    }
  }

  loadDashboard();
})();
