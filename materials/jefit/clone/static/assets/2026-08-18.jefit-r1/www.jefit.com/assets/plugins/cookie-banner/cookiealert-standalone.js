(function () {
    "use strict";

    var OPT_OUT_KEY = "cookie-opt-out";
    var CONSENT_EVENT = "jefit:consent";

    var acceptedInThisTab = false;
    var bannerEl = null;
    var modalEl = null;
    var optIn = true;

    function readOptOut() {
        try { return localStorage.getItem(OPT_OUT_KEY); }
        catch (e) { return null; }
    }

    function writeOptOut(value) {
        try { localStorage.setItem(OPT_OUT_KEY, value); }
        catch (e) {}
    }

    function isAccepted() {
        return readOptOut() === "false";
    }

    function fireConsent() {
        if (acceptedInThisTab) return;
        acceptedInThisTab = true;
        try {
            window.dispatchEvent(new CustomEvent(CONSENT_EVENT));
        } catch (e) {
            var evt = document.createEvent("Event");
            evt.initEvent(CONSENT_EVENT, false, false);
            window.dispatchEvent(evt);
        }
    }

    window.jefitConsent = {
        isAccepted: isAccepted,
        onAccepted: function (callback) {
            if (isAccepted()) {
                acceptedInThisTab = true;
                setTimeout(callback, 0);
            } else {
                window.addEventListener(CONSENT_EVENT, callback, { once: true });
            }
        }
    };

    function accept() {
        writeOptOut("false");
        hideBanner();
        fireConsent();
    }

    function reject() {
        writeOptOut("true");
        hideBanner();
    }

    function hideBanner() {
        if (bannerEl) bannerEl.classList.remove("is-visible");
        closeModal();
    }

    function openModal() {
        if (!modalEl) return;
        modalEl.classList.add("is-visible");
        var toggle = modalEl.querySelector("#jefit-cc-optional");
        if (toggle) toggle.checked = optIn;
    }

    function closeModal() {
        if (modalEl) modalEl.classList.remove("is-visible");
    }

    function saveFromModal() {
        var toggle = modalEl && modalEl.querySelector("#jefit-cc-optional");
        optIn = !!(toggle && toggle.checked);
        if (optIn) {
            accept();
        } else {
            reject();
        }
        closeModal();
    }

    var CSS = [
        "#jefit-cc-banner{position:fixed;left:0;right:0;bottom:0;z-index:2147483000;",
        "background:#16181d;color:#fff;padding:16px 24px;",
        "box-shadow:0 -6px 24px rgba(45,124,255,.25);",
        "display:flex;flex-direction:column;gap:16px;",
        "transform:translateY(100%);transition:transform .3s ease;",
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;",
        "font-size:14px;line-height:1.45;}",
        "#jefit-cc-banner.is-visible{transform:translateY(0);}",
        "#jefit-cc-banner h4{margin:0 0 4px 0;font-size:18px;font-weight:600;color:#fff;}",
        "#jefit-cc-banner p{margin:0;color:#c7c9cf;}",
        "#jefit-cc-banner a{color:#fff;text-decoration:underline;}",
        "#jefit-cc-banner a:hover{color:#2d7cff;}",
        "#jefit-cc-banner .jefit-cc-actions{display:flex;gap:8px;flex-shrink:0;}",
        "#jefit-cc-banner button{font:inherit;border:0;border-radius:6px;padding:10px 18px;cursor:pointer;}",
        "#jefit-cc-banner .jefit-cc-btn-text{background:transparent;color:#c7c9cf;}",
        "#jefit-cc-banner .jefit-cc-btn-text:hover{color:#fff;}",
        "#jefit-cc-banner .jefit-cc-btn-primary{background:#2d7cff;color:#fff;font-weight:600;}",
        "#jefit-cc-banner .jefit-cc-btn-primary:hover{background:#1f6ae8;}",
        "@media (min-width:640px){",
        "#jefit-cc-banner{flex-direction:row;justify-content:space-between;align-items:center;padding:20px 40px;}",
        "#jefit-cc-banner .jefit-cc-copy{max-width:640px;}}",
        "#jefit-cc-modal{position:fixed;inset:0;z-index:2147483100;",
        "background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;padding:16px;}",
        "#jefit-cc-modal.is-visible{display:flex;}",
        "#jefit-cc-modal .jefit-cc-dialog{background:#1c1f26;color:#fff;border-radius:10px;",
        "max-width:520px;width:100%;padding:24px;box-shadow:0 20px 60px rgba(0,0,0,.6);",
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}",
        "#jefit-cc-modal h3{margin:0 0 16px 0;font-size:20px;font-weight:600;}",
        "#jefit-cc-modal .jefit-cc-field{padding:12px 0;border-top:1px solid #2a2e38;}",
        "#jefit-cc-modal .jefit-cc-field:first-of-type{border-top:0;}",
        "#jefit-cc-modal .jefit-cc-field-head{display:flex;justify-content:space-between;align-items:center;gap:12px;}",
        "#jefit-cc-modal label{font-weight:600;font-size:15px;}",
        "#jefit-cc-modal .jefit-cc-desc{margin:6px 0 0 0;font-size:13px;color:#c7c9cf;line-height:1.5;}",
        "#jefit-cc-modal .jefit-cc-switch{position:relative;display:inline-block;width:40px;height:22px;flex-shrink:0;}",
        "#jefit-cc-modal .jefit-cc-switch input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:pointer;z-index:1;}",
        "#jefit-cc-modal .jefit-cc-switch input:disabled{cursor:not-allowed;}",
        "#jefit-cc-modal .jefit-cc-slider{position:absolute;inset:0;background:#3a3f4a;border-radius:22px;transition:background .2s;}",
        "#jefit-cc-modal .jefit-cc-slider:before{content:'';position:absolute;height:16px;width:16px;left:3px;top:3px;",
        "background:#fff;border-radius:50%;transition:transform .2s;}",
        "#jefit-cc-modal input:checked + .jefit-cc-slider{background:#2d7cff;}",
        "#jefit-cc-modal input:checked + .jefit-cc-slider:before{transform:translateX(18px);}",
        "#jefit-cc-modal input:disabled + .jefit-cc-slider{opacity:.7;cursor:not-allowed;}",
        "#jefit-cc-modal .jefit-cc-actions{margin-top:20px;display:flex;justify-content:flex-end;}",
        "#jefit-cc-modal .jefit-cc-btn-primary{background:#2d7cff;color:#fff;font-weight:600;",
        "border:0;border-radius:6px;padding:10px 20px;cursor:pointer;font:inherit;}",
        "#jefit-cc-modal .jefit-cc-btn-primary:hover{background:#1f6ae8;}"
    ].join("");

    function injectStyle() {
        var style = document.createElement("style");
        style.setAttribute("data-jefit-cc", "1");
        style.textContent = CSS;
        (document.head || document.documentElement).appendChild(style);
    }

    function buildDom() {
        bannerEl = document.createElement("div");
        bannerEl.id = "jefit-cc-banner";
        bannerEl.setAttribute("role", "region");
        bannerEl.setAttribute("aria-label", "Cookie consent");
        bannerEl.innerHTML = [
            "<div class='jefit-cc-copy'>",
            "  <h4>We value your privacy</h4>",
            "  <p>Jefit uses cookies to keep you signed in, remember your preferences, and understand how the site is used so we can improve it. Optional cookies power analytics and product insights &mdash; they only run if you accept. You can change your choice anytime by clearing your browser storage. Read more in our <a href='/privacy-policy' target='_blank' rel='noopener'>cookie policy</a>.</p>",
            "</div>",
            "<div class='jefit-cc-actions'>",
            "  <button type='button' class='jefit-cc-btn-text' id='jefit-cc-customize'>Customize Settings</button>",
            "  <button type='button' class='jefit-cc-btn-primary' id='jefit-cc-accept'>Accept</button>",
            "</div>"
        ].join("");

        modalEl = document.createElement("div");
        modalEl.id = "jefit-cc-modal";
        modalEl.setAttribute("role", "dialog");
        modalEl.setAttribute("aria-modal", "true");
        modalEl.setAttribute("aria-labelledby", "jefit-cc-modal-title");
        modalEl.innerHTML = [
            "<div class='jefit-cc-dialog'>",
            "  <h3 id='jefit-cc-modal-title'>Customize Cookie Preferences</h3>",
            "  <div class='jefit-cc-field'>",
            "    <div class='jefit-cc-field-head'>",
            "      <label>Required cookies</label>",
            "      <span class='jefit-cc-switch'>",
            "        <input type='checkbox' checked disabled>",
            "        <span class='jefit-cc-slider'></span>",
            "      </span>",
            "    </div>",
            "    <p class='jefit-cc-desc'>These cookies are necessary for the website to function and cannot be switched off in our systems. These cookies are usually only set in response to actions made by you, such as setting your privacy preferences, logging in or filling in forms.</p>",
            "  </div>",
            "  <div class='jefit-cc-field'>",
            "    <div class='jefit-cc-field-head'>",
            "      <label for='jefit-cc-optional'>Optional cookies</label>",
            "      <span class='jefit-cc-switch'>",
            "        <input type='checkbox' id='jefit-cc-optional' checked>",
            "        <span class='jefit-cc-slider'></span>",
            "      </span>",
            "    </div>",
            "    <p class='jefit-cc-desc'>These cookies allow the website to remember choices you make, provide enhanced features, and tell us how we can improve the product. They may be set by us or by third party providers whose services we have added to our pages.</p>",
            "  </div>",
            "  <div class='jefit-cc-actions'>",
            "    <button type='button' class='jefit-cc-btn-primary' id='jefit-cc-save'>Save</button>",
            "  </div>",
            "</div>"
        ].join("");

        document.body.appendChild(bannerEl);
        document.body.appendChild(modalEl);

        document.getElementById("jefit-cc-accept").addEventListener("click", accept);
        document.getElementById("jefit-cc-customize").addEventListener("click", openModal);
        document.getElementById("jefit-cc-save").addEventListener("click", saveFromModal);
        modalEl.addEventListener("click", function (e) {
            if (e.target === modalEl) closeModal();
        });

        if (readOptOut() === null) {
            bannerEl.offsetHeight;
            bannerEl.classList.add("is-visible");
        }
    }

    function init() {
        if (document.querySelector("[data-jefit-cc]")) return;
        injectStyle();
        if (document.body) {
            buildDom();
        } else {
            document.addEventListener("DOMContentLoaded", buildDom);
        }
    }

    init();

    window.addEventListener("storage", function (e) {
        if (e.key !== OPT_OUT_KEY) return;
        if (e.newValue === "false") {
            hideBanner();
            fireConsent();
        } else if (acceptedInThisTab) {
            window.location.reload();
        }
    });
})();
