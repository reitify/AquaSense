(() => {
  const storageKey = "aquasense-theme";
  const root = document.documentElement;
  const button = document.getElementById("theme-toggle");
  const label = button?.querySelector(".theme-label");
  const themeSelect = document.getElementById("settings-theme");
  const refreshSelects = document.querySelectorAll(
    "#settings-refresh, #dashboard-refresh-interval",
  );
  const refreshNowButton = document.getElementById("dashboard-refresh-now");
  const saveStatus = document.getElementById("settings-save-status");
  const navButton = document.getElementById("nav-menu-toggle");
  const navLinks = document.getElementById("primary-navigation");

  const readPreference = (key, fallback) => {
    try {
      return localStorage.getItem(key) || fallback;
    } catch {
      return fallback;
    }
  };

  const savePreference = (key, value) => {
    try {
      localStorage.setItem(key, value);
      if (saveStatus) saveStatus.textContent = "Preferences saved in this browser.";
    } catch {
      if (saveStatus) {
        saveStatus.textContent = "Could not save preferences. Check your browser storage settings.";
      }
    }
  };

  const savedTheme = readPreference(storageKey, "light");
  const refreshIntervals = new Set(["0", "15", "30", "60"]);
  const savedRefreshInterval = readPreference("aquasense-dashboard-refresh", "0");
  const refreshInterval = refreshIntervals.has(savedRefreshInterval) ? savedRefreshInterval : "0";

  const applyTheme = (theme) => {
    const isDark = theme === "dark";
    root.dataset.theme = isDark ? "dark" : "light";
    button?.setAttribute("aria-pressed", String(isDark));
    button?.setAttribute("aria-label", `Switch to ${isDark ? "light" : "dark"} theme`);
    if (label) label.textContent = isDark ? "Light mode" : "Dark mode";
    if (themeSelect) themeSelect.value = isDark ? "dark" : "light";
  };

  applyTheme(savedTheme);

  let refreshTimeoutId;

  const applyRefreshInterval = (interval) => {
    refreshSelects.forEach((select) => {
      select.value = interval;
    });
    window.clearTimeout(refreshTimeoutId);
    if (document.body.dataset.page === "main.index" && Number(interval) > 0) {
      refreshTimeoutId = window.setTimeout(
        () => window.location.reload(),
        Number(interval) * 1000,
      );
    }
  };

  const updateRefreshInterval = (interval) => {
    const nextInterval = refreshIntervals.has(interval) ? interval : "0";
    applyRefreshInterval(nextInterval);
    savePreference("aquasense-dashboard-refresh", nextInterval);
  };

  applyRefreshInterval(refreshInterval);

  themeSelect?.addEventListener("change", () => {
    const nextTheme = themeSelect.value === "dark" ? "dark" : "light";
    applyTheme(nextTheme);
    savePreference(storageKey, nextTheme);
  });

  refreshSelects.forEach((select) => {
    select.addEventListener("change", () => {
      updateRefreshInterval(select.value);
    });
  });

  refreshNowButton?.addEventListener("click", () => window.location.reload());

  window.addEventListener("storage", (event) => {
    if (event.key === "aquasense-dashboard-refresh") {
      const nextInterval = refreshIntervals.has(event.newValue) ? event.newValue : "0";
      applyRefreshInterval(nextInterval);
    }
  });

  button?.addEventListener("click", () => {
    const nextTheme = root.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
    savePreference(storageKey, nextTheme);
  });

  const closeNavigation = () => {
    navButton?.setAttribute("aria-expanded", "false");
    navLinks?.classList.remove("is-open");
  };

  navButton?.addEventListener("click", () => {
    const isExpanded = navButton.getAttribute("aria-expanded") === "true";
    navButton.setAttribute("aria-expanded", String(!isExpanded));
    navLinks?.classList.toggle("is-open", !isExpanded);
  });

  navLinks?.addEventListener("click", (event) => {
    if (event.target.closest("a")) closeNavigation();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && navLinks?.classList.contains("is-open")) {
      closeNavigation();
      navButton?.focus();
    }
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".nav-menu")) closeNavigation();
  });

  window.matchMedia("(min-width: 1161px)").addEventListener("change", closeNavigation);
})();