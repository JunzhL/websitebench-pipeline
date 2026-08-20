(function () {
  var _user_id = null;
  var _session_id = getCookie('SC_session');

  if (!_session_id) {
    _session_id = setCookie('SC_session');
  }

  var _sift = (window._sift = window._sift || []);
  _sift.push(['_setAccount', siftBeaconKey]);
  _sift.push(['_setUserId', _user_id]);
  _sift.push(['_setSessionId', _session_id]);
  _sift.push(['_trackPageview']);

  (function () {
    function ls() {
      var e = document.createElement('script');
      e.src = 'https://cdn.sift.com/s.js';
      document.body.appendChild(e);
    }

    if (window.attachEvent) {
      window.attachEvent('onload', ls);
    } else {
      window.addEventListener('load', ls, false);
    }
  })();

  function getCookie(name) {
    var value = '; ' + document.cookie;
    var parts = value.split('; ' + name + '=');
    if (parts.length === 2) return parts.pop().split(';').shift();
  }

  function setCookie(name) {
    var d = new Date();
    d.setTime(d.getTime() + 30 * 24 * 60 * 60 * 1000);
    var expires = 'expires=' + d.toUTCString();
    var rand = Math.floor(Math.random() * 4096);
    var cvalue = rand + new Date().getTime().toString(16);
    var hostName = window.location.hostname;
    var domain = hostName.substring(hostName.lastIndexOf('.', hostName.lastIndexOf('.') - 1) + 1);
    document.cookie = name + '=' + cvalue + ';' + expires + ';path=/' + ';domain=' + domain;
    return cvalue;
  }
})();
