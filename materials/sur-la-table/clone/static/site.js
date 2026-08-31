const main = document.querySelector("main");
const money = cents => new Intl.NumberFormat("en-US", {style:"currency", currency:"USD"}).format(cents / 100);
const dateTime = value => new Intl.DateTimeFormat("en-US", {weekday:"long", month:"long", day:"numeric", year:"numeric", hour:"numeric", minute:"2-digit", timeZone:"America/Los_Angeles", timeZoneName:"short"}).format(new Date(value));
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const params = new URLSearchParams(location.search);

async function api(path, options = {}) {
  const init = {...options, headers:{"Content-Type":"application/json", ...(options.headers || {})}};
  const response = await fetch(path, init);
  let data;
  try { data = await response.json(); } catch { data = {error:"Unexpected local response."}; }
  if (!response.ok) throw Object.assign(new Error(data.error || "Request failed."), {data, status:response.status});
  return data;
}

function setMain(html) { main.innerHTML = html; main.focus(); }
function crumb(items) { return `<nav class="breadcrumb" aria-label="Breadcrumb">${items.map((x,i) => i === items.length - 1 ? esc(x[0]) : `<a href="${x[1]}">${esc(x[0])}</a> / `).join("")}</nav>`; }
function errorText(error) {
  if (error.data?.errors) return Object.values(error.data.errors).map(esc).join("<br>");
  return esc(error.message);
}
function formError(form, error) {
  let box = form.querySelector("[data-form-error]");
  if (!box) { box = document.createElement("div"); box.dataset.formError = ""; box.className = "error"; box.setAttribute("role", "alert"); form.prepend(box); }
  box.innerHTML = errorText(error);
}

let sessionState = null;
async function loadSession() {
  try { sessionState = (await api("/api/session")).session; } catch { sessionState = null; }
  const accountLink = document.querySelector("[data-account-link]");
  if (sessionState?.authenticated) {
    accountLink.textContent = "My classes";
    accountLink.href = "/order-history";
  }
  return sessionState;
}

function classCard(item) {
  const badge = item.status === "limited" ? `<span class="badge limited">Only ${item.seats_left} seats left</span>` : item.status === "sold-out" ? `<span class="badge sold-out">Sold out</span>` : `<span class="badge">Available</span>`;
  const link = `/cooking-class/fresh-pasta-workshop-kitchenaid/CFA-10544591?session=${encodeURIComponent(item.session_id)}`;
  return `<article class="card">
    <div class="card-image"></div><div class="card-body">${badge}
    <p class="eyebrow">${esc(item.class_type)}</p><h3><a href="${link}">${esc(item.title)}</a></h3>
    <p class="card-meta">${dateTime(item.starts_at)}<br>${esc(item.store_name)}, ${esc(item.city)}<br>${item.distance_miles} miles from downtown San Francisco</p>
    <p class="price"><strong>${money(item.price_cents)}</strong> per guest</p>
    <a class="button ${item.status === "sold-out" ? "secondary" : ""}" href="${link}">${item.status === "sold-out" ? "View other dates" : "View class"}</a>
    </div></article>`;
}

function home() {
  setMain(`<section class="hero"><div><p class="eyebrow">In-store cooking classes</p><h1>Make something memorable</h1><p>Join hands-on cooking classes led by our resident chefs. Search by location, cuisine, date, and availability.</p><a class="button light" href="/cooking-classes/">Explore cooking classes</a></div></section>
  <section class="container"><h2>Find your next class</h2><div class="feature-grid">
  <article class="feature"><p class="eyebrow">Hands-on</p><h3>In-store cooking classes</h3><p>Cook with a chef in a Sur La Table kitchen.</p><a href="/cooking-classes/in-store-cooking-classes/">Browse classes</a></article>
  <article class="feature"><p class="eyebrow">Nearby</p><h3>Find a store</h3><p>Compare class locations by distance from downtown San Francisco.</p><a href="/locations">View locations</a></article>
  <article class="feature"><p class="eyebrow">Your account</p><h3>Manage bookings</h3><p>Review upcoming classes, reschedule, or cancel eligible bookings.</p><a href="/order-history">Open class history</a></article>
  </div></section>`);
}

