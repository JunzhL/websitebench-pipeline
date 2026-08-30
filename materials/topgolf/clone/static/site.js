const main = document.querySelector("main");
const money = cents => `$${(Number(cents) / 100).toFixed(2)}`;
const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);

document.querySelector(".menu")?.addEventListener("click", event => {
  const nav = document.querySelector(".nav");
  nav.classList.toggle("open");
  event.currentTarget.setAttribute("aria-expanded", String(nav.classList.contains("open")));
});

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  const payload = await response.json().catch(() => ({error: "The local service returned an unreadable response."}));
  if (!response.ok) {
    const error = new Error(payload.error || "The local request failed.");
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function crumb(items) {
  return `<nav class="crumb" aria-label="Breadcrumb">${items.map((item, index) => index === items.length - 1 ? `<span>${escapeHtml(item[0])}</span>` : `<a href="${item[1]}">${escapeHtml(item[0])}</a> / `).join("")}</nav>`;
}

function formatDate(startsAt) {
  return new Intl.DateTimeFormat("en-US", {weekday:"long", month:"long", day:"numeric", year:"numeric", timeZone:"America/New_York"}).format(new Date(startsAt));
}

function formatTime(startsAt) {
  return new Intl.DateTimeFormat("en-US", {hour:"numeric", minute:"2-digit", timeZone:"America/New_York"}).format(new Date(startsAt));
}

function endTime(startsAt, duration) {
  return new Intl.DateTimeFormat("en-US", {hour:"numeric", minute:"2-digit", timeZone:"America/New_York"}).format(new Date(new Date(startsAt).getTime() + duration * 60000));
}

async function ensureSession() {
  return api("/api/session");
}

function showFormError(form, error) {
  const box = form.querySelector("[data-form-error]");
  if (box) {
    const fieldErrors = error.payload?.errors;
    box.textContent = fieldErrors ? Object.values(fieldErrors).join(" ") : error.message;
    box.classList.remove("hidden");
    box.focus?.();
  }
}

function home() {
  main.innerHTML = `
    <section class="hero">
      <div><p class="eyebrow">Everyone's game</p><h1>It's golf.<br>It's not golf.</h1><p class="lede">Come play around in a climate-controlled bay with games, food, drinks, and plenty of room for your crew.</p><a class="button light" href="/us/experience/">Explore the experience</a></div>
      <div class="booking-card"><p class="eyebrow">Book a bay</p><h2>Plan your visit</h2>
        <form class="form" data-home-search novalidate>
          <div class="field"><label for="home-location">Location</label><select id="home-location" name="location" required><option value="cleveland">Topgolf Cleveland</option></select></div>
          <div class="form-row"><div class="field"><label for="home-date">Date</label><input id="home-date" name="date" type="date" value="2026-09-05" required></div><div class="field"><label for="home-time">Time</label><select id="home-time" name="time"><option value="14:00">2:00 PM</option><option value="15:00">3:00 PM</option></select></div></div>
          <div class="field"><label for="home-players">Players</label><select id="home-players" name="players">${[1,2,3,4,5,6].map(n => `<option value="${n}" ${n===4?"selected":""}>${n} player${n===1?"":"s"}</option>`).join("")}</select></div>
          <p class="error hidden" data-form-error tabindex="-1"></p><button class="button" type="submit">Find a time</button>
        </form>
      </div>
    </section>
    <section class="content"><div class="section-head"><div><p class="eyebrow">Ways to play</p><h2>More than a driving range</h2></div><a href="/us/locations/">View all locations</a></div>
      <div class="cards"><article class="card"><div class="card-visual">01</div><div class="card-body"><h3>Games for everyone</h3><p>Track every shot and choose games for beginners or experienced players.</p></div></article><article class="card"><div class="card-visual">02</div><div class="card-body"><h3>Food and drinks</h3><p>Order from your bay while you play.</p></div></article><article class="card"><div class="card-visual">03</div><div class="card-body"><h3>All-weather bays</h3><p>Climate-controlled bays keep the group comfortable.</p></div></article></div>
    </section>`;
  ensureSession().catch(() => {});
  main.querySelector("[data-home-search]").addEventListener("submit", event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const date = data.get("date");
    if (!date) return showFormError(event.currentTarget, new Error("Choose a date."));
    location.href = `/us/cleveland/plan-a-visit/?date=${encodeURIComponent(date)}&time=${encodeURIComponent(data.get("time"))}&players=${encodeURIComponent(data.get("players"))}`;
  });
}

