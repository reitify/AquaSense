(() => {
  const storageKey = "aquasense-theme";
  const root = document.documentElement;
  const button = document.getElementById("theme-toggle");
  const label = button?.querySelector(".theme-label");
  const navButton = document.getElementById("nav-menu-toggle");
  const navLinks = document.getElementById("primary-navigation");

  let savedTheme = "light";
  try {
    savedTheme = localStorage.getItem(storageKey) || "light";
  } catch {
    savedTheme = "light";
  }

  const applyTheme = (theme) => {
    const isDark = theme === "dark";
    root.dataset.theme = isDark ? "dark" : "light";
    button?.setAttribute("aria-pressed", String(isDark));
    button?.setAttribute("aria-label", `Switch to ${isDark ? "light" : "dark"} theme`);
    if (label) label.textContent = isDark ? "Light mode" : "Dark mode";
  };

  applyTheme(savedTheme);

  button?.addEventListener("click", () => {
    const nextTheme = root.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
    try {
      localStorage.setItem(storageKey, nextTheme);
    } catch {
      // The theme still changes for this page when storage is unavailable.
    }
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