function classesLanding() {
  setMain(`<section class="hero"><div><p class="eyebrow">Cooking classes</p><h1>Learn. Cook. Share.</h1><p>Choose an in-store class, compare open dates, and reserve your seat in our local sandbox.</p><a class="button light" href="/cooking-classes/in-store-cooking-classes/?availability=available">Find an in-store class</a></div></section>
  <section class="container"><h2>Ways to learn</h2><div class="feature-grid"><article class="feature"><h3>In-store classes</h3><p>Hands-on instruction in a Sur La Table kitchen.</p><a href="/cooking-classes/in-store-cooking-classes/">View schedule</a></article><article class="feature"><h3>Weekend afternoons</h3><p>Find Saturday and Sunday sessions starting after noon.</p><a href="/cooking-classes/in-store-cooking-classes/?q=pasta&availability=available">Find pasta classes</a></article><article class="feature"><h3>Class questions</h3><p>Read cancellation, rescheduling, and attendance guidance.</p><a href="/cooking-class-faq.html">Read FAQ</a></article></div></section>`);
}

async function resultsPage() {
  const values = {q:params.get("q") || "", store:params.get("store") || "", cuisine:params.get("cuisine") || "", availability:params.get("availability") || "", sort:params.get("sort") || "date"};
  const search = new URLSearchParams(Object.entries(values).filter(([,v]) => v));
  const [{classes,count},{stores}] = await Promise.all([api(`/api/classes?${search}`), api("/api/stores")]);
  setMain(`<section class="container">${crumb([["Cooking Classes","/cooking-classes/"],["In-Store Cooking Classes"]])}<p class="eyebrow">Cooking class schedule</p><h1>In-Store Cooking Classes</h1><form class="filters" method="get">
  <div class="field"><label for="q">Search</label><input id="q" name="q" value="${esc(values.q)}" placeholder="Try pasta"></div>
  <div class="field"><label for="store">Location</label><select id="store" name="store"><option value="">All locations</option>${stores.map(s=>`<option value="${s.store_id}" ${values.store===s.store_id?"selected":""}>${esc(s.name)} (${s.distance_miles} mi)</option>`).join("")}</select></div>
  <div class="field"><label for="cuisine">Cuisine</label><select id="cuisine" name="cuisine"><option value="">All cuisines</option><option ${values.cuisine==="Italian"?"selected":""}>Italian</option><option ${values.cuisine==="French"?"selected":""}>French</option></select></div>
  <div class="field"><label for="availability">Availability</label><select id="availability" name="availability"><option value="">All</option><option value="available" ${values.availability==="available"?"selected":""}>Seats available</option></select></div>
  <div class="field"><label for="sort">Sort by</label><select id="sort" name="sort"><option value="date">Soonest date</option><option value="price-low" ${values.sort==="price-low"?"selected":""}>Price: low to high</option><option value="distance" ${values.sort==="distance"?"selected":""}>Distance</option><option value="availability" ${values.sort==="availability"?"selected":""}>Most seats</option></select></div>
  <button type="submit">Apply</button></form>
  <div class="results-bar"><strong>${count} class session${count===1?"":"s"}</strong><a href="/cooking-classes/in-store-cooking-classes/">Clear filters</a></div>
  ${count ? `<div class="cards">${classes.map(classCard).join("")}</div>` : `<div class="empty"><h2>No cooking classes found</h2><p>We couldn't find a class matching those filters. Clear them or return to all available in-store classes.</p><a class="button" href="/cooking-classes/in-store-cooking-classes/?availability=available">See available classes</a></div>`}
  </section>`);
}

async function locationsPage() {
  const {stores} = await api("/api/stores");
  const matchingIndex = stores.findIndex(s => Boolean(s.qualifying_pasta_session));
  setMain(`<section class="container">${crumb([["Home","/"],["Locations"]])}<p class="eyebrow">Store locator</p><h1>Locations near downtown San Francisco</h1><p>Distance ranks the observed stores. Berkeley is closest overall. Palo Alto is the nearest location with the selected available pasta class.</p><div class="store-grid">${stores.map((s,i)=>`<article class="feature" data-store-id="${esc(s.store_id)}"><span class="badge">${i+1} by distance</span><h2>${esc(s.name)}</h2><p>${esc(s.address)}</p><p><strong>${s.distance_miles} miles</strong> from downtown San Francisco</p><p class="policy">${i===0?"Closest overall. ":""}${s.qualifying_pasta_session?(i===matchingIndex?"Nearest location with a qualifying available pasta class.":"Qualifying available pasta class found."):"No qualifying available pasta class at this location."}</p><a href="/cooking-classes/in-store-cooking-classes/?store=${s.store_id}">View cooking classes</a></article>`).join("")}</div></section>`);
}

async function detailPage() {
  const sessionId = params.get("session") || "pasta-pa-20260926-1300";
  const [{class:item},{classes:alternates}] = await Promise.all([api(`/api/classes/${sessionId}`), api("/api/classes?q=pasta&sort=date")]);
  if (!item) return notFound();
  const canBook = item.status !== "sold-out" && item.seats_left > 0;
  setMain(`<section class="container">${crumb([["Cooking Classes","/cooking-classes/"],["In-Store Classes","/cooking-classes/in-store-cooking-classes/"],[item.title]])}<div class="detail-grid"><div><div class="detail-image">Fresh pasta, made by hand</div><p class="eyebrow">${esc(item.class_type)}</p><h1>${esc(item.title)}</h1><p>${esc(item.description)}</p><h2>What you'll learn</h2><ul><li>Mix and knead fresh pasta dough</li><li>Shape two pasta styles</li><li>Pair pasta with seasonal sauces</li></ul><h2>Reviews</h2><p><strong>(${item.review_count}) Reviews</strong></p><p class="card-meta">Review content was unavailable in the source evidence and is not reproduced here.</p><h2>Class policies</h2><p class="policy">Cancel or reschedule at least 48 hours before class start for a refund, gift card, or exchange. Changes within 48 hours are not eligible for a refund, exchange, or store credit.</p></div>
  <aside class="panel sticky"><span class="badge ${item.status}">${item.status === "limited" ? `Only ${item.seats_left} seats left` : item.status}</span><h2>Select this class</h2><p><strong>${dateTime(item.starts_at)}</strong></p><p>${esc(item.store_name)}<br>${esc(item.address)}<br>${item.distance_miles} miles from downtown San Francisco</p><p class="price"><strong>${money(item.price_cents)}</strong> per guest</p><div class="field"><label for="party">Guests</label><select id="party"><option value="1">1 person</option><option value="2">2 people</option><option value="3">3 people</option><option value="4">4 people</option></select></div><p class="party-comparison" role="status">1 guest totals ${money(item.price_cents)}.</p><p>${canBook ? `<a class="button" data-book href="/booking/review?session=${item.session_id}&party=1">Continue to review</a>` : `<a class="button secondary" href="/cooking-classes/in-store-cooking-classes/?q=pasta&availability=available">Find another date</a>`}</p></aside></div>
  <h2>Compare pasta class dates</h2><div class="cards">${alternates.map(classCard).join("")}</div></section>`);
  document.querySelector("#party")?.addEventListener("change", event => {
    const link = document.querySelector("[data-book]");
    if (link) link.href = `/booking/review?session=${item.session_id}&party=${event.target.value}`;
    document.querySelector(".party-comparison").textContent = `${event.target.value} guest${event.target.value==="1"?"":"s"} total ${money(item.price_cents*Number(event.target.value))}.`;
  });
}

async function loginPage() {
  await loadSession();
  const returnTo = params.get("return") || "/order-history";
  setMain(`<section class="container narrow">${crumb([["Home","/"],["Sign In"]])}<p class="eyebrow">My account</p><h1>Sign In</h1><p>Email and password are the available identity choices. No identity-provider sign-in was observed.</p><form class="form" data-login novalidate><div class="field"><label for="email">Email address</label><input id="email" name="email" type="email" autocomplete="email" required></div><div class="field"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required></div><button type="submit">Sign in</button></form><p><a href="/account/forgot-password">Forgot password?</a></p><p>New here? <a href="/account/registration">Create an account</a>.</p><div class="policy"><strong>Seeded account for local history checks</strong><br>Email: history@example.test<br>Password: Pasta2026!</div></section>`);
  document.querySelector("[data-login]").addEventListener("submit", async event => {
    event.preventDefault(); const form = event.currentTarget;
    const missing = [];
    if (!form.email.value.trim()) missing.push("Email address is required");
    if (!form.password.value) missing.push("Password is required");
    if (missing.length) { formError(form, new Error(missing.join(". "))); return; }
    try { await api("/api/auth/sign-in", {method:"POST",body:JSON.stringify({email:form.email.value,password:form.password.value})}); location.href = returnTo.startsWith("/") ? returnTo : "/order-history"; }
    catch (error) { formError(form,error); }
  });
}

function registrationPage() {
  const returnTo = params.get("return") || "/order-history";
  setMain(`<section class="container narrow">${crumb([["Home","/"],["Create Account"]])}<p class="eyebrow">My account</p><h1>Create an Account</h1><form class="form" data-register novalidate><div class="form-row"><div class="field"><label for="first-name">First name</label><input id="first-name" name="first_name" autocomplete="given-name" required></div><div class="field"><label for="last-name">Last name</label><input id="last-name" name="last_name" autocomplete="family-name" required></div></div><div class="field"><label for="email">Email address</label><input id="email" name="email" type="email" autocomplete="email" required></div><div class="field"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="new-password" minlength="8" required><small>Use 8 to 128 characters. Password cannot contain only spaces.</small></div><label><input type="checkbox" name="marketing"> Send me Sur La Table offers (optional)</label><p>By creating an account, you agree to the <a href="/terms" data-static-link>Terms of Use</a> and acknowledge the <a href="/privacy" data-static-link>Privacy Policy</a>.</p><button type="submit">Create account</button></form><section data-verification hidden><h2>Verify your local account</h2><p class="local-guidance" role="status"></p><div class="local-code-value" data-local-secret></div><button type="button" class="secondary" data-use-local-code>Use local verification code</button><form class="form" data-verify><div class="field"><label for="code">Verification code</label><input id="code" name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required></div><button type="submit">Verify account</button></form></section><p>Already registered? <a href="/account/login">Return to sign in</a>.</p></section>`);
  document.querySelectorAll("[data-static-link]").forEach(link => link.addEventListener("click", e => { e.preventDefault(); alert("This offline clone does not reproduce the full legal document. The source registration surface exposed this link."); }));
  const form = document.querySelector("[data-register]");
  let localCode = "";
  form.addEventListener("submit", async event => { event.preventDefault(); try { const data = await api("/api/auth/registration", {method:"POST",body:JSON.stringify(Object.fromEntries(new FormData(form)))}); localCode=String(data.verification_code||""); const section=document.querySelector("[data-verification]"); section.hidden=false; section.querySelector(".local-guidance").textContent=data.guidance; section.querySelector(".local-code-value").textContent=localCode; section.scrollIntoView({behavior:"smooth"}); } catch(error){ formError(form,error); } });
  document.querySelector("[data-use-local-code]").addEventListener("click",()=>{document.querySelector("[data-verify] input[name=code]").value=localCode;});
  document.querySelector("[data-verify]").addEventListener("submit", async event => { event.preventDefault(); const verify=event.currentTarget; try { await api("/api/auth/registration/verify", {method:"POST",body:JSON.stringify({code:verify.code.value})}); location.href=returnTo.startsWith("/")?returnTo:"/order-history"; } catch(error){ formError(verify,error); } });
}

function recoveryPage() {
  setMain(`<section class="container narrow">${crumb([["Sign In","/account/login"],["Reset Password"]])}<p class="eyebrow">Account access</p><h1>Reset Your Password</h1><p>Enter the email address associated with your local account. The public response does not reveal whether an account exists.</p><form class="form" data-recovery novalidate><div class="field"><label for="email">Email address</label><input id="email" name="email" type="email" autocomplete="email" required><small>Email address is required to continue. No reset message is sent until this form is submitted.</small></div><button type="submit">Continue</button></form><p><a href="/account/login">Return to sign in</a></p></section>`);
  document.querySelector("[data-recovery]").addEventListener("submit", async event => { event.preventDefault(); const form=event.currentTarget; try { const data=await api("/api/auth/recovery",{method:"POST",body:JSON.stringify({email:form.email.value})}); form.innerHTML=`<div class="success" role="status">${esc(data.message)} No real reset email was sent.</div>`; } catch(error){formError(form,error);} });
}

async function reviewPage() {
  const sessionId=params.get("session") || "pasta-pa-20260926-1300";
  const party=Math.min(8,Math.max(1,Number(params.get("party") || 1)));
  const [state,{class:item}]=await Promise.all([loadSession(),api(`/api/classes/${sessionId}`)]);
  if (!item) return notFound();
  if (!state?.authenticated) {
    const back=encodeURIComponent(location.pathname+location.search);
    setMain(`<section class="container narrow">${crumb([["Class details",`/cooking-class/fresh-pasta-workshop-kitchenaid/CFA-10544591?session=${sessionId}`],["Booking review"]])}<p class="eyebrow">Account required</p><h1>Sign in to continue</h1><p>Your booking must be tied to a local account before it can be confirmed.</p><div class="actions"><a class="button" href="/account/login?return=${back}">Sign in</a><a class="button secondary" href="/account/registration?return=${back}">Create an account</a></div></section>`); return;
  }
  const total=item.price_cents*party; const account=state.account;
  setMain(`<section class="container">${crumb([["Class details",`/cooking-class/fresh-pasta-workshop-kitchenaid/CFA-10544591?session=${sessionId}`],["Booking review"]])}<p class="eyebrow">Final review</p><h1>Review your booking</h1><div class="review-grid"><form class="form" data-booking novalidate><h2>Attendee details</h2><div class="field"><label for="attendee-name">Attendee name</label><input id="attendee-name" name="attendee_name" value="${esc(account.display_name)}" required></div><div class="field"><label for="attendee-email">Attendee email</label><input id="attendee-email" name="attendee_email" type="email" value="${esc(account.email_normalized)}" required></div><h2>Local sandbox outcome</h2><div class="field"><label for="scenario">Payment simulation</label><select id="scenario" name="scenario_id"><option value="sandbox-approved">Simulated approval</option><option value="sandbox-declined">Simulated decline</option><option value="sandbox-retry">Simulated retry</option></select><small>No card number, CVV, expiry date, bank account, deposit, or live payment is accepted.</small></div><label><input type="checkbox" name="terms" required> I agree to the 48-hour class cancellation policy.</label><button type="submit">Confirm local booking</button></form><aside class="panel sticky"><p class="eyebrow">Your class</p><h2>${esc(item.title)}</h2><p><strong>${dateTime(item.starts_at)}</strong><br>${esc(item.store_name)}<br>${esc(item.address)}</p><div class="totals"><div><span>${party} guest${party===1?"":"s"} x ${money(item.price_cents)}</span><span>${money(total)}</span></div><div><span>Subtotal</span><span>${money(total)}</span></div><div class="total"><span>Total</span><span>${money(total)}</span></div></div><p class="card-meta">USD. No tax, fee, deposit, discount, or gratuity.</p></aside></div></section>`);
  const form=document.querySelector("[data-booking]");
  form.addEventListener("submit",async event=>{event.preventDefault();if(!form.terms.checked){formError(form,new Error("Accept the cancellation policy before continuing."));return;}form.querySelector("button").disabled=true;try{const data=await api("/api/bookings",{method:"POST",body:JSON.stringify({session_id:sessionId,party_size:party,attendee_name:form.attendee_name.value,attendee_email:form.attendee_email.value,scenario_id:form.scenario_id.value,idempotency_key:`review-${sessionId}-${party}-${account.subject_id}`})});location.href=`/booking/confirmation/${data.booking.booking_id}`;}catch(error){formError(form,error);form.querySelector("button").disabled=false;}});
}

async function confirmationPage() {
  await loadSession();
  const bookingId=location.pathname.split("/").filter(Boolean).pop();
  try {
    const {booking:b}=await api(`/api/bookings/${encodeURIComponent(bookingId)}`);
    if(!b) return notFound();
    setMain(`<section class="container narrow"><div class="success">Your local cooking class booking is confirmed.</div><p class="eyebrow">Confirmation ${esc(b.booking_id)}</p><h1>You're booked</h1><div class="panel"><h2>${esc(b.title)}</h2><p><strong>${dateTime(b.starts_at)}</strong><br>${esc(b.store_name)}<br>${esc(b.address)}</p><div class="totals"><div><span>Guests</span><span>${b.party_size}</span></div><div><span>Attendee</span><span>${esc(b.attendee_name)}</span></div><div><span>Subtotal</span><span>${money(b.subtotal_cents)}</span></div><div class="total"><span>Total</span><span>${money(b.total_cents)} USD</span></div></div><p><span class="badge">${esc(b.status)}</span></p><p class="card-meta">Payment adapter: local-sandbox. No real payment or external reservation occurred.</p></div><div class="actions"><a class="button" href="/order-history">View my classes</a><a class="button secondary" href="/cooking-classes/in-store-cooking-classes/">Book another class</a></div></section>`);
  } catch(error) {
    if(error.status===401) setMain(`<section class="container narrow"><h1>Sign in to view confirmation</h1><p>This confirmation belongs to a local account.</p><a class="button" href="/account/login?return=${encodeURIComponent(location.pathname)}">Sign in</a></section>`); else throw error;
  }
}

