/* IPVanish offline clone runtime.
 *
 * The served documents are the captured post-render DOM with every source
 * <script> removed: re-running the site's own JavaScript would either hydrate
 * an SPA over the server-rendered markup or call a third party, and both are
 * forbidden. This bundle puts back, clone-locally, only the behaviour a frozen
 * journey needs, reproducing what the source's own handlers did.
 *
 * Nothing here makes a network request.
 */
(function () {
  "use strict";

  function all(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  /* ------------------------------------------------------ Astra breakpoint */

  /* Astra does not switch its header layout by media query alone: its frontend
   * script stamps `ast-desktop` or `ast-header-break-point` on <body> against
   * the theme's configured breakpoint, and its stylesheets key off that class.
   * The served document is the desktop capture, so it carries `ast-desktop`;
   * without this the mobile header's Get Started button computed
   * `display: none` at every viewport. The breakpoint value is carried on this
   * script tag by the build tool, read out of the capture itself. */
  function syncHeaderBreakpoint() {
    var tag = document.querySelector("script[data-astra-breakpoint]");
    if (!tag) {
      /* The Angular checkout, the Next.js SSO views and the Zendesk support
       * centre are not Astra pages and carry no breakpoint, so there is no
       * class to switch. */
      return;
    }
    var configured = parseInt(tag.getAttribute("data-astra-breakpoint"), 10);
    if (!configured || isNaN(configured)) {
      return;
    }
    var narrow = window.innerWidth < configured;
    document.body.classList.toggle("ast-header-break-point", narrow);
    document.body.classList.toggle("ast-desktop", !narrow);
  }

  /* ---------------------------------------------------------------- images */

  /* The source runs lazysizes: images below the fold ship a 1px data: gif in
   * `src` and the real URL in `data-src`. With the source scripts gone nothing
   * would ever swap them, so the clone does the swap itself. */
  function resolveLazyImages(root) {
    all("[data-src],[data-srcset]", root).forEach(function (node) {
      var src = node.getAttribute("data-src");
      var srcset = node.getAttribute("data-srcset");
      if (srcset) {
        node.setAttribute("srcset", srcset);
      }
      if (src) {
        node.setAttribute("src", src);
      }
      if (node.classList.contains("lazyload")) {
        node.classList.remove("lazyload");
        node.classList.add("lazyloaded");
      }
    });
  }

  /* --------------------------------------------------------------- pricing */

  /* The pricing tabs are bare <p><strong> elements on the source; its jQuery
   * showed one period's panels and hid the other two, and toggled `active` on
   * the tab. Desktop and mobile strips drive their own panels -- the source
   * does not synchronise them, and neither does this. */
  var PERIODS = [
    { key: "biennial", tab: "biennial-link", panel: "pricing-pg-biennial-tab", query: "2-year" },
    { key: "annual", tab: "annual-link", panel: "pricing-pg-yearly-tab", query: "yearly" },
    { key: "monthly", tab: "monthly-link", panel: "pricing-pg-monthly-tab", query: "monthly" }
  ];

  function selectPeriod(period, mobile) {
    PERIODS.forEach(function (entry) {
      var tabClass = mobile ? entry.tab.replace("-link", "-mobile-link") : entry.tab;
      var panelClass = mobile
        ? entry.panel.replace("pricing-pg-", "pricing-pg-mobile-")
        : entry.panel;
      var active = entry.key === period.key;
      all("." + tabClass).forEach(function (tab) {
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", active ? "true" : "false");
      });
      all("." + panelClass).forEach(function (panel) {
        panel.style.display = active ? "block" : "none";
      });
    });
    if (window.history && window.history.replaceState) {
      var url = window.location.pathname + "?period=" + period.query;
      window.history.replaceState(null, "", url);
    }
  }

  function wirePricing() {
    if (!document.querySelector(".pricing-nav-wrapper")) {
      return;
    }
    [false, true].forEach(function (mobile) {
      PERIODS.forEach(function (entry) {
        var tabClass = mobile ? entry.tab.replace("-link", "-mobile-link") : entry.tab;
        all("." + tabClass).forEach(function (tab) {
          /* The source ships a <p>; make it reachable by keyboard too without
           * changing the element, so pixels stay as captured. */
          if (!tab.hasAttribute("tabindex")) {
            tab.setAttribute("tabindex", "0");
          }
          if (!tab.hasAttribute("role")) {
            tab.setAttribute("role", "tab");
          }
          tab.style.cursor = "pointer";
          tab.addEventListener("click", function () {
            selectPeriod(entry, mobile);
          });
          tab.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              selectPeriod(entry, mobile);
            }
          });
        });
      });
    });
    /* Establish the initial state explicitly. The JEFIT run shipped stacked
     * tab panels precisely because nothing did this. */
    var requested = new URLSearchParams(window.location.search).get("period");
    var lookup = {
      "2-year": "biennial",
      biennial: "biennial",
      yearly: "annual",
      annual: "annual",
      monthly: "monthly"
    };
    var wanted = lookup[(requested || "").toLowerCase()] || "biennial";
    PERIODS.forEach(function (entry) {
      if (entry.key === wanted) {
        selectPeriod(entry, false);
        selectPeriod(entry, true);
      }
    });
  }

  /* The source's plan-card buttons carry no href in markup; its jQuery copies
   * the checkout URL from the sibling cart link. */
  function wirePlanButtons() {
    all(".wp-block-button__link").forEach(function (button) {
      if (button.getAttribute("href")) {
        return;
      }
      var card = button.closest(".wp-block-column, .wp-block-group") || document;
      var cart = card.querySelector("a.monthly-cart-link[href], a[href*='/checkout/']");
      if (cart) {
        button.setAttribute("href", cart.getAttribute("href"));
      }
    });
  }

  /* ------------------------------------------------------------- mega menu */

  /* Astra opens a mega menu on hover through CSS; the captured open state adds
   * `ast-menu-hover hover focus` to the <li> and drops `ast-hidden` from the
   * panel. Reproduce that on a real click so the state is operable by pointer
   * as well as by hover. */
  function wireMegaMenu() {
    all("li.astra-megamenu-li").forEach(function (item) {
      var panel = item.querySelector("ul.astra-megamenu");
      var toggles = all(".dropdown-menu-toggle, .ast-menu-toggle", item);
      if (!panel) {
        return;
      }
      function open(state) {
        item.classList.toggle("ast-menu-hover", state);
        item.classList.toggle("hover", state);
        item.classList.toggle("focus", state);
        if (state) {
          item.setAttribute("data-megamenu-trigger", "hover");
          panel.classList.remove("ast-hidden");
        } else {
          panel.classList.add("ast-hidden");
        }
      }
      toggles.forEach(function (toggle) {
        toggle.addEventListener("click", function (event) {
          event.preventDefault();
          event.stopPropagation();
          open(!item.classList.contains("ast-menu-hover"));
        });
      });
      var link = item.querySelector("a.menu-link");
      if (link && (link.getAttribute("href") || "#") === "#") {
        link.addEventListener("click", function (event) {
          event.preventDefault();
          open(!item.classList.contains("ast-menu-hover"));
        });
      }
    });
  }

  function wireMobileMenu() {
    all("button.menu-toggle").forEach(function (button) {
      button.addEventListener("click", function () {
        var open = !button.classList.contains("toggled");
        button.classList.toggle("toggled", open);
        button.setAttribute("aria-expanded", open ? "true" : "false");
        var nav = document.querySelector(
          "#ast-mobile-header .ast-mobile-header-content, .main-header-bar-navigation"
        );
        if (nav) {
          nav.style.display = open ? "block" : "";
        }
      });
    });
  }

  /* --------------------------------------------------- pricing feature lists */

  /* The mobile cards' "View All Features ∨" / "Hide All Features ∧" control. */
  function wireFeatureToggles() {
    all("[class*='-features-link']").forEach(function (control) {
      var panel = control
        .closest(".wp-block-group, .wp-block-column")
        .parentNode.querySelector("[class*='-features-view']");
      if (!panel) {
        return;
      }
      control.style.cursor = "pointer";
      control.addEventListener("click", function () {
        var hidden = window.getComputedStyle(panel).display === "none";
        panel.style.display = hidden ? "block" : "none";
        control.textContent = hidden
          ? "Hide All Features ∧"
          : "View All Features ∨";
      });
    });
  }

  /* ---------------------------------------------------------- checkout rows */

  /* Step one of the checkout is a payment-method chooser. Activating a row
   * navigates to the same path with `method=`, so the server derives the order
   * summary and the sandbox form rather than the client. */
  var METHODS = [
    ["c-payment-method-type-select__item--cc", "card"],
    ["c-payment-method-type-select__item--paypal", "paypal"],
    ["c-payment-method-type-select__item--applepay", "applepay"],
    ["c-payment-method-type-select__item--googlepay", "googlepay"]
  ];

  function wireCheckoutChooser() {
    METHODS.forEach(function (entry) {
      all("." + entry[0]).forEach(function (row) {
        var item = row.closest("li") || row;
        item.style.cursor = "pointer";
        item.setAttribute("role", "button");
        if (!item.hasAttribute("tabindex")) {
          item.setAttribute("tabindex", "0");
        }
        function go(event) {
          if (event) {
            event.preventDefault();
          }
          var params = new URLSearchParams(window.location.search);
          params.set("method", entry[1]);
          window.location.assign(
            window.location.pathname + "?" + params.toString()
          );
        }
        /* The revealed sandbox form and the `Subscribe now` button both live
         * inside the Credit card <li>, and the button is associated with the
         * form by its `form` attribute rather than by containment. A row-level
         * navigation handler would swallow that submit, so anything
         * interactive inside the row is left alone. */
        var GUARD =
          "#ipvanish-sandbox-form, suite-payment-method-form," +
          " vipre-customizable-terms-conditions, [data-clone-action]," +
          " button, a, input, select, textarea, label, legend";
        item.addEventListener("click", function (event) {
          if (event.target.closest(GUARD)) {
            return;
          }
          go(event);
        });
        item.addEventListener("keydown", function (event) {
          if (event.key === "Enter" || event.key === " ") {
            go(event);
          }
        });
      });
    });
  }

  /* ------------------------------------------------------------------ boot */

  function boot() {
    syncHeaderBreakpoint();
    window.addEventListener("resize", syncHeaderBreakpoint);
    resolveLazyImages(document);
    wirePlanButtons();
    wirePricing();
    wireMegaMenu();
    wireMobileMenu();
    wireFeatureToggles();
    wireCheckoutChooser();
    document.documentElement.setAttribute("data-ipvanish-clone", "ready");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
