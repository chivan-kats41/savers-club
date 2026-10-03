// 1K Saver Club — shared front-end behaviour (vanilla JS, no build step).

document.addEventListener("DOMContentLoaded", () => {
  // 1. Icons (lucide, loaded via CDN in base.html)
  if (window.lucide) window.lucide.createIcons();

  // 2. Mobile sidebar drawer (role dashboards)
  const openBtn = document.getElementById("mobile-nav-open");
  const closeBtn = document.getElementById("mobile-nav-close");
  const drawer = document.getElementById("mobile-nav-drawer");
  const backdrop = document.getElementById("mobile-nav-backdrop");

  const openDrawer = () => {
    if (!drawer) return;
    drawer.classList.remove("-translate-x-full");
    backdrop?.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
  };
  const closeDrawer = () => {
    if (!drawer) return;
    drawer.classList.add("-translate-x-full");
    backdrop?.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
  };
  openBtn?.addEventListener("click", openDrawer);
  closeBtn?.addEventListener("click", closeDrawer);
  backdrop?.addEventListener("click", closeDrawer);

  // 3. Reveal-on-scroll animation for elements marked .reveal
  const revealTargets = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && revealTargets.length) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 }
    );
    revealTargets.forEach((el) => io.observe(el));
  } else {
    revealTargets.forEach((el) => el.classList.add("is-visible"));
  }

  // 4. In-page hash tabs (role hub pages: #basket, #deals, #claims, etc.)
  //    Mirrors the original SPA's `hash` nav links: clicking a nav item
  //    scrolls to the matching <section id="...">.
  document.querySelectorAll('a[href*="#"]').forEach((link) => {
    link.addEventListener("click", (e) => {
      const url = new URL(link.href);
      if (url.pathname !== window.location.pathname) return;
      const id = url.hash.replace("#", "");
      const target = document.getElementById(id);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        history.pushState(null, "", url.hash);
      }
    });
  });

  // 5. Notification bell / search — small affordance, no backend yet
  document.getElementById("notif-bell")?.addEventListener("click", () => {
    document.getElementById("notif-dot")?.classList.add("hidden");
  });

  // 6. Generic admin table search (data-table-search="tableId" input filters rows)
  document.querySelectorAll("[data-table-search]").forEach((input) => {
    const table = document.getElementById(input.getAttribute("data-table-search"));
    if (!table) return;
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      table.querySelectorAll("tbody tr").forEach((row) => {
        row.style.display = !q || row.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  });

  // 7. Generic modal toggling: [data-modal-open="id"] shows #id, [data-modal-close] hides nearest .modal-backdrop
  document.querySelectorAll("[data-modal-open]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById(btn.getAttribute("data-modal-open"))?.classList.remove("hidden");
    });
  });
  document.querySelectorAll("[data-modal-close]").forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.closest(".modal-backdrop")?.classList.add("hidden");
    });
  });
  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.classList.add("hidden");
    });
  });
});

// ---------- Chart.js helpers (replaces Recharts from the React build) ----------
// Call from a page's inline <script> once Chart.js + this file are loaded.

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function chartPalette() {
  return [
    "oklch(0.55 0.16 155)",
    "oklch(0.55 0.17 245)",
    "oklch(0.72 0.17 55)",
    "oklch(0.65 0.18 300)",
    "oklch(0.7 0.15 195)",
    "oklch(0.6 0.22 25)",
  ];
}

function makeLineChart(canvasId, labels, series) {
  const el = document.getElementById(canvasId);
  if (!el || !window.Chart) return;
  const palette = chartPalette();
  return new Chart(el, {
    type: "line",
    data: {
      labels,
      datasets: series.map((s, i) => ({
        label: s.label,
        data: s.data,
        borderColor: palette[i % palette.length],
        backgroundColor: palette[i % palette.length],
        tension: 0.35,
        fill: false,
        pointRadius: 2,
        borderWidth: 2,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 700, easing: "easeOutQuart" },
      plugins: { legend: { display: series.length > 1, labels: { boxWidth: 10, font: { size: 11 } } } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11 } } },
        y: { grid: { color: "rgba(0,0,0,0.06)" }, ticks: { font: { size: 11 } } },
      },
    },
  });
}

function makeBarChart(canvasId, labels, data, opts = {}) {
  const el = document.getElementById(canvasId);
  if (!el || !window.Chart) return;
  const palette = chartPalette();
  return new Chart(el, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: opts.label || "",
          data,
          backgroundColor: opts.multiColor ? labels.map((_, i) => palette[i % palette.length]) : palette[0],
          borderRadius: 6,
          maxBarThickness: 34,
        },
      ],
    },
    options: {
      indexAxis: opts.horizontal ? "y" : "x",
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 700, easing: "easeOutQuart" },
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: !opts.horizontal ? false : true }, ticks: { font: { size: 11 } } },
        y: { grid: { display: opts.horizontal ? false : true }, ticks: { font: { size: 11 } } },
      },
    },
  });
}

function makePieChart(canvasId, labels, data) {
  const el = document.getElementById(canvasId);
  if (!el || !window.Chart) return;
  const palette = chartPalette();
  return new Chart(el, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{ data, backgroundColor: labels.map((_, i) => palette[i % palette.length]), borderWidth: 2, borderColor: "#fff" }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 700, easing: "easeOutQuart" },
      cutout: "62%",
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 }, padding: 12 } } },
    },
  });
}

// ---- CSP-safe helpers (no inline event handlers anywhere) -------------------
document.addEventListener("change", function (ev) {
  var el = ev.target.closest("[data-autosubmit]");
  if (el && el.form) el.form.submit();
});

// Pages that should stay fresh (rider jobs, agent queue, notifications) set
// <body data-autorefresh="30">. We only reload when the tab is visible and the
// user isn't typing or has no open <details>, so nothing they entered is lost.
(function () {
  var secs = parseInt(document.body && document.body.getAttribute("data-autorefresh"), 10);
  if (!secs || secs < 10) return;
  setInterval(function () {
    if (document.hidden) return;
    var a = document.activeElement;
    if (a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) return;
    if (document.querySelector("details[open], .modal-backdrop:not(.hidden)")) return;
    window.location.reload();
  }, secs * 1000);
})();

// Payment forms: show the phone box for mobile money and the email box for card.
// Hidden inputs are disabled so they're neither validated nor sent.
(function () {
  function apply(form) {
    var sel = form.querySelector("[data-method-switch]");
    if (!sel) return;
    form.querySelectorAll("[data-show-for]").forEach(function (box) {
      var on = box.getAttribute("data-show-for") === sel.value;
      box.classList.toggle("hidden", !on);
      box.querySelectorAll("input").forEach(function (i) { i.disabled = !on; });
    });
    var hint = form.querySelector("[data-method-hint]");
    if (hint) hint.textContent = sel.value === "card"
      ? "You'll be taken to a secure page to enter your card details. We never see or store them."
      : "You'll get a prompt on your phone to approve the payment.";
  }
  document.addEventListener("change", function (ev) {
    var sel = ev.target.closest("[data-method-switch]");
    if (sel && sel.form) apply(sel.form);
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form").forEach(function (f) { if (f.querySelector("[data-method-switch]")) apply(f); });
  });
})();