async function historyPage() {
  const state=await loadSession();
  if(!state?.authenticated){setMain(`<section class="container narrow">${crumb([["Home","/"],["My Cooking Classes"]])}<p class="eyebrow">Account history</p><h1>My Cooking Classes</h1><p>Sign in to view upcoming and past class bookings.</p><a class="button" href="/account/login?return=/order-history">Sign in</a></section>`);return;}
  const {bookings}=await api("/api/bookings");
  setMain(`<section class="container">${crumb([["Cooking Classes","/cooking-classes/"],["My Cooking Classes"]])}<div class="results-bar"><div><p class="eyebrow">Account history</p><h1>My Cooking Classes</h1></div><button class="secondary" data-signout>Sign out</button></div>${bookings.length?bookings.map(b=>`<article class="booking-row" data-booking-id="${esc(b.booking_id)}"><div class="booking-head"><div><p class="eyebrow">${esc(b.booking_id)}</p><h2>${esc(b.title)}</h2><p>${dateTime(b.starts_at)}<br>${esc(b.store_name)}<br>${esc(b.address)}</p></div><div><span class="badge status">${esc(b.status)}</span><p><strong>${money(b.total_cents)}</strong><br>${b.party_size} guest${b.party_size===1?"":"s"}</p></div></div><details><summary>Booking details and options</summary><p>Attendee: ${esc(b.attendee_name)} (${esc(b.attendee_email)})</p><p>Cancellation policy: changes must be made at least 48 hours before class start.</p>${b.status!=="cancelled"?`<form class="actions" data-reschedule-form="${esc(b.booking_id)}"><label>Replacement date <select name="session_id"><option value="pasta-pa-20260927-1500">Sunday, September 27, 2026 at 3:00 PM</option></select></label><button class="secondary" type="submit">Reschedule</button></form><button class="danger" data-cancel="${esc(b.booking_id)}" data-confirmed="false">Cancel booking</button>`:"<p>This booking is cancelled and cannot be changed.</p>"}</details></article>`).join(""):`<div class="empty"><h2>No class bookings yet</h2><p>Browse available in-store classes to start your history.</p><a class="button" href="/cooking-classes/in-store-cooking-classes/?availability=available">Find a class</a></div>`}<p><a href="/cooking-classes/in-store-cooking-classes/">Return to in-store cooking classes</a></p></section>`);
  document.querySelector("[data-signout]").addEventListener("click",async()=>{await api("/api/auth/sign-out",{method:"POST",body:"{}"});location.href="/account/login";});
  document.querySelectorAll("[data-cancel]").forEach(button=>button.addEventListener("click",async()=>{if(button.dataset.confirmed!=="true"){button.dataset.confirmed="true";button.textContent="Confirm cancellation";return;}try{await api(`/api/bookings/${button.dataset.cancel}/actions`,{method:"POST",body:JSON.stringify({action:"cancel"})});historyPage();}catch(error){formError(button.closest("details"),error);}}));
  document.querySelectorAll("[data-reschedule-form]").forEach(form=>form.addEventListener("submit",async event=>{event.preventDefault();try{await api(`/api/bookings/${form.dataset.rescheduleForm}/actions`,{method:"POST",body:JSON.stringify({action:"reschedule",session_id:form.session_id.value})});historyPage();}catch(error){formError(form,error);}}));
}

