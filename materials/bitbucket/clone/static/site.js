(() => {
  "use strict";

  const forms = document.querySelectorAll("form[data-single-submit]");
  for (const form of forms) {
    form.addEventListener("submit", () => {
      const button = form.querySelector("button[type='submit']");
      if (!button || button.disabled) return;
      button.disabled = true;
      button.dataset.originalText = button.textContent;
      button.textContent = "Working...";
    });
  }

  const cooldown = document.querySelector("[data-retry-after]");
  if (cooldown) {
    let seconds = Number(cooldown.dataset.retryAfter || "0");
    const button = cooldown.querySelector("button[type='submit']");
    const label = cooldown.querySelector("[data-cooldown-label]");
    if (button && seconds > 0) {
      button.disabled = true;
      const update = () => {
        if (label) label.textContent = `Try again in ${seconds}s`;
        if (seconds <= 0) {
          button.disabled = false;
          if (label) label.textContent = "You can try again now.";
          return;
        }
        seconds -= 1;
        window.setTimeout(update, 1000);
      };
      update();
    }
  }

  const projectFilter = document.querySelector("[data-project-filter]");
  if (projectFilter) {
    projectFilter.addEventListener("input", () => {
      const query = projectFilter.value.trim().toLowerCase();
      for (const project of document.querySelectorAll("[data-project-card]")) {
        project.hidden = !project.textContent.toLowerCase().includes(query);
      }
      const visible = document.querySelectorAll("[data-project-card]:not([hidden])").length;
      const noResults = document.querySelector("[data-no-project-results]");
      if (noResults) noResults.hidden = visible !== 0;
    });
  }

  for (const button of document.querySelectorAll("[data-confirm]")) {
    button.addEventListener("click", (event) => {
      if (!window.confirm(button.dataset.confirm)) event.preventDefault();
    });
  }
})();
