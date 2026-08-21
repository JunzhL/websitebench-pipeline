/*
 * Clone-local behaviour bundle.
 *
 * The build pass strips every script the source shipped, UIkit included, so the
 * handful of controls the frozen journeys depend on are reimplemented here from
 * the *same attributes the source markup already carries*. Nothing here invents
 * an interaction the source does not have, and nothing here makes a network
 * request of any kind.
 *
 * Implemented:
 *   - uk-filter: the plan grids. `/privacy-protection-plans/`, `/pricing/`,
 *     `/scan/` and `/signup/` all drive their cards with `uk-filter-control`
 *     over a target container. Two notations ship on this source - a JSON
 *     object and UIkit's `filter: X; group: Y` shorthand - and both are parsed.
 *     The hidden size-filter container keeps its inline `display:none`, exactly
 *     as the source ships it, so nothing here makes an inoperable control
 *     operable.
 *   - lazy images: the source lazy-loads below the fold through `data-src` and
 *     `data-srcset`. With the loader gone those payloads would never be
 *     requested, so they are promoted once at boot.
 *   - uk-toggle / uk-offcanvas: the mobile header menu.
 *   - the checkout promo panel.
 *
 * `document.documentElement[data-deleteme-clone="ready"]` is the handshake the
 * operability tests wait on.
 */
(function () {
  "use strict";

  function all(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  /* ---------------------------------------------------------------- filters */

  function parseControl(raw) {
    var value = (raw || "").trim();
    if (!value) return null;
    if (value.charAt(0) === "{") {
      try {
        var parsed = JSON.parse(value);
        return { filter: parsed.filter || "", group: parsed.group || "" };
      } catch (error) {
        return null;
      }
    }
    var out = { filter: "", group: "" };
    value.split(";").forEach(function (part) {
      var colon = part.indexOf(":");
      if (colon === -1) return;
      var key = part.slice(0, colon).trim();
      var item = part.slice(colon + 1).trim();
      if (key === "filter") out.filter = item;
      else if (key === "group") out.group = item;
    });
    return out.filter ? out : null;
  }

  function parseOptions(raw) {
    var out = {};
    (raw || "").split(";").forEach(function (part) {
      var colon = part.indexOf(":");
      if (colon === -1) return;
      out[part.slice(0, colon).trim()] = part.slice(colon + 1).trim();
    });
    return out;
  }

  function wireFilter(container) {
    var options = parseOptions(container.getAttribute("uk-filter"));
    var targetSelector = options.target;
    if (!targetSelector) return;
    var target = container.querySelector(targetSelector);
    if (!target) return;
    var controls = all("[uk-filter-control]", container).filter(function (node) {
      return parseControl(node.getAttribute("uk-filter-control")) !== null;
    });
    if (!controls.length) return;

    var state = {};
    controls.forEach(function (node) {
      var spec = parseControl(node.getAttribute("uk-filter-control"));
      if (node.classList.contains("uk-active")) state[spec.group] = spec.filter;
      else if (!(spec.group in state)) state[spec.group] = state[spec.group] || null;
    });

    function apply() {
      var active = Object.keys(state)
        .map(function (group) {
          return state[group];
        })
        .filter(Boolean);
      Array.prototype.forEach.call(target.children, function (item) {
        var visible = active.every(function (selector) {
          try {
            return item.matches(selector);
          } catch (error) {
            return true;
          }
        });
        // The source's own filter writes exactly this inline style, which is
        // what the frozen `plans.term-1y` and `plans.term-2y` captures show.
        item.style.display = visible ? "" : "none";
      });
    }

    controls.forEach(function (node) {
      var spec = parseControl(node.getAttribute("uk-filter-control"));
      node.addEventListener("click", function (event) {
        event.preventDefault();
        state[spec.group] = spec.filter;
        controls.forEach(function (other) {
          var otherSpec = parseControl(other.getAttribute("uk-filter-control"));
          if (otherSpec.group === spec.group) other.classList.remove("uk-active");
        });
        node.classList.add("uk-active");
        apply();
      });
      var anchor = node.querySelector("a,button");
      if (anchor) {
        anchor.addEventListener("click", function (event) {
          event.preventDefault();
        });
      }
    });

    apply();
  }

  function wireFilters() {
    all("[uk-filter]").forEach(wireFilter);
  }

  /* ------------------------------------------------------------ lazy images */

  function resolveLazyImages() {
    all("img[data-src], img[data-srcset], source[data-srcset], source[data-src]").forEach(
      function (node) {
        var set = node.getAttribute("data-srcset");
        if (set) node.setAttribute("srcset", set);
        var src = node.getAttribute("data-src");
        if (src) node.setAttribute("src", src);
        node.removeAttribute("loading");
      }
    );
    all("[data-bg]").forEach(function (node) {
      var url = node.getAttribute("data-bg");
      if (url) node.style.backgroundImage = 'url("' + url + '")';
    });
  }

  /* ------------------------------------------------------------ mobile menu */

  function wireToggles() {
    all("[uk-toggle]").forEach(function (node) {
      var options = parseOptions(node.getAttribute("uk-toggle"));
      var selector = options.target || node.getAttribute("href");
      if (!selector || selector.charAt(0) !== "#") return;
      var panel = document.querySelector(selector);
      if (!panel) return;
      node.addEventListener("click", function (event) {
        event.preventDefault();
        var open = panel.classList.toggle("uk-open");
        panel.setAttribute("aria-hidden", open ? "false" : "true");
        if (panel.classList.contains("uk-offcanvas")) {
          panel.style.display = open ? "block" : "";
        }
      });
    });
    all(".uk-offcanvas-close").forEach(function (node) {
      node.addEventListener("click", function (event) {
        event.preventDefault();
        var panel = node.closest(".uk-offcanvas");
        if (!panel) return;
        panel.classList.remove("uk-open");
        panel.style.display = "";
      });
    });
  }

  /* --------------------------------------------------------------- checkout */

  function wirePromoPanel() {
    all("[data-promo-toggle]").forEach(function (node) {
      var panel = document.querySelector("[data-promo-panel]");
      if (!panel) return;
      node.addEventListener("click", function (event) {
        event.preventDefault();
        var open = panel.hasAttribute("hidden");
        if (open) panel.removeAttribute("hidden");
        else panel.setAttribute("hidden", "");
        node.setAttribute("aria-expanded", open ? "true" : "false");
      });
    });
  }

  /* ------------------------------------------------- application-host fields */

  function primeFloatingLabels() {
    // The application host renders its labels as overlays inside the field.
    // Emotion's rules for that never reached the capture, so `clone.css`
    // rebuilds the effect and needs `:placeholder-shown` to know when the
    // field is empty.
    all(".MuiInputBase-input").forEach(function (node) {
      if (!node.getAttribute("placeholder")) node.setAttribute("placeholder", " ");
    });
  }

  function boot() {
    primeFloatingLabels();
    resolveLazyImages();
    wireFilters();
    wireToggles();
    wirePromoPanel();
    document.documentElement.setAttribute("data-deleteme-clone", "ready");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