function faqPage(){setMain(`<section class="container narrow">${crumb([["Cooking Classes","/cooking-classes/"],["Cooking Class FAQ"]])}<p class="eyebrow">Help</p><h1>Cooking Class FAQ</h1><div class="help-list"><details open><summary>Can I cancel or reschedule a class?</summary><p>With at least 48 hours' notice, choose a refund, gift card, or exchange. Within 48 hours of class start, refunds, exchanges, and store credit are unavailable.</p></details><details><summary>What happens if an action fails?</summary><p>Keep your current page open, correct the field named in the message, and try once more. A retryable local sandbox result does not create a booking or charge.</p></details><details><summary>How do I access my account?</summary><p>Use the sign-in page with email and password. Registration and password recovery use local-only verification and do not send real email.</p></details></div><p><a class="button" href="/contactus">Contact support</a></p></section>`);}

function contactPage(){setMain(`<section class="container narrow">${crumb([["Home","/"],["Contact Us"]])}<p class="eyebrow">Customer service</p><h1>How can we help?</h1><div class="help-list"><details open><summary>Cooking classes</summary><p>Find booking, rescheduling, cancellation, and attendance guidance in the <a href="/cooking-class-faq.html">Cooking Class FAQ</a>. This offline clone does not send contact forms or place calls.</p></details><details><summary>Account access</summary><p>Open <a href="/account/login">sign in</a>, <a href="/account/registration">registration</a>, or <a href="/account/forgot-password">password recovery</a>. Local verification never exposes private account data.</p></details><details><summary>Failed actions</summary><p>Read the inline error, correct the named field, and retry. Declined and retryable sandbox outcomes never create a charge.</p></details></div><div class="policy"><strong>Cooking class support</strong><br>Public phone guidance was visible on the source contact surface. This clone intentionally does not initiate a call or message.</div></section>`);}

