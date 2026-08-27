
(function(){
  var script = document.currentScript;
  var token = (script && script.dataset && script.dataset.token) || '';

  // Use the same origin as the script src so this works on workers.dev or seal.vpntrust.net
  var origin;
  try {
    origin = new URL(script.src).origin;
  } catch (e) {
    origin = window.location.origin;
  }

  var style = document.createElement('style');
  style.textContent = '.vti-badge{display:inline-flex;align-items:center;font:600 12px/1.2 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;border:1px solid #e5e7eb;border-radius:999px;padding:6px 10px;gap:8px}.vti-dot{width:8px;height:8px;border-radius:999px;background:#10b981}.vti-badge.pending .vti-dot{background:#f59e0b}.vti-badge.revoked .vti-dot,.vti-badge.unregistered .vti-dot,.vti-badge.unknown .vti-dot{background:#ef4444}.vti-muted{color:#6b7280}';
  document.head.appendChild(style);

  function mountBadge(state){
    var span = document.createElement('span');
    span.className = 'vti-badge ' + state;
    span.setAttribute('aria-label', 'VTI Trust Seal');

    var dot = document.createElement('span');
    dot.className = 'vti-dot';

    var text = document.createElement('span');
    text.className = 'vti-muted';

    var label = 'VTI Verified Member';
    if (state === 'pending') label = 'VTI Membership Pending';
    if (['revoked','unregistered','unknown','inactive'].indexOf(state) >= 0) label = 'VTI Not Verified';

    text.textContent = label;

    span.appendChild(dot);
    span.appendChild(text);

    var anchor = document.createElement('a');
    anchor.href = origin + '/verify?token=' + encodeURIComponent(token);
    anchor.target = '_blank';
    anchor.rel = 'noopener nofollow';
    anchor.appendChild(span);

    (script && script.parentNode || document.body).insertBefore(anchor, script);
  }

  if (!token) {
    mountBadge('unknown');
    return;
  }

  fetch(origin + '/v1/verify?token=' + encodeURIComponent(token), { mode: 'cors' })
    .then(function(r){ return r.json(); })
    .then(function(d){
      var state = d && d.status ? d.status : 'unknown';
      // Normalize to known class names
      if (['verified','pending','revoked','unregistered','unknown','inactive'].indexOf(state) === -1) {
        state = 'unknown';
      }
      mountBadge(state);
    })
    .catch(function(){
      mountBadge('unknown');
    });
})();
