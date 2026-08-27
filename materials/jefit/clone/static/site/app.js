/* JEFIT offline clone runtime.
 *
 * Clone-local interaction layer over the frozen captured DOM: consent
 * banner, theme, header nav overlays, discovery filters, the signup
 * questionnaire stepper, and the member area's real local business actions
 * (plans, logging, settings, community, checkout navigation). Every request
 * stays on this origin; no external library is loaded.
 */
(function () {
  "use strict";

  var CONSENT_KEY = "jefit-clone-consent";
  var THEME_KEY = "jefit-clone-theme";

  function $(selector, root) {
    return (root || document).querySelector(selector);
  }
  function $all(selector, root) {
    return Array.prototype.slice.call(
      (root || document).querySelectorAll(selector)
    );
  }
  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body || {}),
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok, status: response.status, data: data };
      });
    });
  }
  function textOf(el) {
    return (el.textContent || "").replace(/\s+/g, " ").trim();
  }

  /* ---------------- honest clone-local notice ---------------- */

  function notice(message) {
    var existing = $("[data-clone-notice]");
    if (existing) existing.remove();
    var wrap = document.createElement("div");
    wrap.setAttribute("data-clone-notice", "");
    wrap.setAttribute(
      "style",
      "position:fixed;inset:0;z-index:9999;background:rgba(15,23,42,.55);" +
        "display:flex;align-items:center;justify-content:center;"
    );
    var card = document.createElement("div");
    card.setAttribute(
      "style",
      "background:#fff;color:#18202a;max-width:26rem;margin:1rem;" +
        "border-radius:12px;padding:1.5rem;font:14px/1.5 -apple-system," +
        "'Segoe UI',sans-serif;box-shadow:0 24px 48px rgba(0,0,0,.25)"
    );
    var text = document.createElement("p");
    text.style.margin = "0 0 1rem";
    text.textContent = message;
    var button = document.createElement("button");
    button.textContent = "OK";
    button.setAttribute(
      "style",
      "background:#1c5fc9;color:#fff;border:0;border-radius:6px;" +
        "padding:.5rem 1.25rem;cursor:pointer"
    );
    button.addEventListener("click", function () {
      wrap.remove();
    });
    card.appendChild(text);
    card.appendChild(button);
    wrap.appendChild(card);
    document.body.appendChild(wrap);
  }
  var EXTERNAL_NOTICE =
    "This offline clone does not connect to external services. " +
    "No remote request was made.";

  /* ---------------- consent banner ---------------- */

  function initConsent() {
    var banner = $('[aria-label="Cookie consent"]');
    if (!banner) return;
    var accepted = null;
    try {
      accepted = window.localStorage.getItem(CONSENT_KEY);
    } catch (err) {
      accepted = null;
    }
    if (accepted) {
      banner.style.display = "none";
      banner.setAttribute("inert", "");
      return;
    }
    // The capture froze this banner already dismissed (consent accepted once
    // per capture context), so the document ships it translated off-screen.
    // Until this clone's own consent is recorded, slide it into view exactly
    // as the source does on a first visit.
    banner.classList.remove("translate-y-full");
    banner.style.display = "";
    banner.removeAttribute("inert");
    banner.style.visibility = "visible";
    banner.style.opacity = "1";
    banner.style.transform = "none";
    banner.style.translate = "0 0";
    banner.addEventListener("click", function (event) {
      var button = event.target.closest("button");
      if (!button) return;
      var label = textOf(button);
      if (label === "Accept" || label === "Customize Settings") {
        try {
          window.localStorage.setItem(
            CONSENT_KEY,
            label === "Accept" ? "accepted" : "customized"
          );
        } catch (err) {
          /* storage unavailable: hide for this page only */
        }
        banner.style.display = "none";
        banner.setAttribute("inert", "");
      }
    });
  }

  /* ---------------- theme (light/dark) ---------------- */

  function applyTheme(theme) {
    var root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(theme);
    root.style.colorScheme = theme;
    try {
      window.localStorage.setItem(THEME_KEY, theme);
    } catch (err) {
      /* ignore */
    }
  }
  function initTheme() {
    var stored = null;
    try {
      stored = window.localStorage.getItem(THEME_KEY);
    } catch (err) {
      stored = null;
    }
    if (stored === "dark" || stored === "light") applyTheme(stored);
  }

  /* ---------------- header nav overlays ---------------- */

  var NAV_KEYS = { Products: "products", Workouts: "workouts", More: "more" };

  function overlayTemplate(key) {
    return $('template[data-nav-overlay="' + key + '"]');
  }

  function closeNavPanels() {
    $all("[data-clone-nav-panel]").forEach(function (el) {
      el.remove();
    });
  }

  function initNav() {
    document.addEventListener("click", function (event) {
      var button = event.target.closest("button");
      if (!button) {
        if (!event.target.closest("[data-clone-nav-panel]")) closeNavPanels();
        return;
      }
      var label = textOf(button);
      if (NAV_KEYS[label] && button.closest("header, nav")) {
        var template = overlayTemplate(NAV_KEYS[label]);
        if (!template) return;
        var open = button.parentElement.querySelector(
          "[data-clone-nav-panel]"
        );
        closeNavPanels();
        if (open) return;
        var holder = document.createElement("div");
        holder.setAttribute("data-clone-nav-panel", NAV_KEYS[label]);
        holder.innerHTML = template.innerHTML;
        var parent = button.parentElement;
        if (getComputedStyle(parent).position === "static") {
          parent.style.position = "relative";
        }
        parent.appendChild(holder);
        event.preventDefault();
        return;
      }
      if (label === "Open main menu") {
        var mobileTemplate = overlayTemplate("mobile-menu");
        if (!mobileTemplate) return;
        closeNavPanels();
        var menu = document.createElement("div");
        menu.setAttribute("data-clone-nav-panel", "mobile-menu");
        menu.innerHTML = mobileTemplate.innerHTML;
        document.body.appendChild(menu);
        menu.addEventListener("click", function (inner) {
          var closer = inner.target.closest("button");
          if (closer && /close/i.test(closer.getAttribute("aria-label") || "")) {
            menu.remove();
          }
        });
        event.preventDefault();
      }
    });
  }

  /* ---------------- theme + external-service affordances ---------------- */

  var EXTERNAL_LABELS = [
    "Continue with Google",
    "Continue with Apple",
    "Continue with Facebook",
    "Sign in with Google",
    "Sign in with Apple",
    "Manage",
  ];

  function initExternalBoundaries() {
    document.addEventListener("click", function (event) {
      var control = event.target.closest("button, a");
      if (!control) return;
      var label = textOf(control);
      var ariaLabel = control.getAttribute("aria-label") || "";
      if (
        label === "Light mode" ||
        label === "Dark mode" ||
        ariaLabel === "Toggle dark mode"
      ) {
        applyTheme(
          document.documentElement.classList.contains("dark")
            ? "light"
            : "dark"
        );
        event.preventDefault();
        return;
      }
      if (
        EXTERNAL_LABELS.indexOf(label) >= 0 ||
        (control.getAttribute("aria-label") || "").indexOf("Continue with") === 0
      ) {
        // IdP buttons / Strava manage: visual parity only, honest notice.
        if (label === "Manage" && !control.closest("[data-settings-panel='integrations']")) {
          return;
        }
        event.preventDefault();
        notice(EXTERNAL_NOTICE);
      }
    });
  }

  /* ---------------- exercises: client-side filters + search ------------- */

  function catalogData() {
    var holder = $("#jefit-catalog");
    if (!holder) return null;
    try {
      return JSON.parse(holder.textContent);
    } catch (err) {
      return null;
    }
  }

  function initExerciseFilters() {
    var data = catalogData();
    if (!data) return;
    var grid = $(".grid.grid-cols-1");
    if (!grid) return;
    var cards = $all("a[href^='/exercises/'], a[href^='/my-jefit/exercises/']", grid).filter(
      function (a) {
        return /\/exercises\/\d+\//.test(a.getAttribute("href"));
      }
    );
    if (!cards.length) return;
    var cardTemplate = cards[0].cloneNode(true);
    var active = { muscle: null, equipment: null, search: "" };
    var muscles = data.muscles;
    var equipment = data.equipment;

    function matches(entry) {
      if (active.muscle && entry.muscle !== active.muscle) return false;
      if (active.equipment && entry.equipment !== active.equipment) {
        return false;
      }
      if (active.search) {
        var needle = active.search.toLowerCase();
        if (entry.name.toLowerCase().indexOf(needle) < 0) return false;
      }
      return true;
    }

    function renderCard(entry) {
      var node = cardTemplate.cloneNode(true);
      node.setAttribute(
        "href",
        (location.pathname.indexOf("/my-jefit/") === 0
          ? "/my-jefit/exercises/"
          : "/exercises/") + entry.id + "/" + entry.slug
      );
      var img = node.querySelector("img");
      if (img) {
        img.setAttribute("alt", entry.name + " Demonstration");
        img.setAttribute("srcset", entry.srcset);
        img.setAttribute("src", entry.src);
      }
      var name = node.querySelector("p");
      if (name) name.textContent = entry.name;
      var pills = $all("span.underline, span[class*='jefit-blue']", node);
      if (pills.length >= 2) {
        pills[0].textContent = entry.muscle;
        pills[1].textContent = entry.equipment;
      }
      var description = node.querySelector("p[class*='line-clamp-4']");
      if (description) description.textContent = entry.description;
      return node;
    }

    var countEl = null;
    $all("p").some(function (p) {
      if (/EXERCISES FOUND/.test(p.textContent)) {
        countEl = p.querySelector("span") || p;
        return true;
      }
      return false;
    });

    function applyFilters() {
      var anyFilter = active.muscle || active.equipment || active.search;
      var visible = anyFilter ? data.exercises.filter(matches) : null;
      var list = visible === null
        ? data.exercises.slice(0, data.page_size)
        : visible;
      grid.innerHTML = "";
      list.forEach(function (entry) {
        grid.appendChild(renderCard(entry));
      });
      if (countEl) {
        var total = visible === null ? data.exercises.length : visible.length;
        countEl.textContent = String(total);
        countEl.appendChild(document.createTextNode(" "));
      }
    }

    document.addEventListener("click", function (event) {
      var button = event.target.closest("button");
      if (!button) return;
      var label = textOf(button);
      if (muscles.indexOf(label) >= 0) {
        active.muscle = active.muscle === label ? null : label;
        applyFilters();
      } else if (equipment.indexOf(label) >= 0) {
        active.equipment = active.equipment === label ? null : label;
        applyFilters();
      } else if (/^CLEAR/.test(label)) {
        active.muscle = null;
        active.equipment = null;
        active.search = "";
        var search = $("input[placeholder*='Search']");
        if (search) search.value = "";
        applyFilters();
      } else if (label === "FILTERS") {
        var modal = $('[data-clone-modal="filters"]');
        if (modal) modal.style.display = "";
      }
    });
    document.addEventListener("input", function (event) {
      var input = event.target;
      if (
        input.tagName === "INPUT" &&
        /search/i.test(input.getAttribute("placeholder") || "")
      ) {
        active.search = input.value.trim();
        applyFilters();
      }
    });
    document.addEventListener("submit", function (event) {
      var form = event.target;
      if (form.querySelector("input[placeholder*='Search']")) {
        event.preventDefault();
        applyFilters();
      }
    });
  }

  /* ---------------- signup questionnaire stepper ---------------- */

  function initSignup() {
    if (location.pathname !== "/signup") return;
    var holder = $("#jefit-signup-steps");
    if (!holder) return;
    var panels;
    try {
      panels = JSON.parse(holder.textContent);
    } catch (err) {
      return;
    }
    var step = 1;
    var match = /[?&]step=(\d+)/.exec(location.search);
    if (match) step = Math.min(17, Math.max(1, parseInt(match[1], 10)));
    var answers = {};
    try {
      answers = JSON.parse(
        window.sessionStorage.getItem("jefit-clone-signup") || "{}"
      );
    } catch (err) {
      answers = {};
    }

    function slotBounds() {
      var walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_COMMENT
      );
      var start = null;
      var end = null;
      var node;
      while ((node = walker.nextNode())) {
        if (node.nodeValue === "jefit-signup-slot") start = node;
        if (node.nodeValue === "/jefit-signup-slot") end = node;
      }
      return start && end ? [start, end] : null;
    }

    function renderStep(next) {
      var bounds = slotBounds();
      if (!bounds) return;
      step = Math.min(17, Math.max(1, next));
      var range = document.createRange();
      range.setStartAfter(bounds[0]);
      range.setEndBefore(bounds[1]);
      range.deleteContents();
      var template = document.createElement("template");
      template.innerHTML = panels[String(step)];
      range.insertNode(template.content);
      window.scrollTo(0, 0);
      if (hasAnswer()) enableContinue();
      // Step 17 is the "Analyzing your answers" panel: it carries no control
      // and the source hands off to /signup/results on its own once the
      // animation completes. The captured evidence shows both states but not
      // the duration, so the delay is a disclosed clone-local choice.
      if (step >= 17) {
        window.setTimeout(function () {
          if (location.pathname === "/signup") {
            location.assign("/signup/results");
          }
        }, 2500);
      }
    }

    function persist() {
      try {
        window.sessionStorage.setItem(
          "jefit-clone-signup",
          JSON.stringify(answers)
        );
      } catch (err) {
        /* ignore */
      }
    }

    // Source behaviour (capture evidence signup-step-01..16): single-choice
    // steps carry no Continue button and advance the moment an option is
    // picked; multi-choice steps (e.g. "What are your target zones?") and
    // numeric steps keep Continue. Some steps render options as bare
    // cursor-pointer chips with no ARIA role, so they must be clickable too.
    function continueButton() {
      var found = null;
      $all("button").forEach(function (item) {
        if (
          !found &&
          item.offsetParent !== null &&
          /^(continue|next)$/i.test(textOf(item))
        ) {
          found = item;
        }
      });
      return found;
    }

    function stepHasContinue() {
      return continueButton() !== null;
    }

    // Steps whose Continue is gated on an answer were captured in their
    // EMPTY state, so the frozen button ships `pointer-events-none` and no
    // captured frame shows its enabled styling. Enabling it once an answer
    // exists is the source behaviour; the enabled fill is the primary-button
    // colour measured on the observed /login submit (disclosed inference,
    // same as the /signup/register Continue).
    function enableContinue() {
      var button = continueButton();
      if (!button) return;
      button.classList.remove("pointer-events-none");
      button.removeAttribute("disabled");
      button.style.backgroundColor = "rgb(49, 121, 255)";
      button.style.color = "rgb(255, 255, 255)";
      button.style.cursor = "pointer";
    }

    function hasAnswer() {
      if (answers["step-" + step]) return true;
      var answered = false;
      $all("input").forEach(function (field) {
        if (field.offsetParent !== null && String(field.value).trim() !== "") {
          answered = true;
        }
      });
      $all("[aria-checked='true'], [data-checked], [data-selected]").forEach(
        function (node) {
          if (node.offsetParent !== null) answered = true;
        }
      );
      return answered;
    }

    // Any answering gesture ungates Continue: numeric steps (height/weight/
    // age) answer by typing, chip steps by selecting. Re-synced on every
    // interaction so no panel can end up rendered-but-unusable.
    document.addEventListener("input", function () {
      if (hasAnswer()) enableContinue();
    });
    document.addEventListener("click", function () {
      window.setTimeout(function () {
        if (hasAnswer()) enableContinue();
      }, 0);
    });
    document.addEventListener("change", function () {
      if (hasAnswer()) enableContinue();
    });

    function optionChip(target) {
      var chip = target.closest("div.cursor-pointer");
      if (!chip || chip.querySelector("div.cursor-pointer")) return null;
      var text = textOf(chip);
      return text && text.length < 60 ? chip : null;
    }

    document.addEventListener("click", function (event) {
      var control = event.target.closest(
        "button, [role='radio'], [role='checkbox'], [role='option'], a"
      );
      var chip = control ? null : optionChip(event.target);
      if (!control && !chip) return;
      var label = textOf(control || chip);
      var radio = event.target.closest(
        "[role='radio'], [role='checkbox'], [role='option']"
      );
      var group = event.target.closest("[role='radiogroup'], [role='group']");
      if ((radio && group) || chip) {
        var multi =
          (radio && radio.getAttribute("role") === "checkbox") ||
          (chip && stepHasContinue());
        var node = radio || chip;
        if (!multi) {
          var siblings = group
            ? $all("[role='radio'], [role='option']", group)
            : $all("div.cursor-pointer");
          siblings.forEach(function (item) {
            item.setAttribute("aria-checked", "false");
            item.style.outline = "";
          });
          node.setAttribute("aria-checked", "true");
          node.style.outline = "2px solid #1c5fc9";
        } else {
          var checked = node.getAttribute("aria-checked") === "true";
          node.setAttribute("aria-checked", checked ? "false" : "true");
          node.style.outline = checked ? "" : "2px solid #1c5fc9";
        }
        answers["step-" + step] = label;
        persist();
        enableContinue();
        // Single-choice steps advance immediately, as on the source.
        if (!multi && !stepHasContinue()) {
          if (step >= 17) location.assign("/signup/results");
          else renderStep(step + 1);
        }
        return;
      }
      if (label === "Continue" || label === "Next") {
        event.preventDefault();
        answers["step-" + step] = answers["step-" + step] || null;
        persist();
        if (step >= 17) {
          location.assign("/signup/results");
        } else {
          renderStep(step + 1);
        }
        return;
      }
      if (
        control.tagName === "BUTTON" &&
        (control.getAttribute("aria-label") === "back" ||
          label === "Back" ||
          control.querySelector("path[d^='M10.5 19.5']"))
      ) {
        if (step > 1) {
          event.preventDefault();
          renderStep(step - 1);
        }
      }
    });
    if (step !== 1) renderStep(step);
  }

  function initSignupResults() {
    if (location.pathname !== "/signup/results") return;
    document.addEventListener("click", function (event) {
      var button = event.target.closest("button, a");
      if (!button) return;
      if (textOf(button) === "Continue") {
        event.preventDefault();
        location.assign("/signup/register");
      }
    });
  }

  function initRegister() {
    if (location.pathname !== "/signup/register") return;
    var form = $("form[action='/signup/register']");
    if (!form) return;
    // The captured source froze this step with an empty field, so its Continue
    // button is serialized in the disabled state (pointer-events-none). Source
    // enables it once the address validates; mirror that here. The enabled fill
    // is the primary-button colour measured on the observed /login submit
    // (rgb(49,121,255) on white text) — the source's own enabled state for
    // THIS button was never captured, so the colour is borrowed from the same
    // design system rather than invented.
    var emailField = form.querySelector("input[name='email']");
    var submitButton = form.querySelector("button");
    if (emailField && submitButton) {
      var syncSubmitState = function () {
        var ready = emailField.checkValidity() && emailField.value.trim() !== "";
        submitButton.classList.toggle("pointer-events-none", !ready);
        if (ready) {
          submitButton.style.backgroundColor = "rgb(49, 121, 255)";
          submitButton.style.color = "rgb(255, 255, 255)";
          submitButton.style.cursor = "pointer";
        } else {
          submitButton.style.backgroundColor = "";
          submitButton.style.color = "";
          submitButton.style.cursor = "";
        }
      };
      emailField.addEventListener("input", syncSubmitState);
      emailField.addEventListener("change", syncSubmitState);
      syncSubmitState();
    }
    form.addEventListener("submit", function () {
      if (!form.querySelector("input[name='questionnaire']")) {
        var hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "questionnaire";
        try {
          hidden.value =
            window.sessionStorage.getItem("jefit-clone-signup") || "{}";
        } catch (err) {
          hidden.value = "{}";
        }
        form.appendChild(hidden);
      }
    });
  }

  /* ---------------- login redirect preservation ---------------- */

  function initLogin() {
    if (location.pathname !== "/login") return;
    var form = $("form[action='/login']");
    if (!form) return;
    var match = /[?&]redirect=([^&]+)/.exec(location.search);
    if (match && !form.querySelector("input[name='redirect']")) {
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "redirect";
      hidden.value = decodeURIComponent(match[1]);
      form.appendChild(hidden);
    }
  }

  /* ---------------- anonymous routine builder ---------------- */

  function initBuildRoutine() {
    if (location.pathname !== "/build-routine") return;
    var code = (/[?&]code=([A-Za-z0-9_-]+)/.exec(location.search) || [])[1];
    document.addEventListener("click", function (event) {
      var button = event.target.closest("button, a");
      if (!button || textOf(button) !== "Save") return;
      event.preventDefault();
      var name = "";
      var input = $("input[type='text']");
      if (input) name = input.value.trim();
      postJSON("/api/build-routine/save", { code: code || "", name: name })
        .then(function (result) {
          if (result.ok && result.data.redirect) {
            location.assign(result.data.redirect);
          }
        });
    });
  }

  /* ---------------- captured swiper carousels ---------------- */

  function initSwipers() {
    // The captured DOM freezes each swiper track at a pixel offset measured
    // at capture-time slide width. Recompute the offset from the marked
    // active slide and the REAL rendered slide width so the active slide
    // (text + image together) is exactly what shows.
    $all(".swiper-wrapper").forEach(function (wrapper) {
      var slides = $all(":scope > .swiper-slide", wrapper);
      if (!slides.length) return;
      var active = slides.findIndex(function (slide) {
        return slide.classList.contains("swiper-slide-active");
      });
      if (active < 0) active = 0;
      function apply() {
        var width = slides[0].getBoundingClientRect().width;
        if (!width) return;
        wrapper.style.transitionDuration = "0ms";
        wrapper.style.transform =
          "translate3d(-" + Math.round(active * width) + "px, 0px, 0px)";
      }
      apply();
      window.addEventListener("resize", apply);
      // lazy image loads can settle layout after first paint
      window.setTimeout(apply, 250);
    });
  }

  /* ---------------- captured first-run modal ---------------- */

  function initCapturedModal() {
    // The builder captures ship the source's own first-run modal (portal
    // root) open, exactly as the walk saw it. Its close control ("X") and
    // its CTA both dismiss it, as on source.
    var portal = document.getElementById("headlessui-portal-root");
    if (!portal || portal.hasAttribute("data-clone-modal")) return;
    portal.addEventListener("click", function (event) {
      var control = event.target.closest("button, a");
      if (!control) return;
      var label = textOf(control);
      if (label === "X" || label === "Try it out now!" || label === "Close") {
        event.preventDefault();
        portal.remove();
        // the captured document also carries the modal's scroll lock and the
        // inert page container; releasing both is what dismissal does
        document.documentElement.style.overflow = "";
        document.documentElement.style.paddingRight = "";
        $all("[inert]").forEach(function (el) {
          if (!el.closest("[aria-label='Cookie consent']")) {
            el.removeAttribute("inert");
          }
        });
      }
    });
  }

  /* ---------------- member: overlays (menus / modals) ---------------- */

  function toggleOverlay(key) {
    var overlay = $('[data-clone-overlay="' + key + '"]');
    if (!overlay) return false;
    overlay.style.display = overlay.style.display === "none" ? "" : "none";
    return true;
  }

  function initMemberOverlays() {
    document.addEventListener("click", function (event) {
      var control = event.target.closest("button, a");
      if (!control) return;
      var label = textOf(control);
      if (label === "Get App" || label.indexOf("Get App") === 0) {
        if (toggleOverlay("getapp-menu")) event.preventDefault();
        return;
      }
      if (label === "Sync Info") {
        if (toggleOverlay("sync-info")) event.preventDefault();
        return;
      }
      if (/^Create Post/.test(label) || /^Ask a Question/.test(label)) {
        if (toggleOverlay("create-post")) event.preventDefault();
        return;
      }
      // The dashboard card's button wraps the label plus its supporting copy,
      // so match the phrase rather than the whole text. Settings' upgrade
      // cards are anchors to /elite/checkout and must keep navigating.
      if (
        control.tagName === "BUTTON" &&
        /upgrade to elite/i.test(label)
      ) {
        if (toggleOverlay("elite-plan")) event.preventDefault();
        return;
      }
      var accountButton = control.closest("button");
      if (
        accountButton &&
        accountButton.querySelector("span[data-slot='avatar']")
      ) {
        if (toggleOverlay("account-menu")) event.preventDefault();
        return;
      }
      if (label === "Sign out") {
        event.preventDefault();
        var form = document.createElement("form");
        form.method = "post";
        form.action = "/logout";
        document.body.appendChild(form);
        form.submit();
        return;
      }
      // close boxes inside overlays
      var overlayRoot = control.closest("[data-clone-overlay]");
      if (
        overlayRoot &&
        (label === "Close" ||
          /close/i.test(control.getAttribute("aria-label") || "") ||
          label === "Cancel" ||
          label === "Got it")
      ) {
        overlayRoot.style.display = "none";
        event.preventDefault();
      }
    });
  }

  /* ---------------- member: workouts list ---------------- */

  function initWorkouts() {
    if (location.pathname !== "/my-jefit/workouts") return;
    document.addEventListener("click", function (event) {
      var control = event.target.closest("button, a");
      if (!control) return;
      var label = textOf(control);
      if (label === "Create Plan" || label === "Create Plan +") {
        event.preventDefault();
        postJSON("/api/plans", {}).then(function (result) {
          if (result.ok) {
            location.assign("/my-jefit/workouts/edit?id=" + result.data.id);
          }
        });
        return;
      }
      var menuButton = control.closest("button[id^='plan-menu-']");
      if (menuButton) {
        event.preventDefault();
        var planId = menuButton.id.replace("plan-menu-", "");
        var overlay = $('[data-clone-overlay="plan-menu"]');
        if (overlay) {
          overlay.setAttribute("data-plan-id", planId);
          overlay.style.display =
            overlay.style.display === "none" ? "" : "none";
        }
        return;
      }
      var menu = control.closest('[data-clone-overlay="plan-menu"]');
      if (menu) {
        var planTarget = menu.getAttribute("data-plan-id");
        if (!planTarget) return;
        if (label === "Edit Plan") {
          event.preventDefault();
          location.assign("/my-jefit/workouts/edit?id=" + planTarget);
        } else if (label === "Set as current plan") {
          event.preventDefault();
          postJSON("/api/plans/" + planTarget + "/set-current", {}).then(
            function () {
              location.reload();
            }
          );
        } else if (label === "Delete") {
          event.preventDefault();
          postJSON("/api/plans/" + planTarget + "/delete", {}).then(
            function () {
              location.reload();
            }
          );
        } else if (label === "Printable Version") {
          event.preventDefault();
          notice(
            "The printable view is not part of this offline clone; your " +
              "plan data is available on this page and in the CSV export."
          );
        }
      }
    });
  }

  /* ---------------- member: routine editor (autosave) ---------------- */

  function initEditor() {
    if (location.pathname !== "/my-jefit/workouts/edit") return;
    var planId = (/[?&]id=(\d+)/.exec(location.search) || [])[1];
    if (!planId) return;
    var nameInput = $("input[value]");
    document.addEventListener(
      "change",
      function (event) {
        var input = event.target;
        if (input.tagName !== "INPUT") return;
        if (input === nameInput) {
          postJSON("/api/plans/" + planId + "/name", {
            name: input.value,
          }).then(function (result) {
            if (result.ok && result.data.name) {
              // empty names are silently ignored on source: restore
              input.value = result.data.name;
            }
          });
          return;
        }
        var setId = /^set-(\d+)-/.exec(input.id || "");
        var block = input.closest("[data-rfd-draggable-id]");
        if (block) {
          var entryId = (block.getAttribute("data-rfd-draggable-id") || "")
            .replace("x-", "");
          var grid = input.closest(".grid");
          var payload = {};
          var inputs = $all("input", block);
          var index = inputs.indexOf(input);
          // per-block inputs: [weight, reps] per set row, then rest
          var value = parseFloat(input.value);
          if (isNaN(value)) return;
          if (input.value === String(inputs.length)) { /* noop guard */ }
          if (index >= 0) {
            var restInput = inputs[inputs.length - 1];
            if (input === restInput) payload.rest_seconds = value;
            else if (index % 2 === 0) payload.weight_lbs = value;
            else payload.reps = value;
          }
          if (setId) { /* id carries set index; entry-level model */ }
          if (entryId && Object.keys(payload).length) {
            postJSON("/api/entries/" + entryId, payload);
          }
        }
      },
      true
    );
    document.addEventListener("click", function (event) {
      var control = event.target.closest("button, a");
      if (!control) return;
      var label = textOf(control);
      if (label === "Add Day") {
        event.preventDefault();
        postJSON("/api/plans/" + planId + "/days", {}).then(function () {
          location.reload();
        });
        return;
      }
      var add = control.closest("button[data-exercise-id]");
      if (add) {
        event.preventDefault();
        var dayEl = $("[data-rfd-droppable-id]");
        var dayId = dayEl
          ? (dayEl.getAttribute("data-rfd-droppable-id") || "").replace(
              "day-",
              ""
            )
          : "";
        if (!dayId) return;
        postJSON("/api/days/" + dayId + "/exercises", {
          exercise_id: parseInt(add.getAttribute("data-exercise-id"), 10),
        }).then(function () {
          location.reload();
        });
        return;
      }
      if (label === "Save") {
        event.preventDefault();
        location.assign("/my-jefit/workouts");
      }
    });
  }

  /* ---------------- member: workout log ---------------- */

  function initHistory() {
    if (location.pathname.indexOf("/my-jefit/progress/history") !== 0) return;
    var holder = $("#jefit-history");
    var state = { selected: "", dates: [] };
    if (holder) {
      try {
        state = JSON.parse(holder.textContent);
      } catch (err) {
        /* keep defaults */
      }
    }
    var sessionId = null;
    document.addEventListener("click", function (event) {
      var control = event.target.closest("button, a");
      if (!control) return;
      var label = textOf(control);
      if (label === "+ Add session") {
        event.preventDefault();
        var modal = $('[data-clone-modal="workout-log"]');
        if (modal) modal.style.display = "";
        return;
      }
      var modalRoot = control.closest('[data-clone-modal="workout-log"]');
      if (modalRoot) {
        var add = control.closest("button[data-exercise-id]");
        if (add) {
          event.preventDefault();
          var exerciseId = parseInt(
            add.getAttribute("data-exercise-id"),
            10
          );
          var ensure = sessionId
            ? Promise.resolve({ ok: true, data: { id: sessionId } })
            : postJSON("/api/sessions", {
                date: state.selected || undefined,
                start: "09:00",
                end: "10:00",
              });
          ensure.then(function (created) {
            if (!created.ok) return;
            sessionId = created.data.id;
            postJSON("/api/sessions/" + sessionId + "/sets", {
              exercise_id: exerciseId,
            }).then(function () {
              location.reload();
            });
          });
          return;
        }
        if (
          label === "Close" ||
          /close/i.test(control.getAttribute("aria-label") || "")
        ) {
          event.preventDefault();
          modalRoot.style.display = "none";
        }
        return;
      }
      // calendar day selection: buttons whose text is a bare day number
      var day = /^(\d{1,2})$/.exec(label);
      if (day && control.closest("main")) {
        var monthMatch = state.selected
          ? state.selected.slice(0, 8)
          : "2026-08-";
        var target =
          monthMatch + ("0" + day[1]).slice(-2);
        if (target !== state.selected) {
          event.preventDefault();
          location.assign(
            "/my-jefit/progress/history?date=" + target
          );
        }
      }
    });
  }

  /* ---------------- member: settings ---------------- */

  var SETTINGS_TABS = {
    Account: "account",
    Profile: "profile",
    Privacy: "privacy",
    "Data Controls": "data-controls",
    Integrations: "integrations",
  };

  function initSettings() {
    if (location.pathname !== "/my-jefit/settings") return;
    var config = {};
    var holder = $("#jefit-settings");
    if (holder) {
      try {
        config = JSON.parse(holder.textContent);
      } catch (err) {
        config = {};
      }
    }
    var PROFILE_CYCLES = {
      gender: ["Male", "Female", "Prefer not to say"],
      unit_system: ["Imperial", "Metric"],
      workout_level: ["Beginner", "Intermediate", "Advanced"],
      top_goal: ["Maintaining", "Bulking", "Cutting", "Strength"],
    };
    // Each panel was carved from its own captured page, so each carries a copy
    // of the tab bar. The source shows exactly one panel at a time; without an
    // initial activation all five stack (document grew to 5x the viewport), so
    // establish the default panel on load, not only on click.
    function activatePanel(key) {
      var panels = $all("[data-settings-panel]");
      if (!panels.length) return;
      var known = panels.some(function (panel) {
        return panel.getAttribute("data-settings-panel") === key;
      });
      if (!known) key = "account";
      panels.forEach(function (panel) {
        panel.style.display =
          panel.getAttribute("data-settings-panel") === key ? "" : "none";
      });
    }
    var initialTab = (config && config.active_tab) || "account";
    var tabParam = /[?&]tab=([a-z-]+)/.exec(location.search);
    if (tabParam) initialTab = tabParam[1];
    activatePanel(initialTab);

    document.addEventListener("click", function (event) {
      var control = event.target.closest("button, a");
      if (!control) return;
      var label = textOf(control);
      if (SETTINGS_TABS[label] && control.closest("nav")) {
        event.preventDefault();
        activatePanel(SETTINGS_TABS[label]);
        return;
      }
      if (label === "Resend Verification Link") {
        event.preventDefault();
        postJSON("/api/settings/resend-verification", {}).then(function () {
          var code = window.prompt(
            "A verification code was placed in the local outbox " +
              "(GET /api/outbox). Enter it to verify this account:"
          );
          if (code) {
            postJSON("/api/settings/verify-email", { code: code }).then(
              function (result) {
                if (result.ok) location.reload();
              }
            );
          }
        });
        return;
      }
      if (label === "Delete Data") {
        event.preventDefault();
        if (window.confirm("Delete all workout data for this account?")) {
          postJSON("/api/settings/delete-data", {}).then(function () {
            location.reload();
          });
        }
        return;
      }
      if (label === "Delete Account") {
        event.preventDefault();
        if (window.confirm("Permanently delete this account?")) {
          postJSON("/api/settings/delete-account", {}).then(function () {
            location.assign("/");
          });
        }
        return;
      }
      if (label === "Export" || /Export/.test(label)) {
        event.preventDefault();
        location.assign("/my-jefit/settings/export.csv");
        return;
      }
      var panel = control.closest("[data-settings-panel]");
      if (panel && panel.getAttribute("data-settings-panel") === "profile") {
        // clone-local minimal editing: clicking a value control cycles the
        // observed options and autosaves (depth evidence unavailable).
        var field = null;
        var row = control.closest("div");
        var rowText = row ? textOf(row) : "";
        Object.keys(PROFILE_CYCLES).some(function (candidate) {
          var labels = {
            gender: "Gender",
            unit_system: "Unit",
            workout_level: "level",
            top_goal: "goal",
          };
          if (rowText.toLowerCase().indexOf(labels[candidate].toLowerCase()) >= 0) {
            field = candidate;
            return true;
          }
          return false;
        });
        if (field && control.tagName === "BUTTON") {
          event.preventDefault();
          var cycle = PROFILE_CYCLES[field];
          var current = config[field] || cycle[0];
          var next = cycle[(cycle.indexOf(current) + 1) % cycle.length];
          config[field] = next;
          var payload = {};
          payload[field] = next;
          postJSON("/api/settings/profile", payload).then(function () {
            control.textContent = next;
          });
        }
        return;
      }
      if (
        panel &&
        panel.getAttribute("data-settings-panel") === "privacy" &&
        control.getAttribute("role") === "switch"
      ) {
        event.preventDefault();
        var switches = $all("[role='switch']", panel);
        var order = ["training_reports", "promotional_emails", "product_tips"];
        var idx = switches.indexOf(control);
        var name = order[idx] || order[0];
        var prefs = config.email_prefs || {};
        prefs[name] = !prefs[name];
        config.email_prefs = prefs;
        control.setAttribute(
          "aria-checked",
          prefs[name] ? "true" : "false"
        );
        postJSON("/api/settings/privacy", { email_prefs: prefs });
        return;
      }
    });
  }

  /* ---------------- member: custom exercises + create post -------------- */

  function initCustomExercises() {
    if (location.pathname !== "/my-jefit/exercises") return;
    document.addEventListener("click", function (event) {
      var control = event.target.closest("button");
      if (!control) return;
      if (/^Create custom exercise/.test(textOf(control))) {
        event.preventDefault();
        var name = window.prompt(
          "Custom exercise name (clone-local, free tier allows 3):"
        );
        if (name) {
          postJSON("/api/custom-exercises", { name: name }).then(
            function (result) {
              if (result.ok) location.reload();
              else notice(result.data.error || "Could not create exercise.");
            }
          );
        }
      }
    });
  }

  function initCreatePost() {
    document.addEventListener("click", function (event) {
      var control = event.target.closest("button");
      if (!control) return;
      var overlay = control.closest('[data-clone-overlay="create-post"]');
      if (!overlay) return;
      if (textOf(control) === "Post") {
        event.preventDefault();
        var inputs = $all("textarea, input[type='text']", overlay);
        var title = inputs.length > 1 ? inputs[0].value : "";
        var body = inputs.length > 1 ? inputs[1].value : (inputs[0] || {}).value || "";
        var feed =
          location.pathname === "/my-jefit/popular" ? "popular" : "qa";
        postJSON("/api/posts", { feed: feed, title: title, body: body }).then(
          function (result) {
            if (result.ok) {
              overlay.style.display = "none";
              if (location.pathname === "/my-jefit") {
                location.assign("/my-jefit/qa");
              } else {
                location.reload();
              }
            }
          }
        );
      }
    });
  }

  /* ---------------- boot ---------------- */

  function boot() {
    initTheme();
    initConsent();
    initNav();
    initExternalBoundaries();
    initExerciseFilters();
    initSignup();
    initSignupResults();
    initRegister();
    initLogin();
    initBuildRoutine();
    initSwipers();
    initCapturedModal();
    initMemberOverlays();
    initWorkouts();
    initEditor();
    initHistory();
    initSettings();
    initCustomExercises();
    initCreatePost();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