function notFound(){setMain(`<section class="not-found"><p class="code">410</p><p class="eyebrow">Page unavailable</p><h1>We couldn't find that page</h1><p>The link may be old or the page may have moved. Primary navigation remains available above.</p><div class="actions"><a class="button" href="/cooking-classes/">Cooking classes</a><a class="button secondary" href="/cooking-classes/in-store-cooking-classes/?availability=available">Available in-store classes</a></div></section>`);}

async function route(){
  await loadSession();
  const path=location.pathname;
  try{
    if(path==="/")home();
    else if(path==="/cooking-classes/"||path==="/cooking-classes")classesLanding();
    else if(path==="/cooking-classes/in-store-cooking-classes/"||path==="/cooking-classes/in-store-cooking-classes")await resultsPage();
    else if(path.startsWith("/cooking-class/"))await detailPage();
    else if(path==="/locations")await locationsPage();
    else if(path==="/account/login")await loginPage();
    else if(path==="/account/registration")registrationPage();
    else if(path==="/account/forgot-password")recoveryPage();
    else if(path==="/booking/review")await reviewPage();
    else if(path.startsWith("/booking/confirmation/"))await confirmationPage();
    else if(path==="/order-history")await historyPage();
    else if(path==="/cooking-class-faq.html")faqPage();
    else if(path==="/contactus")contactPage();
    else notFound();
  }catch(error){setMain(`<section class="container narrow"><h1>Something went wrong</h1><p class="error">${errorText(error)}</p><a class="button" href="/cooking-classes/">Return to cooking classes</a></section>`);}
}

route();
