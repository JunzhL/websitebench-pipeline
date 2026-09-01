document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-single-submit]").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector("button[type='submit']");
      if (button) {
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
      }
    });
  });

  document.querySelectorAll("form[data-retry-after]").forEach((form) => {
    let seconds = Number.parseInt(form.dataset.retryAfter || "0", 10);
    const button = form.querySelector("button[type='submit']");
    const label = form.querySelector("[data-cooldown-label]");
    if (!button || !label || seconds <= 0) return;
    button.disabled = true;
    const update = () => {
      label.textContent = seconds > 0 ? ` Try again in ${seconds}s.` : " You can try again.";
      button.disabled = seconds > 0;
      seconds -= 1;
      if (seconds >= 0) window.setTimeout(update, 1000);
    };
    update();
  });

  const editor = document.querySelector(".code-editor");
  if (editor) {
    editor.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      event.preventDefault();
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      editor.value = `${editor.value.slice(0, start)}    ${editor.value.slice(end)}`;
      editor.selectionStart = editor.selectionEnd = start + 4;
    });
  }
});