function experience() {
  main.innerHTML = `<section class="page-hero dark"><p class="eyebrow">PLAY</p><h1>The Topgolf Experience</h1><p class="lede">A place to play, eat, drink, and have fun, whether you golf all the time or have never picked up a club.</p><span class="canonical">/us/experience/</span></section>
  <section class="content">${crumb([["Home","/us/"],["Experience"]])}<div class="split"><div><h2>Come play around</h2><p class="lede">Every bay has clubs, targets, ball tracking, seating, and service from the venue team.</p><div class="cards"><article class="card"><div class="card-body"><h3>Choose a game</h3><p>Play target games made for different skill levels.</p></div></article><article class="card"><div class="card-body"><h3>Bring your crew</h3><p>Up to six players can share one bay.</p></div></article></div></div><aside class="panel"><h3>Ready to play?</h3><p>Find the closest observed venue and compare available times.</p><a class="button" href="/us/locations/">Find a location</a></aside></div></section>`;
}

async function locations() {
  main.innerHTML = `<section class="page-hero"><p class="eyebrow">Find your venue</p><h1>Topgolf Locations</h1><p class="lede">Search observed venues and compare straight-line distance from downtown Toronto.</p><span class="canonical">/us/locations/</span></section><section class="content"><form class="filters" data-location-search><div class="field"><label for="location-query">City, state, or venue</label><input id="location-query" name="q" placeholder="Try Cleveland"></div><button class="button" type="submit">Search locations</button></form><div data-location-results></div></section>`;
  const form = main.querySelector("[data-location-search]");
  const results = main.querySelector("[data-location-results]");
  async function load() {
    const q = new FormData(form).get("q") || "";
    const data = await api(`/api/venues?q=${encodeURIComponent(q)}`);
    if (!data.count) {
      results.innerHTML = `<div class="empty"><h2>No locations found</h2><p>We couldn't find a venue for <strong>${escapeHtml(q)}</strong>.</p><button class="button secondary" data-clear-search>View available locations</button></div>`;
      results.querySelector("[data-clear-search]").addEventListener("click", () => {form.q.value = ""; load();});
      return;
    }
    results.innerHTML = `<div class="cards">${data.venues.map((venue, index) => `<article class="card"><div class="card-visual">${String(index+1).padStart(2,"0")}</div><div class="card-body"><p class="distance">${venue.distance_km.toFixed(1)} km from downtown Toronto</p><h3>${escapeHtml(venue.name)}</h3><p>${escapeHtml(venue.address)}</p><p class="meta">${index===0?"Closest observed Topgolf":"Observed alternative"}</p><a class="button secondary" href="${venue.venue_id === "cleveland" ? "/us/cleveland/" : "/us/locations/"}">View venue</a></div></article>`).join("")}</div>`;
  }
  form.addEventListener("submit", event => {event.preventDefault(); load().catch(error => results.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`);});
  await load();
}

async function venue() {
  await ensureSession();
  const [{venue}, favorite] = await Promise.all([api("/api/venues/cleveland"), api("/api/favorites/cleveland").catch(() => ({saved:false}))]);
  main.innerHTML = `<section class="page-hero dark"><p class="eyebrow">Ohio</p><h1>${escapeHtml(venue.name)}</h1><p class="lede">${escapeHtml(venue.description)}</p><span class="canonical">/us/cleveland/</span></section>
  <section class="content">${crumb([["Home","/us/"],["Locations","/us/locations/"],["Cleveland"]])}<div class="split"><div><p class="distance">Closest observed venue to downtown Toronto, ${venue.distance_km.toFixed(1)} km straight-line</p><h2>Plan your visit</h2><p>${escapeHtml(venue.address)}</p><div class="help-list"><article class="help-item"><h3>Pricing</h3><p>${escapeHtml(venue.pricing_note)}</p></article><article class="help-item"><h3>Hours</h3><p>${escapeHtml(venue.hours_note)}</p></article><article class="help-item"><h3>Policies and availability</h3><p>${escapeHtml(venue.policy_note)}</p></article><article class="help-item"><h3>Amenities</h3><p>Climate-controlled bays, complimentary clubs, games, food and beverage service, and accessible venue support.</p></article></div></div><aside class="panel sticky"><h3>Topgolf Cleveland</h3><p>${escapeHtml(venue.address)}</p><a class="button" href="/us/cleveland/plan-a-visit/">Book a Bay</a><button class="button secondary" data-favorite type="button">${favorite.saved?"Saved":"Save venue"}</button><p class="notice local hidden" data-favorite-note aria-live="polite"></p></aside></div></section>`;
  const button = main.querySelector("[data-favorite]");
  button.addEventListener("click", async () => {
    const remove = button.textContent === "Saved";
    const state = await api("/api/favorites/cleveland", {method: remove ? "DELETE" : "POST", body: "{}"});
    button.textContent = state.saved ? "Saved" : "Save venue";
    const note = main.querySelector("[data-favorite-note]");
    note.textContent = state.saved ? "Cleveland is saved for this local account or browser session." : "Cleveland was removed from saved venues.";
    note.classList.remove("hidden");
  });
}

async function planVisit() {
  await ensureSession();
  const params = new URLSearchParams(location.search);
  const initialDate = params.get("date") || "2026-09-05";
  const initialTime = params.get("time") || "14:00";
  const players = Number(params.get("players") || 4);
  main.innerHTML = `<section class="page-hero"><p class="eyebrow">Book a bay</p><h1>Choose your play time</h1><p class="lede">Topgolf Cleveland</p><span class="canonical">/us/cleveland/plan-a-visit/</span></section><section class="content">${crumb([["Home","/us/"],["Cleveland","/us/cleveland/"],["Plan a Visit"]])}<div class="split"><div><form class="form" data-options><div class="form-row"><div class="field"><label for="visit-date">Date</label><select id="visit-date" name="date"><option value="2026-09-05" ${initialDate==="2026-09-05"?"selected":""}>Saturday, September 5, 2026</option><option value="2026-09-12" ${initialDate==="2026-09-12"?"selected":""}>Saturday, September 12, 2026</option></select></div><div class="field"><label for="visit-time">Start time</label><select id="visit-time" name="time"><option value="14:00" ${initialTime==="14:00"?"selected":""}>2:00 PM</option><option value="15:00" ${initialTime==="15:00"?"selected":""}>3:00 PM</option></select></div></div><div class="field"><label for="visit-players">Players</label><select id="visit-players" name="players">${[1,2,3,4,5,6].map(n => `<option value="${n}" ${n===players?"selected":""}>${n} player${n===1?"":"s"}</option>`).join("")}</select><small>One bay accommodates up to six players.</small></div></form><h2>Available sessions</h2><p>Compare durations for the selected date and time. No source slot hold is created.</p><div class="slots" data-slots></div></div><aside class="panel sticky" data-selection><h3>Your selection</h3><p>Choose an available session.</p></aside></div></section>`;
  const form = main.querySelector("[data-options]");
  const slotsBox = main.querySelector("[data-slots]");
  const selectionBox = main.querySelector("[data-selection]");
  let selected = null;
  async function loadSlots() {
    const values = new FormData(form);
    const date = values.get("date");
    const time = values.get("time");
    const data = await api(`/api/venues/cleveland/availability?date=${encodeURIComponent(date)}`);
    const matches = data.slots.filter(slot => slot.starts_at.slice(11,16) === time);
    slotsBox.innerHTML = matches.length ? matches.map(slot => `<button type="button" class="slot ${slot.available?"":"unavailable"}" data-slot="${slot.slot_id}" ${slot.available?"":"disabled"}><span><strong>${slot.duration_minutes} minutes</strong><small>${formatTime(slot.starts_at)} - ${endTime(slot.starts_at,slot.duration_minutes)}</small>${slot.recommended?'<span class="tag">Recommended</span>':""}</span><strong>${money(slot.price_cents)}</strong>${slot.available?"":'<small>Unavailable</small>'}</button>`).join("") : `<div class="empty"><h3>No matching sessions</h3><p>Change the date or start time to compare availability.</p></div>`;
    selected = matches.find(slot => slot.available && slot.recommended) || matches.find(slot => slot.available) || null;
    renderSelection();
    slotsBox.querySelectorAll("[data-slot]:not(:disabled)").forEach(button => button.addEventListener("click", () => {selected = matches.find(slot => slot.slot_id === button.dataset.slot); renderSelection();}));
  }
  function renderSelection() {
    slotsBox.querySelectorAll("[data-slot]").forEach(button => button.classList.toggle("selected", selected && button.dataset.slot === selected.slot_id));
    if (!selected) {selectionBox.innerHTML = `<h3>Your selection</h3><p>No available session selected.</p>`; return;}
    const party = Number(form.players.value);
    selectionBox.innerHTML = `<h3>Your selection</h3><div class="summary-list"><div class="summary-row"><span>Location</span><strong>Topgolf Cleveland</strong></div><div class="summary-row"><span>Date</span><strong>${formatDate(selected.starts_at)}</strong></div><div class="summary-row"><span>Time</span><strong>${formatTime(selected.starts_at)} - ${endTime(selected.starts_at,selected.duration_minutes)}</strong></div><div class="summary-row"><span>Players</span><strong>${party}</strong></div><div class="summary-row"><span>Bay</span><strong>1</strong></div><div class="summary-row"><span>Duration</span><strong>${selected.duration_minutes} minutes</strong></div><div class="summary-row total"><span>Gameplay</span><strong>${money(selected.price_cents)}</strong></div></div><p class="notice">Prices exclude sales tax. A one-time new-player membership fee may apply on the source site.</p><button class="button" data-continue>Continue to review</button>`;
    selectionBox.querySelector("[data-continue]").addEventListener("click", () => {
      sessionStorage.setItem("topgolf-booking-selection", JSON.stringify({slot_id:selected.slot_id,party_size:party,selected_at:Date.now()}));
      location.href = "/booking/review";
    });
  }
  form.addEventListener("change", loadSlots);
  await loadSlots();
}

async function bookingReview() {
  await ensureSession();
  const selection = JSON.parse(sessionStorage.getItem("topgolf-booking-selection") || '{"slot_id":"cle-20260905-1400-120","party_size":4,"selected_at":0}');
  if (selection.selected_at && Date.now() - Number(selection.selected_at) > 15 * 60 * 1000) {
    main.innerHTML = `<section class="content narrow"><div class="empty"><h1>Your booking session expired</h1><p>Choose a current time to refresh availability. No slot was held.</p><a class="button" href="/us/cleveland/plan-a-visit/">Choose another time</a></div></section>`;
    return;
  }
  let quote;
  try {
    quote = (await api("/api/booking/quote", {method:"POST", body:JSON.stringify(selection)})).quote;
  } catch (error) {
    main.innerHTML = `<section class="content narrow"><div class="empty"><h1>Session no longer available</h1><p>${escapeHtml(error.message)}</p><a class="button" href="/us/cleveland/plan-a-visit/">Choose another time</a></div></section>`;
    return;
  }
  main.innerHTML = `<section class="page-hero"><p class="eyebrow">Local checkout</p><h1>Review your bay</h1><p class="lede">Confirm your details before creating a local reservation.</p><span class="canonical">/booking/review</span></section><section class="content">${crumb([["Home","/us/"],["Choose a Time","/us/cleveland/plan-a-visit/"],["Review"]])}<div class="split"><div><div class="notice local"><strong>Offline sandbox</strong><br>No real payment, SMS, source hold, or source booking will occur.</div><h2>Guest details</h2><form class="form" data-booking-form novalidate><div class="form-row"><div class="field"><label for="first-name">First Name</label><input id="first-name" name="first_name" autocomplete="given-name" required><span class="field-error" data-error="first_name"></span></div><div class="field"><label for="last-name">Last Name</label><input id="last-name" name="last_name" autocomplete="family-name" required><span class="field-error" data-error="last_name"></span></div></div><div class="form-row"><div class="field"><label for="guest-phone">Phone Number</label><input id="guest-phone" name="phone" type="tel" autocomplete="tel" placeholder="416-555-0188" required><span class="field-error" data-error="phone"></span></div><div class="field"><label for="guest-email">Email Address</label><input id="guest-email" name="email" type="email" autocomplete="email" placeholder="guest@example.test" required><span class="field-error" data-error="email"></span></div></div><div class="field"><label for="accessibility">Accessibility request</label><textarea id="accessibility" name="accessibility_request" placeholder="Tell the venue team about access needs"></textarea></div><div class="field"><label for="special-request">Special requests</label><textarea id="special-request" name="special_request" placeholder="Optional local note"></textarea></div><div class="field"><label for="scenario">Payment outcome</label><select id="scenario" name="scenario_id"><option value="sandbox-approved">Local sandbox approval</option><option value="sandbox-declined">Local sandbox decline</option><option value="sandbox-retry">Local sandbox retry</option></select><small>No payment credentials are collected.</small></div><label class="check"><input type="checkbox" name="terms_accepted" required><span>I agree to the <a href="/us/faq/">Terms and cancellation policy</a>. Changes generally close two hours before the reservation.</span></label><p class="error hidden" data-form-error tabindex="-1"></p><button class="button" type="submit">Book Now in Local Sandbox</button></form></div><aside class="panel sticky"><p class="eyebrow">Payment summary</p><h3>${escapeHtml(quote.venue_name)}</h3><div class="summary-list"><div class="summary-row"><span>Date</span><strong>${formatDate(quote.starts_at)}</strong></div><div class="summary-row"><span>Time</span><strong>${formatTime(quote.starts_at)} - ${endTime(quote.starts_at,quote.duration_minutes)}</strong></div><div class="summary-row"><span>Duration</span><strong>${quote.duration_minutes} minutes</strong></div><div class="summary-row"><span>Players</span><strong>${quote.party_size}</strong></div><div class="summary-row"><span>Bays</span><strong>1</strong></div><div class="summary-row"><span>Gameplay subtotal</span><strong>${money(quote.subtotal_cents)}</strong></div><div class="summary-row"><span>Tax</span><strong>Unavailable, not included</strong></div><div class="summary-row"><span>Membership fee</span><strong>May apply, not included</strong></div><div class="summary-row total"><span>Total</span><strong>${money(quote.total_cents)} USD</strong></div><div class="summary-row"><span>Due now</span><strong>${money(quote.total_cents)} USD</strong></div><div class="summary-row"><span>Due at location</span><strong>$0.00 USD</strong></div></div></aside></div></section>`;
  const form = main.querySelector("[data-booking-form]");
  form.addEventListener("submit", async event => {
    event.preventDefault();
    form.querySelectorAll(".field-error").forEach(el => el.textContent = "");
    const data = Object.fromEntries(new FormData(form));
    const errors = {};
    for (const field of ["first_name","last_name","phone","email"]) if (!String(data[field] || "").trim()) errors[field] = `${field.replace("_"," ")} is required.`;
    if (!data.terms_accepted) errors.terms_accepted = "Accept the Terms and cancellation policy.";
    Object.entries(errors).forEach(([key, message]) => {const target=form.querySelector(`[data-error="${key}"]`);if(target)target.textContent=message;});
    if (Object.keys(errors).length) return showFormError(form, {message:Object.values(errors).join(" "),payload:{errors}});
    const payload = {...data, slot_id:selection.slot_id, party_size:Number(selection.party_size), terms_accepted:true, idempotency_key:sessionStorage.getItem("topgolf-submission-key") || crypto.randomUUID()};
    sessionStorage.setItem("topgolf-submission-key", payload.idempotency_key);
    try {
      const result = await api("/api/reservations", {method:"POST", body:JSON.stringify(payload)});
      sessionStorage.setItem("topgolf-last-reservation", result.reservation.reservation_id);
      location.href = `/booking/confirmation/${encodeURIComponent(result.reservation.reservation_id)}`;
    } catch (error) {showFormError(form, error);}
  });
}

async function confirmation() {
  const reservationId = decodeURIComponent(location.pathname.split("/").pop());
  try {
    const {reservation} = await api(`/api/reservations/${encodeURIComponent(reservationId)}`);
    main.innerHTML = `<section class="page-hero dark"><p class="eyebrow">Local confirmation</p><h1>Your bay is booked</h1><p class="lede">Reservation ${escapeHtml(reservation.reservation_id)}</p><span class="canonical">${escapeHtml(location.pathname)}</span></section><section class="content narrow"><article class="panel confirmation"><div class="confirmation-icon" aria-hidden="true">✓</div><span class="status ${reservation.status}">${escapeHtml(reservation.status)}</span><h2>We'll see you at Topgolf Cleveland</h2><p>This confirmation belongs only to this local browser session or verified account. Refreshing this page reloads the saved reservation from the site database.</p><div class="summary-list"><div class="summary-row"><span>Location</span><strong>${escapeHtml(reservation.venue_name)}</strong></div><div class="summary-row"><span>Address</span><strong>${escapeHtml(reservation.address)}</strong></div><div class="summary-row"><span>Date</span><strong>${formatDate(reservation.starts_at)}</strong></div><div class="summary-row"><span>Time</span><strong>${formatTime(reservation.starts_at)} - ${endTime(reservation.starts_at,reservation.duration_minutes)}</strong></div><div class="summary-row"><span>Duration</span><strong>${reservation.duration_minutes} minutes</strong></div><div class="summary-row"><span>Players</span><strong>${reservation.party_size}</strong></div><div class="summary-row"><span>Bays</span><strong>${reservation.bay_count}</strong></div><div class="summary-row"><span>Gameplay subtotal</span><strong>${money(reservation.subtotal_cents)}</strong></div><div class="summary-row"><span>Tax</span><strong>Unavailable, not included</strong></div><div class="summary-row"><span>Membership fee</span><strong>May apply, not included</strong></div><div class="summary-row total"><span>Total</span><strong>${money(reservation.total_cents)} USD</strong></div><div class="summary-row"><span>Payment</span><strong>Approved, local-sandbox</strong></div></div><p class="notice local">No source booking, SMS, payment, or email occurred.</p><div class="form-row"><a class="button secondary" href="/reservations/${encodeURIComponent(reservation.reservation_id)}">Manage reservation</a><a class="button" href="/us/cleveland/plan-a-visit/">Book again</a></div></article></section>`;
  } catch (error) {
    main.innerHTML = `<section class="content narrow"><div class="empty"><h1>Confirmation unavailable</h1><p>${escapeHtml(error.message)}</p><a class="button" href="/us/cleveland/plan-a-visit/">Return to available times</a></div></section>`;
  }
}

function phoneLogin() {
  main.innerHTML = `<section class="page-hero"><p class="eyebrow">My account</p><h1>Sign in with your mobile number</h1><p class="lede">The observed booking flow uses SMS verification. This clone keeps verification local and sends no message.</p><span class="canonical">/account/login</span></section><section class="content narrow">${crumb([["Home","/us/"],["Sign In"]])}<div class="panel"><form class="form" data-phone-start novalidate><div class="field"><label for="country">Country</label><select id="country" name="country"><option value="US-CA">United States / Canada (+1)</option></select></div><div class="field"><label for="mobile-number">Mobile number</label><input id="mobile-number" name="phone" type="tel" autocomplete="tel" placeholder="416-555-0188" required><span class="field-error" data-error="phone"></span></div><p class="error hidden" data-form-error tabindex="-1"></p><button class="button" type="submit">Send Code</button><p class="meta">By continuing, you acknowledge the <a href="/us/faq/">Terms</a> and <a href="/us/company/contact-us/">Privacy guidance</a>.</p></form><form class="form hidden" data-phone-verify novalidate><div class="notice local">No SMS was sent. Enter a test code to inspect validation, or use the local verification action.</div><div class="field"><label for="verification-code">Verification code</label><input id="verification-code" name="code" inputmode="numeric" maxlength="6" pattern="[0-9]{6}" aria-describedby="code-guidance"><small id="code-guidance">Enter the six-digit code. Five incorrect attempts lock the challenge.</small></div><p class="error hidden" data-form-error tabindex="-1"></p><div class="form-row"><button class="button secondary" type="submit">Verify code</button><button class="button" type="button" data-use-local>Use local verification</button></div><button type="button" class="button secondary" data-back-phone>Back to mobile number</button></form></div></section>`;
  ensureSession().catch(() => {});
  const start = main.querySelector("[data-phone-start]");
  const verify = main.querySelector("[data-phone-verify]");
  start.addEventListener("submit", async event => {
    event.preventDefault();
    try {
      await api("/api/auth/phone/start", {method:"POST", body:JSON.stringify({phone:new FormData(start).get("phone")})});
      start.classList.add("hidden"); verify.classList.remove("hidden"); verify.querySelector("input").focus();
    } catch (error) {showFormError(start,error);}
  });
  async function complete(payload) {
    try {
      await api("/api/auth/phone/verify", {method:"POST", body:JSON.stringify(payload)});
      location.href = "/reservations";
    } catch (error) {showFormError(verify,error);}
  }
  verify.addEventListener("submit", event => {event.preventDefault();complete({code:new FormData(verify).get("code")});});
  verify.querySelector("[data-use-local]").addEventListener("click", () => complete({use_local_code:true}));
  verify.querySelector("[data-back-phone]").addEventListener("click", () => {verify.classList.add("hidden");start.classList.remove("hidden");});
}

async function history() {
  main.innerHTML = `<section class="page-hero"><p class="eyebrow">My account</p><h1>My Reservations</h1><p class="lede">Upcoming local bay reservations.</p><span class="canonical">/reservations</span></section><section class="content" data-history><div class="loading">Loading reservations...</div></section>`;
  const box = main.querySelector("[data-history]");
  try {
    const session = await ensureSession();
    if (!session.authenticated) {
      box.innerHTML = `<div class="empty"><h2>Verify your mobile number</h2><p>Sign in to view account-owned reservations and management options.</p><a class="button" href="/account/login">Sign in</a><a class="button secondary" href="/us/cleveland/plan-a-visit/">Return to available bays</a></div>`;
      return;
    }
    const data = await api("/api/reservations");
    if (!data.reservations.length) {
      box.innerHTML = `<div class="empty"><h2>No upcoming reservations</h2><p>Book a bay, or verify the same mobile number used for a guest reservation.</p><a class="button" href="/us/cleveland/plan-a-visit/">Find a time</a></div>`;
      return;
    }
    box.innerHTML = `<div class="section-head"><div><p class="eyebrow">Signed in as</p><h2>${escapeHtml(session.account.display_name)}</h2></div><button class="button secondary" data-sign-out>Sign out</button></div><div class="cards">${data.reservations.map(item => `<article class="card"><div class="card-body"><span class="status ${item.status}">${escapeHtml(item.status)}</span><h3>${escapeHtml(item.venue_name)}</h3><p><strong>${formatDate(item.starts_at)}</strong><br>${formatTime(item.starts_at)} for ${item.duration_minutes} minutes</p><p>${item.party_size} players, ${item.bay_count} bay</p><p class="meta">${escapeHtml(item.reservation_id)}</p><a class="button secondary" href="/reservations/${encodeURIComponent(item.reservation_id)}">View details</a></div></article>`).join("")}</div>`;
    box.querySelector("[data-sign-out]").addEventListener("click", async () => {await api("/api/auth/sign-out",{method:"POST",body:"{}"});location.href="/us/";});
  } catch (error) {box.innerHTML = `<div class="empty"><h2>Reservations unavailable</h2><p>${escapeHtml(error.message)}</p><button class="button" onclick="location.reload()">Try again</button></div>`;}
}

async function reservationDetail() {
  const id = decodeURIComponent(location.pathname.split("/").pop());
  main.innerHTML = `<section class="page-hero"><p class="eyebrow">Manage</p><h1>Reservation details</h1><span class="canonical">${escapeHtml(location.pathname)}</span></section><section class="content narrow" data-reservation-detail><div class="loading">Loading reservation...</div></section>`;
  const box = main.querySelector("[data-reservation-detail]");
  try {
    const {reservation} = await api(`/api/reservations/${encodeURIComponent(id)}`);
    box.innerHTML = `<article class="panel"><span class="status ${reservation.status}">${escapeHtml(reservation.status)}</span><h2>${escapeHtml(reservation.venue_name)}</h2><div class="summary-list"><div class="summary-row"><span>Reservation</span><strong>${escapeHtml(reservation.reservation_id)}</strong></div><div class="summary-row"><span>Date</span><strong>${formatDate(reservation.starts_at)}</strong></div><div class="summary-row"><span>Time</span><strong>${formatTime(reservation.starts_at)} - ${endTime(reservation.starts_at,reservation.duration_minutes)}</strong></div><div class="summary-row"><span>Players</span><strong>${reservation.party_size}</strong></div><div class="summary-row total"><span>Total</span><strong>${money(reservation.total_cents)} USD</strong></div><div class="summary-row"><span>Refund</span><strong>${escapeHtml(reservation.refund_status)}</strong></div></div>${reservation.status!=="cancelled"?`<div class="form"><button class="button secondary" data-reschedule>Move to Saturday, September 12 at 2:00 PM</button><button class="button danger" data-cancel>Cancel and refund local reservation</button><p class="error hidden" data-action-error></p></div>`:"<p>Cancelled reservations cannot be changed.</p>"}<a href="/reservations">Back to reservations</a></article>`;
    async function act(action, slotId) {
      try {
        await api(`/api/reservations/${encodeURIComponent(id)}/actions`, {method:"POST",body:JSON.stringify({action,slot_id:slotId})});
        location.reload();
      } catch (error) {const node=box.querySelector("[data-action-error]");node.textContent=error.message;node.classList.remove("hidden");}
    }
    box.querySelector("[data-reschedule]")?.addEventListener("click", () => act("reschedule","cle-20260912-1400-120"));
    box.querySelector("[data-cancel]")?.addEventListener("click", () => act("cancel"));
  } catch (error) {
    box.innerHTML = `<div class="empty"><h2>Reservation unavailable</h2><p>${escapeHtml(error.message)}</p><a class="button" href="/reservations">Back to reservations</a><a class="button secondary" href="/us/locations/">Browse locations</a></div>`;
  }
}

function faq() {
  main.innerHTML = `<section class="page-hero"><p class="eyebrow">Help</p><h1>Frequently Asked Questions</h1><p class="lede">Guidance for visits, reservations, account access, and failed actions.</p><span class="canonical">/us/faq/</span></section><section class="content narrow"><div class="help-list"><article class="help-item"><h2>Booking a bay</h2><p>Select a venue, date, start time, player count, and duration. One bay supports up to six players.</p><a href="/us/cleveland/plan-a-visit/">View available bays</a></article><article class="help-item"><h2>Changes and cancellations</h2><p>Local reservations can generally change or cancel at least two hours before the start. Local cancellation marks the sandbox payment refunded.</p><a href="/reservations">Open reservations</a></article><article class="help-item"><h2>Account access</h2><p>The observed sign-in uses a mobile number and SMS. This clone sends no SMS and provides a local verification action.</p><a href="/account/login">Open sign in</a></article><article class="help-item"><h2>Failed actions</h2><p>Return to available times after a conflict, resend after an expired challenge, or retry a local-sandbox payment outcome.</p><a href="/us/company/contact-us/">More support options</a></article></div></section>`;
}

function contact() {
  main.innerHTML = `<section class="page-hero dark"><p class="eyebrow">Support</p><h1>Contact Topgolf</h1><p class="lede">Find public guidance without exposing account or reservation data.</p><span class="canonical">/us/company/contact-us/</span></section><section class="content"><div class="cards"><article class="card"><div class="card-body"><h2>Reservations</h2><p>Use local reservation details to inspect, reschedule, or cancel. No message is sent.</p><a href="/reservations">My Reservations</a></div></article><article class="card"><div class="card-body"><h2>Account access</h2><p>Review mobile-number verification and validation guidance.</p><a href="/account/login">Sign-in help</a></div></article><article class="card"><div class="card-body"><h2>Failed action</h2><p>Return safely to available bays and retry with another local outcome.</p><a href="/us/cleveland/plan-a-visit/">Available bays</a></div></article></div><p class="notice local">This offline support page never sends messages or reveals private account data.</p></section>`;
}

function simplePage(type) {
  const pages = {
    app:["Topgolf App","Keep scores and manage play from the Topgolf app. App installation is outside this local clone.","/us/company/app/"],
    memberships:["Memberships","A one-time new-player membership fee may apply on the source site. Its amount was unavailable and is not included in local totals.","/us/pricing/memberships/"],
  };
  const item = pages[type];
  main.innerHTML = `<section class="page-hero"><p class="eyebrow">Topgolf</p><h1>${item[0]}</h1><p class="lede">${item[1]}</p><span class="canonical">${item[2]}</span></section><section class="content narrow"><a class="button" href="/us/cleveland/plan-a-visit/">Book a Bay</a></section>`;
}

function notFound() {
  main.innerHTML = `<section class="page-hero dark"><p class="eyebrow">404</p><h1>That shot went out of bounds</h1><p class="lede">The page you requested does not exist, but primary navigation and safe recovery routes are still available.</p></section><section class="content narrow"><div class="empty"><h2>Let's get you back in play</h2><p>Browse observed locations or return to the Topgolf experience.</p><a class="button" href="/us/locations/">Find a location</a><a class="button secondary" href="/us/experience/">Topgolf Experience</a></div></section>`;
}

const path = location.pathname;
const route = path === "/" || path === "/us/" ? home
  : path === "/us/experience/" ? experience
  : path === "/us/locations/" ? locations
  : path === "/us/cleveland/" ? venue
  : path === "/us/cleveland/plan-a-visit/" ? planVisit
  : path === "/booking/review" ? bookingReview
  : path.startsWith("/booking/confirmation/") ? confirmation
  : path === "/account/login" ? phoneLogin
  : path === "/reservations" ? history
  : path.startsWith("/reservations/") ? reservationDetail
  : path === "/us/faq/" ? faq
  : path === "/us/company/contact-us/" ? contact
  : path === "/us/company/app/" ? () => simplePage("app")
  : path === "/us/pricing/memberships/" ? () => simplePage("memberships")
  : notFound;

Promise.resolve(route()).catch(error => {
  main.innerHTML = `<section class="content narrow"><div class="empty"><h1>Something went wrong</h1><p>${escapeHtml(error.message)}</p><button class="button" onclick="location.reload()">Try again</button><a class="button secondary" href="/us/locations/">Browse locations</a></div></section>`;
});
