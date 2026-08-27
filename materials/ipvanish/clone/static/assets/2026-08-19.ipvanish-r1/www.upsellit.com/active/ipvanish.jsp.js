Array.prototype.filter||(Array.prototype.filter=function(t,e){"use strict";if("Function"!=typeof t&&"function"!=typeof t||!this)throw new TypeError;var r=this.length>>>0,o=new Array(r),n=this,l=0,i=-1;if(void 0===e)for(;++i!==r;)i in this&&t(n[i],i,n)&&(o[l++]=n[i]);else for(;++i!==r;)i in this&&t.call(e,n[i],i,n)&&(o[l++]=n[i]);return o.length=l,o}),Array.prototype.forEach||(Array.prototype.forEach=function(t){var e,r;if(null==this)throw new TypeError('"this" is null or not defined');var o=Object(this),n=o.length>>>0;if("function"!=typeof t)throw new TypeError(t+" is not a function");for(arguments.length>1&&(e=arguments[1]),r=0;r<n;){var l;r in o&&(l=o[r],t.call(e,l,r,o)),r++}}),window.NodeList&&!NodeList.prototype.forEach&&(NodeList.prototype.forEach=Array.prototype.forEach),Array.prototype.indexOf||(Array.prototype.indexOf=function(t,e){var r;if(null==this)throw new TypeError('"this" is null or not defined');var o=Object(this),n=o.length>>>0;if(0===n)return-1;var l=0|e;if(l>=n)return-1;for(r=Math.max(l>=0?l:n-Math.abs(l),0);r<n;){if(r in o&&o[r]===t)return r;r++}return-1}),document.getElementsByClassName||(document.getElementsByClassName=function(t){var e,r,o,n=document,l=[];if(n.querySelectorAll)return n.querySelectorAll("."+t);if(n.evaluate)for(r=".//*[contains(concat(' ', @class, ' '), ' "+t+" ')]",e=n.evaluate(r,n,null,0,null);o=e.iterateNext();)l.push(o);else for(e=n.getElementsByTagName("*"),r=new RegExp("(^|\\s)"+t+"(\\s|$)"),o=0;o<e.length;o++)r.test(e[o].className)&&l.push(e[o]);return l}),document.querySelectorAll||(document.querySelectorAll=function(t){var e,r=document.createElement("style"),o=[];for(document.documentElement.firstChild.appendChild(r),document._qsa=[],r.styleSheet.cssText=t+"{x-qsa:expression(document._qsa && document._qsa.push(this))}",window.scrollBy(0,0),r.parentNode.removeChild(r);document._qsa.length;)(e=document._qsa.shift()).style.removeAttribute("x-qsa"),o.push(e);return document._qsa=null,o}),document.querySelector||(document.querySelector=function(t){var e=document.querySelectorAll(t);return e.length?e[0]:null}),Object.keys||(Object.keys=function(){"use strict";var t=Object.prototype.hasOwnProperty,e=!{toString:null}.propertyIsEnumerable("toString"),r=["toString","toLocaleString","valueOf","hasOwnProperty","isPrototypeOf","propertyIsEnumerable","constructor"],o=r.length;return function(n){if("function"!=typeof n&&("object"!=typeof n||null===n))throw new TypeError("Object.keys called on non-object");var l,i,s=[];for(l in n)t.call(n,l)&&s.push(l);if(e)for(i=0;i<o;i++)t.call(n,r[i])&&s.push(r[i]);return s}}()),"function"!=typeof String.prototype.trim&&(String.prototype.trim=function(){return this.replace(/^\s+|\s+$/g,"")}),String.prototype.replaceAll||(String.prototype.replaceAll=function(t,e){return"[object regexp]"===Object.prototype.toString.call(t).toLowerCase()?this.replace(t,e):this.replace(new RegExp(t,"g"),e)}),window.hasOwnProperty=window.hasOwnProperty||Object.prototype.hasOwnProperty;
if (typeof usi_commons === 'undefined') {
	usi_commons={logs:[],log:function(e){if(usi_commons.debug)try{usi_commons.logs.push(e),e instanceof Error?console.log(e.name+": "+e.message):console.log.apply(console,arguments)}catch(r){usi_commons.report_error_no_console(r)}},log_error:function(e){if(usi_commons.debug)try{e instanceof Error?console.log("%c USI Error:",usi_commons.log_styles.error,e.name+": "+e.message):console.log("%c USI Error:",usi_commons.log_styles.error,e)}catch(r){usi_commons.report_error_no_console(r)}},log_success:function(e){if(usi_commons.debug)try{console.log("%c USI Success:",usi_commons.log_styles.success,e)}catch(r){usi_commons.report_error_no_console(r)}},dir:function(e){if(usi_commons.debug)try{console.dir(e)}catch(r){usi_commons.report_error_no_console(r)}},log_styles:{error:"color: red; font-weight: bold;",success:"color: green; font-weight: bold;"},is_mobile:/iphone|ipod|ipad|android|blackberry|mobi/i.test(navigator.userAgent.toLowerCase()),device:/iphone|ipod|ipad|android|blackberry|mobi/i.test(navigator.userAgent.toLowerCase())?"mobile":"desktop",gup:function(e){try{e=e.replace(/[\[]/,"\\[").replace(/[\]]/,"\\]");var r="[\\?&]"+e+"=([^&#\\?]*)",t=RegExp(r).exec(window.location.href);if(null==t)return"";return t[1]}catch(i){usi_commons.report_error(i)}},load_script:function(e,r,t){try{0==e.indexOf("//")&&(e="https:"+e),(-1!=e.indexOf("/pixel.jsp")||-1!=e.indexOf("/blank.jsp")||-1!=e.indexOf("/customer_ip.jsp"))&&(e=e.replace(usi_commons.cdn,usi_commons.domain));var i=document.getElementsByTagName("head")[0],o=document.createElement("script");o.type="text/javascript";var n="";t||-1!=e.indexOf("/active/")||-1!=e.indexOf("_pixel.jsp")||-1!=e.indexOf("_throttle.jsp")||-1!=e.indexOf("metro")||-1!=e.indexOf("_suppress")||-1!=e.indexOf("product_recommendations")||-1!=e.indexOf("_pid.jsp")||-1!=e.indexOf("_zips")||(n=-1==e.indexOf("?")?"?":"&",-1!=e.indexOf("pv2.js")&&(n="%7C"),n+="si="+usi_commons.get_sess()),o.src=e+n,"function"==typeof r&&(o.onload=function(){try{r()}catch(e){usi_commons.report_error(e)}}),i.appendChild(o)}catch(s){usi_commons.report_error(s)}},fetch:function(e,r,t){try{t=t||{},0===e.indexOf("//")&&(e="https:"+e);var i=e.replace(usi_commons.cdn,usi_commons.domain),o="";if(-1!==i.indexOf("?")){var n=i.split("?");i=n[0],n.length>1&&(o=n[1])}var s={method:"POST",...t};return""!==o&&(s.body=new URLSearchParams(o)),fetch(i,s).then(e=>{if(!e.ok)throw Error(`HTTP error! status: `);return e.json()}).then(e=>{"function"==typeof r&&r(e)}).catch(e=>{usi_commons.report_error(e)})}catch(a){usi_commons.report_error(a)}},load_view:function(e,r,t,i){try{if("undefined"!=typeof usi_force||-1!=location.href.indexOf("usi_force")||null==usi_cookies.get("usi_sale")&&null==usi_cookies.get("usi_launched")&&null==usi_cookies.get("usi_launched"+r)){t=t||"";var o="";""!=usi_commons.gup("usi_force_date")?o="&usi_force_date="+usi_commons.gup("usi_force_date"):"undefined"!=typeof usi_cookies&&null!=usi_cookies.get("usi_force_date")&&(o="&usi_force_date="+usi_cookies.get("usi_force_date")),usi_commons.debug&&(o+="&usi_referrer="+encodeURIComponent(location.href)),0==t.indexOf("configID:")&&(o+="&configurationID="+encodeURIComponent(t.split("configID:")[1])),"undefined"!=typeof usi_cookies&&(null!=usi_cookies.get("usi_enable")&&(o+="&usi_enable=1"),null!=usi_cookies.get("usi_qa")&&(o+="&usi_qa=true"));var n=usi_commons.domain+"/view.jsp?hash="+e+"&siteID="+r+"&keys="+t+o;if(void 0!==usi_commons.last_view&&usi_commons.last_view==r+"_"+t)return;usi_commons.last_view=r+"_"+t,"undefined"!=typeof usi_js&&"function"==typeof usi_js.cleanup&&usi_js.cleanup(),usi_commons.load_script(n,i)}}catch(s){usi_commons.report_error(s)}},load_back_track:function(){try{if(usi_cookies.get("usi_back_clicked")){var e=usi_cookies.get("usi_back_clicked").split("_");if(3===e.length)return usi_commons.load_view(e[0],e[1],"configID:"+e[2]),!0}}catch(r){usi_commons.report_error(r)}return!1},remove_loads:function(){try{if(null!=document.getElementById("usi_obj")&&document.getElementById("usi_obj").parentNode.parentNode.removeChild(document.getElementById("usi_obj").parentNode),void 0!==usi_commons.usi_loads)for(var e in usi_commons.usi_loads)null!=document.getElementById("usi_"+e)&&document.getElementById("usi_"+e).parentNode.parentNode.removeChild(document.getElementById("usi_"+e).parentNode)}catch(r){usi_commons.report_error(r)}},load:function(e,r,t,i){try{if(void 0!==window["usi_"+r])return!1;t=t||"";var o="";""!=usi_commons.gup("usi_force_date")?o="&usi_force_date="+usi_commons.gup("usi_force_date"):"undefined"!=typeof usi_cookies&&null!=usi_cookies.get("usi_force_date")&&(o="&usi_force_date="+usi_cookies.get("usi_force_date")),usi_commons.debug&&(o+="&usi_referrer="+encodeURIComponent(location.href)),"undefined"!=typeof usi_cookies&&(null!=usi_cookies.get("usi_enable")&&(o+="&usi_enable=1"),null!=usi_cookies.get("usi_qa")&&(o+="&usi_qa=true"));var n=usi_commons.domain+"/usi_load.jsp?hash="+e+"&siteID="+r+"&keys="+t+o;usi_commons.load_script(n,i),void 0===usi_commons.usi_loads&&(usi_commons.usi_loads={}),usi_commons.usi_loads[r]=r}catch(s){usi_commons.report_error(s)}},load_precapture:function(e,r,t){try{if(void 0!==usi_commons.last_precapture_siteID&&usi_commons.last_precapture_siteID==r)return;usi_commons.last_precapture_siteID=r;var i="";"undefined"!=typeof usi_cookies&&null!=usi_cookies.get("usi_enable")&&(i+="&usi_enable=1");var o=usi_commons.domain+"/hound/monitor.jsp?qs="+e+"&siteID="+r+i;usi_commons.load_script(o,t)}catch(n){usi_commons.report_error(n)}},load_mail:function(e,r,t){try{var i=usi_commons.domain+"/mail.jsp?qs="+e+"&siteID="+r+"&domain="+encodeURIComponent(usi_commons.domain);usi_commons.load_script(i,t)}catch(o){usi_commons.report_error(o)}},load_products:function(e){try{if(!e.siteID||!e.pid)return;var r="";["siteID","association_siteID","pid","less_expensive","rows","days_back","force_exact","match","nomatch","name_from","image_from","price_from","url_from","extra_from","extra_merge","custom_callback","allow_dupe_names","expire_seconds","name","ordersID","cartsID","viewsID","companyID","order_by"].forEach(function(t,i){e[t]&&(r+=(0==i?"?":"&")+t+"="+e[t])}),e.filters&&(r+="&filters="+encodeURIComponent(e.filters.map(function(e){return encodeURIComponent(e)}).join("&"))),usi_commons.load_script(usi_commons.cdn+"/utility/product_recommendations_filter_v3.jsp"+r,function(){if("function"==typeof e.callback){var r="string"==typeof e.name?e.name.replace("usi_app."):"product_rec";e.callback("object"==typeof usi_app&&usi_app[r]?usi_app[r]:{})}})}catch(t){usi_commons.report_error(t)}},send_prod_rec:function(e,r,t){var i=!1;try{if(document.getElementsByTagName("html").length>0&&null!=document.getElementsByTagName("html")[0].className&&-1!=document.getElementsByTagName("html")[0].className.indexOf("translated"))return!1;var o=[e,r.name,r.link,r.pid,r.price,r.image];if(-1==o.indexOf(void 0)){var n=[e,r.name.replace(/\|/g,"&#124;"),r.link,r.pid,r.price,r.image].join("|")+"|";r.extra&&(n+=r.extra.replace(/\|/g,"&#124;")+"|"),usi_commons.load_script(usi_commons.domain+"/utility/pv2."+(t?"jsp":"js")+"?"+encodeURIComponent(n)),i=!0}}catch(s){usi_commons.report_error(s),i=!1}return i},report_error:function(e){if(null!=e&&("string"==typeof e&&(e=Error(e)),e instanceof Error)){if(void 0===usi_commons.error_reported){if(usi_commons.error_reported=!0,-1!==location.href.indexOf("usishowerrors"))throw e;usi_commons.load_script(usi_commons.domain+"/err.jsp?oops="+encodeURIComponent(e.message)+"-"+encodeURIComponent(e.stack)+"&url="+encodeURIComponent(location.href)),usi_commons.log_error(e.message),usi_commons.dir(e)}}},report_error_no_console:function(e){if(null!=e&&("string"==typeof e&&(e=Error(e)),e instanceof Error)){if(void 0===usi_commons.error_reported){if(usi_commons.error_reported=!0,-1!==location.href.indexOf("usishowerrors"))throw e;usi_commons.load_script(usi_commons.domain+"/err.jsp?oops="+encodeURIComponent(e.message)+"-"+encodeURIComponent(e.stack)+"&url="+encodeURIComponent(location.href))}}},gup_or_get_cookie:function(e,r,t){try{if("undefined"==typeof usi_cookies){usi_commons.log_error("usi_cookies is not defined");return}r=r||usi_cookies.expire_time.day,"usi_enable"==e&&(r=usi_cookies.expire_time.hour);var i=null,o=usi_commons.gup(e);return""!==o?(i=o,usi_cookies.set(e,i,r,t)):i=usi_cookies.get(e),i||""}catch(n){usi_commons.report_error(n)}},get_sess:function(){var e=null;if("undefined"==typeof usi_cookies)return"";try{if(null==usi_cookies.get("usi_si")){var r=Math.random().toString(36).substring(2);return r.length>6&&(r=r.substring(0,6)),e=r+"_"+Math.round(new Date().getTime()/1e3),usi_cookies.set("usi_si",e,86400),e}null!=usi_cookies.get("usi_si")&&(e=usi_cookies.get("usi_si")),usi_cookies.set("usi_si",e,86400)}catch(t){usi_commons.report_error(t)}return e},get_id:function(e){e||(e="");var r=null;try{if(null==usi_cookies.get("usi_v")&&null==usi_cookies.get("usi_id"+e)){var t=Math.random().toString(36).substring(2);return t.length>6&&(t=t.substring(0,6)),r=t+"_"+Math.round(new Date().getTime()/1e3),usi_cookies.set("usi_id"+e,r,2592e3,!0),r}null!=usi_cookies.get("usi_v")&&(r=usi_cookies.get("usi_v")),null!=usi_cookies.get("usi_id"+e)&&(r=usi_cookies.get("usi_id"+e)),usi_cookies.set("usi_id"+e,r,2592e3,!0)}catch(i){usi_commons.report_error(i)}return r},load_session_data:function(e){try{null==usi_cookies.get_json("usi_session_data")?usi_commons.load_script(usi_commons.domain+"/utility/session_data.jsp?extended="+(e?"true":"false")):(usi_app.session_data=usi_cookies.get_json("usi_session_data"),void 0!==usi_app.session_data_callback&&usi_app.session_data_callback())}catch(r){usi_commons.report_error(r)}},customer_ip:function(e){try{-1!=e?usi_cookies.set("usi_suppress","1",usi_cookies.expire_time.never):usi_app.main()}catch(r){usi_commons.report_error(r)}},customer_check:function(e){try{if(!usi_app.is_enabled&&!usi_cookies.value_exists("usi_ip_checked"))return usi_cookies.set("usi_ip_checked","1",usi_cookies.expire_time.day),usi_commons.load_script(usi_commons.domain+"/utility/customer_ip2.jsp?companyID="+e),!1;return!0}catch(r){usi_commons.report_error(r)}}};
	usi_commons.domain = "https://app.upsellit.com";
	usi_commons.cdn = "https://www.upsellit.com";
	usi_commons.debug = false;
	if (location.href.indexOf("usidebug") != -1 || location.href.indexOf("usi_debug") != -1) {
		usi_commons.debug = true;
	}
	setTimeout(function() {
		try {
			if (usi_commons.gup_or_get_cookie("usi_debug") != "") usi_commons.debug = true;
			if (usi_commons.gup_or_get_cookie("usi_qa") != "") {
				usi_commons.domain = usi_commons.cdn = "https://prod.upsellit.com";
			}
		} catch(err) {
			usi_commons.report_error(err);
		}
	}, 1000);
}

usi_cookieless = "1";
if (typeof(usi_app) == "undefined") {
    if("undefined"==typeof usi_cookies){if(usi_cookies={expire_time:{minute:60,hour:3600,two_hours:7200,four_hours:14400,day:86400,week:604800,two_weeks:1209600,month:2592e3,year:31536e3,never:31536e4},max_cookies_count:15,max_cookie_length:1e3,update_window_name:function(e,r,t){try{var i=-1;if(-1!=t){var o=new Date;o.setTime(o.getTime()+1e3*t),i=o.getTime()}var n=window.top||window,a=0;null!=r&&-1!=r.indexOf("=")&&(r=r.replace(RegExp("=","g"),"USIEQLS")),null!=r&&-1!=r.indexOf(";")&&(r=r.replace(RegExp(";","g"),"USIPRNS"));for(var c=n.name.split(";"),u="",l=0;l<c.length;l++){var s=c[l].split("=");3==s.length?(s[0]==e&&(s[1]=r,s[2]=i,a=1),null!=s[1]&&"null"!=s[1]&&(u+=s[0]+"="+s[1]+"="+s[2]+";")):""!=c[l]&&(u+=c[l]+";")}0==a&&(u+=e+"="+r+"="+i+";"),n.name=u}catch(f){}},flush_window_name:function(e){try{for(var r=window.top||window,t=r.name.split(";"),i="",o=0;o<t.length;o++){var n=t[o].split("=");3==n.length&&(0==n[0].indexOf(e)||(i+=t[o]+";"))}r.name=i}catch(a){}},get_from_window_name:function(e){try{for(var r,t,i=(window.top||window).name.split(";"),o=0;o<i.length;o++){var n=i[o].split("=");if(3==n.length){if(n[0]==e&&(t=n[1],-1!=t.indexOf("USIEQLS")&&(t=t.replace(/USIEQLS/g,"=")),-1!=t.indexOf("USIPRNS")&&(t=t.replace(/USIPRNS/g,";")),!("-1"!=n[2]&&0>usi_cookies.datediff(n[2]))))return r=[t,n[2]]}else if(2==n.length&&n[0]==e)return t=n[1],-1!=t.indexOf("USIEQLS")&&(t=t.replace(/USIEQLS/g,"=")),-1!=t.indexOf("USIPRNS")&&(t=t.replace(/USIPRNS/g,";")),r=[t,new Date().getTime()+6048e5]}}catch(a){}return null},datediff:function(e){return e-new Date().getTime()},count_cookies:function(e){return e=e||"usi_",usi_cookies.search_cookies(e).length},root_domain:function(){try{var e=document.domain.split("."),r=e[e.length-1];if("com"==r||"net"==r||"org"==r||"us"==r||"co"==r||"ca"==r)return e[e.length-2]+"."+e[e.length-1]}catch(t){}return 0==document.domain.indexOf("www.")?document.domain.replace("www.",""):document.domain},create_cookie:function(e,r,t){if(!1!==navigator.cookieEnabled&&void 0===window.usi_nocookies){var i="";if(-1!=t){var o=new Date;o.setTime(o.getTime()+1e3*t),i="; expires="+o.toGMTString()}var n="samesite=none;";0==location.href.indexOf("https://")&&(n+="secure;");var a=usi_cookies.root_domain();"undefined"!=typeof usi_parent_domain&&-1!=document.domain.indexOf(usi_parent_domain)&&(a=usi_parent_domain),document.cookie=e+"="+encodeURIComponent(r)+i+"; path=/;domain="+a+"; "+n}},create_nonencoded_cookie:function(e,r,t,i){if(!1!==navigator.cookieEnabled&&void 0===window.usi_nocookies){var o="";if(-1!=t){var n=new Date;n.setTime(n.getTime()+1e3*t),o="; expires="+n.toGMTString()}var a="samesite=none;";0==location.href.indexOf("https://")&&(a+="secure;");var c=usi_cookies.root_domain();document.cookie=e+"="+r+o+"; path=/;domain="+c+"; "+a,i||(document.cookie=e+"="+r+o+"; path=/;domain="+location.host+"; "+a,document.cookie=e+"="+r+o+"; path=/;domain=; "+a)}},read_cookie:function(e){if(!1===navigator.cookieEnabled)return null;var r=e+"=",t=[];try{t=document.cookie.split(";")}catch(i){}for(var o=0;o<t.length;o++){for(var n=t[o];" "==n.charAt(0);)n=n.substring(1,n.length);if(0==n.indexOf(r))return decodeURIComponent(n.substring(r.length,n.length))}return null},del:function(e){usi_cookies.set(e,null,-100);try{null!=localStorage&&localStorage.removeItem(e),null!=sessionStorage&&sessionStorage.removeItem(e)}catch(r){}},get_ls:function(e){try{var r=localStorage.getItem(e);if(null!=r){if(0==r.indexOf("{")&&-1!=r.indexOf("usi_expires")){var t=JSON.parse(r);if(new Date().getTime()>t.usi_expires)return localStorage.removeItem(e),null;r=t.value}return decodeURIComponent(r)}}catch(i){}return null},get:function(e){var r=usi_cookies.read_cookie(e);if(null!=r)return r;try{if(null!=localStorage&&(r=usi_cookies.get_ls(e),null!=r))return r;if(null!=sessionStorage&&(r=sessionStorage.getItem(e),void 0===r&&(r=null),null!=r))return decodeURIComponent(r)}catch(t){}var i=usi_cookies.get_from_window_name(e);if(null!=i&&i.length>1)try{r=decodeURIComponent(i[0])}catch(o){return i[0]}return r},get_json:function(e){var r=null,t=usi_cookies.get(e);if(null==t)return null;try{r=JSON.parse(t)}catch(i){t=t.replace(/\\"/g,'"');try{r=JSON.parse(JSON.parse(t))}catch(o){try{r=JSON.parse(t)}catch(n){}}}return r},search_cookies:function(e){e=e||"";var r=[];return document.cookie.split(";").forEach(function(t){var i=t.split("=")[0].trim();(""===e||0===i.indexOf(e))&&r.push(i)}),r},set:function(e,r,t,i){"undefined"!=typeof usi_nevercookie&&!0==usi_nevercookie&&(i=!1),void 0===t&&(t=-1);try{r=r.replace(/(\r\n|\n|\r)/gm,"")}catch(o){}"undefined"==typeof usi_windownameless&&(null==r||r.length<1e3)&&usi_cookies.update_window_name(e+"",r+"",t);try{if(t>0&&null!=localStorage){var n=new Date,a={value:r,usi_expires:n.getTime()+1e3*t};localStorage.setItem(e,JSON.stringify(a))}else null!=sessionStorage&&sessionStorage.setItem(e,r)}catch(c){}if(i||null==r){if(null!=r){if(null==usi_cookies.read_cookie(e)&&!i&&usi_cookies.search_cookies("usi_").length+1>usi_cookies.max_cookies_count){usi_cookies.report_error('Set cookie "'+e+'" failed. Max cookies count is '+usi_cookies.max_cookies_count);return}if(r.length>usi_cookies.max_cookie_length){usi_cookies.report_error('Cookie "'+e+'" truncated ('+r.length+"). Max single-cookie length is "+usi_cookies.max_cookie_length);return}}usi_cookies.create_cookie(e,r,t)}},set_json:function(e,r,t,i){var o=JSON.stringify(r).replace(/^"/,"").replace(/"$/,"");usi_cookies.set(e,o,t,i)},flush:function(e){e=e||"usi_";var r,t,i,o=document.cookie.split(";");for(r=0;r<o.length;r++)0==(t=o[r]).trim().toLowerCase().indexOf(e)&&(i=t.trim().split("=")[0],usi_cookies.del(i));usi_cookies.flush_window_name(e);try{if(null!=localStorage)for(var n in localStorage)0==n.indexOf(e)&&localStorage.removeItem(n);if(null!=sessionStorage)for(var n in sessionStorage)0==n.indexOf(e)&&sessionStorage.removeItem(n)}catch(a){}},print:function(){for(var e=document.cookie.split(";"),r="",t="",i=0;i<e.length;i++){var o=e[i];0==o.trim().toLowerCase().indexOf("usi_")&&(console.log(decodeURIComponent(o.trim())+" (cookie)"),t+=decodeURIComponent(o.trim())+" (cookie), ",r+=","+o.trim().toLowerCase().split("=")[0]+",")}try{if(null!=localStorage)for(var n in localStorage)0==n.indexOf("usi_")&&"string"==typeof localStorage[n]&&-1==r.indexOf(","+n+",")&&(console.log(n+"="+usi_cookies.get_ls(n)+" (localStorage)"),t+=n+"="+usi_cookies.get_ls(n)+" (localStorage), ",r+=","+n+",");if(null!=sessionStorage)for(var n in sessionStorage)0==n.indexOf("usi_")&&"string"==typeof sessionStorage[n]&&-1==r.indexOf(","+n+",")&&(console.log(n+"="+sessionStorage[n]+" (sessionStorage)"),t+=n+"="+sessionStorage[n]+" (sessionStorage), ",r+=","+n+",")}catch(a){}for(var c=(window.top||window).name.split(";"),u=0;u<c.length;u++){var l=c[u].split("=");if(3==l.length&&0==l[0].indexOf("usi_")&&-1==r.indexOf(","+l[0]+",")){var s=l[1];-1!=s.indexOf("USIEQLS")&&(s=s.replace(/USIEQLS/g,"=")),-1!=s.indexOf("USIPRNS")&&(s=s.replace(/USIPRNS/g,";")),console.log(l[0]+"="+s+" (window.name)"),t+=l[0]+"="+s+" (window.name), ",r+=","+o.trim().toLowerCase().split("=")[0]+","}}return t},value_exists:function(){var e,r;for(e=0;e<arguments.length;e++)if(r=usi_cookies.get(arguments[e]),""===r||null===r||"null"===r||"undefined"===r)return!1;return!0},report_error:function(e){"undefined"!=typeof usi_commons&&"function"==typeof usi_commons.report_error&&usi_commons.report_error(e)},check_multi_domain:function(){try{"undefined"!=typeof usi_app&&usi_app.company_id?usi_cookies.get("usi_app.company_id")?usi_cookies.get("usi_app.company_id")!==usi_app.company_id&&(window.name=""):usi_cookies.set("usi_app.company_id",usi_app.company_id):setTimeout(function(){usi_cookies.check_multi_domain()},2e3)}catch(e){"undefined"!=typeof usi_commons&&usi_commons.report_error(e)}},monitor_page_views:function(){try{if(void 0===usi_cookies.last_url||usi_cookies.last_url!=location.href){usi_cookies.last_url=location.href;var e=window.self===window.top,r=-1!==location.href.indexOf("/checkouts/");e&&(usi_cookies.get("usi_entry_url_1")||usi_cookies.set("usi_entry_url_1",usi_cookies.last_url,21600),null==document.referrer||usi_cookies.get("usi_referrer_url")||-1!=document.referrer.indexOf(location.host)||usi_cookies.set("usi_referrer_url",document.referrer||"direct traffic",21600)),(e||r)&&(usi_cookies.get("usi_entry_url_1")&&usi_cookies.get("usi_entry_url_1")!=usi_cookies.last_url&&usi_cookies.set("usi_last_url_1",usi_cookies.last_url,21600),usi_cookies.set("usi_pv_count",String(Number(usi_cookies.get("usi_pv_count")||0)+1),21600))}setTimeout(usi_cookies.monitor_page_views,2e3)}catch(t){"undefined"!=typeof usi_commons&&usi_commons.report_error(t)}}},"undefined"!=typeof usi_commons&&"function"==typeof usi_commons.gup&&"function"==typeof usi_commons.gup_or_get_cookie)try{usi_commons.force_date=usi_commons.gup_or_get_cookie("usi_force_date"),usi_commons.force_group=usi_commons.gup_or_get_cookie("usi_force_group"),usi_commons.is_enabled=""!=usi_commons.gup_or_get_cookie("usi_enable",usi_cookies.expire_time.hour,!0),usi_commons.is_forced=""!=usi_commons.gup_or_get_cookie("usi_force",usi_cookies.expire_time.hour,!0),""!=usi_commons.gup("usi_email_id")?usi_cookies.set("usi_email_id",usi_commons.gup("usi_email_id").split(".")[0],Number(usi_commons.gup("usi_email_id").split(".")[1]),!0):null==usi_cookies.read_cookie("usi_email_id")&&null!=usi_cookies.get_from_window_name("usi_email_id")&&usi_cookies.set("usi_email_id",usi_cookies.get_from_window_name("usi_email_id")[0],(usi_cookies.get_from_window_name("usi_email_id")[1]-new Date().getTime())/1e3,!0),""!=usi_commons.gup_or_get_cookie("usi_debug")&&(usi_commons.debug=!0),""!=usi_commons.gup_or_get_cookie("usi_qa")&&(usi_commons.domain=usi_commons.cdn="https://prod.upsellit.com"),usi_cookies.monitor_page_views()}catch(e){usi_commons.report_error(e)}-1!=location.href.indexOf("usi_clearcookies")&&usi_cookies.flush(),usi_commons.objects=["product_rec","product","product_recs","abandon_recs","base_products","buypage_addons","campaign_56959","cart_items","cart_recs","cart_upsell_recs","cross_sell_products","discontinued_rec","filter_rec0","inpage_data","minicart_rec","minicart_recs","newproducts_data","oos_data","oos_rec","oos_rec_data","pdpbundler_recs","prod_27450","product_rec_cart","product_rec_minicart","product_rec_oos","rec_48323","rec_58915","rec_58917","rec_58921","rec_cart_items","recs","recs_34089","recs_51731","search_rec","toppicks","toppicks_customizations","topproducts_data","trade_up_products","variant_group_0","variant_group_1","variant_group_2","variant_group_3","variant_group_4","variant_group_5","variant_group_6","variant_group_7","variant_group_8","variant_group_9"],usi_commons.check_for_back_clicked=function(){try{if("undefined"!=typeof usi_app&&null!=usi_cookies.get("usi_back_clicked")&&window.self===window.top&&(void 0===usi_app.last_back_url||usi_app.last_back_url!=location.href)){usi_app.last_back_url=location.href,void 0!==usi_app.common_objects&&(usi_commons.objects=usi_commons.objects.concat(usi_app.common_objects)),usi_cookies.get("usi_record_rec_names")&&(usi_commons.objects=usi_commons.objects.concat(usi_cookies.get("usi_record_rec_names").split(",")));for(var e=0;e<usi_commons.objects.length;e++)null!=usi_cookies.get("usi_app_"+usi_commons.objects[e])&&(usi_app[usi_commons.objects[e]]=JSON.parse(usi_cookies.get("usi_app_"+usi_commons.objects[e])));var r=usi_cookies.get("usi_back_clicked").split("_");3===r.length&&usi_commons.load_view(r[0],r[1],"configID:"+r[2],function(){usi_js.cleanup=function(){}});return}setTimeout(usi_commons.check_for_back_clicked,1e3)}catch(t){usi_commons.report_error(t)}},setTimeout(usi_commons.check_for_back_clicked,10)}
'undefined'==typeof usi_url&&(usi_url={},usi_url.URL=function(a){a=a||location.href;var b=document.createElement('a');if(b.href=a,this.full=b.href||'',this.protocol=(b.protocol||'').split(':')[0],this.host=b.host||'',-1!=this.host.indexOf(':')&&(this.host=this.host.substring(0,this.host.indexOf(':'))),this.port=b.port||'',this.hash=b.hash||'',this.baseURL='',this.tld='',this.domain='',this.subdomain='',this.domain_tld='',''!==this.protocol&&''!==this.host){this.baseURL=this.protocol+'://'+this.host+'/';var c=this.host.split(/\./g);if(2<=c.length){if(-1<['co','com','org','net','int','edu','gov','mil'].indexOf(c[c.length-2])&&2===c[c.length-1].length){var d=c.pop(),e=c.pop();this.tld=e+'.'+d}else this.tld=c.pop()}0<c.length&&(this.domain=c.pop(),0<c.length&&(this.subdomain=c.join('.'))),this.domain_tld=this.domain+'.'+this.tld}var f=b.pathname||'';0!==f.indexOf('/')&&(f='/'+f),this.path=new usi_url.Path(f),this.params=new usi_url.Params((b.search||'').substr(1))},usi_url.URL.prototype.build=function(a,b,c){var d='';return''!==this.protocol&&''!==this.host&&(null==a&&(a=!0),null==b&&(b=!0),null==c&&(c=!0),!0==a&&(d+=this.protocol+':'),d+='//'+this.host,''!==this.port&&(d+=':'+this.port),!0==b&&(d+=this.path.full,!0==c&&0<Object.keys(this.params.parameters).length&&(d+='?',d+=this.params.build()))),d},usi_url.Path=function(a){a=a||'',this.full=a,this.directories=[],this.filename='';for(var b=a.substr(1).split(/\//g);0<b.length;)1===b.length?this.filename=b.shift():this.directories.push(b.shift());this.has_directory=function(a){return-1<this.directories.indexOf(a)},this.contains=function(a){return-1<this.full.indexOf(a)}},usi_url.Params=function(a){a=a||'',this.full=a,this.parameters=function(a){var b={};if(1===a.length&&''===a[0])return b;for(var c,d,e,f=0;f<a.length;f++)if(e=a[f].split('='),c=e[0]&&e[0].replace(/\+/g,' '),d=e[1]&&e[1].replace(/\+/g,' '),1===e.length)b[c]='';else try{b[c]=decodeURIComponent(d)}catch(a){b[c]=d}return b}(a.split('&')),this.count=Object.keys(this.parameters).length,this.get=function(a){return a in this.parameters?this.parameters[a]:null},this.has=function(a){return a in this.parameters},this.set=function(a,b){this.parameters[a]=b,this.count=Object.keys(this.parameters).length},this.remove=function(a){!0===this.has(a)&&delete this.parameters[a],this.count=Object.keys(this.parameters).length},this.build=function(){var a=this,b=[];for(var c in a.parameters)!0===a.parameters.hasOwnProperty(c)&&b.push(c+'='+encodeURIComponent(a.parameters[c]));return b.join('&')},this.remove_usi_params=function(a){var b=this;for(var c in a=a||[],-1===a.indexOf('usi_')&&a.push('usi_'),b.parameters)if(!0===b.parameters.hasOwnProperty(c)){var d=!1;a.forEach(function(a){0===c.indexOf(a)&&(d=!0)}),d&&b.remove(c)}},this.remove_all=function(){var a=this;for(var b in a.parameters)!0===a.parameters.hasOwnProperty(b)&&a.remove(b)}});
"undefined"==typeof usi_date&&((usi_date={}).add_hours=function(e,t){return!1===usi_date.is_date(e)?e:new Date(e.getTime()+36e5*t)},usi_date.add_minutes=function(e,t){return!1===usi_date.is_date(e)?e:new Date(e.getTime()+6e4*t)},usi_date.add_seconds=function(e,t){return!1===usi_date.is_date(e)?e:new Date(e.getTime()+1e3*t)},usi_date.is_date=function(e){return null!=e&&"object"==typeof e&&e instanceof Date==!0&&!1===isNaN(e.getTime())},usi_date.is_after=function(e){try{usi_date.check_format(e);var t=usi_date.set_date(),r=new Date(e);return t.getTime()>r.getTime()}catch(s){"undefined"!=typeof usi_commons&&"function"==typeof usi_commons.report_error&&usi_commons.report_error(s)}return!1},usi_date.is_before=function(e){try{usi_date.check_format(e);var t=usi_date.set_date(),r=new Date(e);return t.getTime()<r.getTime()}catch(s){"undefined"!=typeof usi_commons&&"function"==typeof usi_commons.report_error&&usi_commons.report_error(s)}return!1},usi_date.is_between=function(e,t){return usi_date.check_format(e,t),usi_date.is_after(e)&&usi_date.is_before(t)},usi_date.check_format=function(e,t){(-1!=e.indexOf(" ")||t&&-1!=t.indexOf(" "))&&"undefined"!=typeof usi_commons&&"function"==typeof usi_commons.report_error&&usi_commons.report_error("Incorrect format: Use YYYY-MM-DDThh:mm:ss")},usi_date.string_to_date=function(e,t){t=t||!1;var r=null,s=/^[0-2]?[0-9]\/[0-3]?[0-9]\/\d{4}(\s[0-2]?[0-9]\:[0-5]?[0-9](?:\:[0-5]?[0-9])?)?$/.exec(e),n=/^(\d{4}\-[0-2]?[0-9]\-[0-3]?[0-9])(\s[0-2]?[0-9]\:[0-5]?[0-9](?:\:[0-5]?[0-9])?)?$/.exec(e);if(2===(s||[]).length){if(r=new Date(e),""===(s[1]||"")&&!0===t){var a=new Date;r=usi_date.add_hours(r,a.getHours()),r=usi_date.add_minutes(r,a.getMinutes()),r=usi_date.add_seconds(r,a.getSeconds())}}else if(3===(n||[]).length){var c=n[1].split(/\-/g),i=c[1]+"/"+c[2]+"/"+c[0];return i+=n[2]||"",usi_date.string_to_date(i,t)}return r},usi_date.set_date=function(){var e=new Date,t=usi_commons.gup("usi_force_date");if(""!==t){t=decodeURIComponent(t);var r=usi_date.string_to_date(t,!0);null!=r?(e=r,usi_cookies.set("usi_force_date",t,usi_cookies.expire_time.hour),usi_commons.log("Date forced to: "+e)):usi_cookies.del("usi_force_date")}else e=null!=usi_cookies.get("usi_force_date")?usi_date.string_to_date(usi_cookies.get("usi_force_date"),!0):new Date;return e},usi_date.diff=function(e,t,r,s){null==s&&(s=1),""!=(r||"")&&(r=usi_date.get_units(r));var n=null;if(!0===usi_date.is_date(t)&&!0===usi_date.is_date(e))try{var a=Math.abs(t-e);switch(r){case"ms":n=a;break;case"seconds":n=usi_dom.to_decimal_places(parseFloat(a)/parseFloat(1e3),s);break;case"minutes":n=usi_dom.to_decimal_places(parseFloat(a)/parseFloat(1e3)/parseFloat(60),s);break;case"hours":n=usi_dom.to_decimal_places(parseFloat(a)/parseFloat(1e3)/parseFloat(60)/parseFloat(60),s);break;case"days":n=usi_dom.to_decimal_places(parseFloat(a)/parseFloat(1e3)/parseFloat(60)/parseFloat(60)/parseFloat(24),s)}}catch(c){n=null}return n},usi_date.get_units=function(e){var t="";switch(e.toLowerCase()){case"days":case"day":case"d":t="days";break;case"hours":case"hour":case"hrs":case"hr":case"h":t="hours";break;case"minutes":case"minute":case"mins":case"min":case"m":t="minutes";break;case"seconds":case"second":case"secs":case"sec":case"s":t="seconds";break;case"ms":case"milliseconds":case"millisecond":case"millis":case"milli":t="ms"}return t});
"undefined"==typeof usi_dom&&((usi_dom={}).get_elements=function(e,t){var n=[];return t=t||document,n=Array.prototype.slice.call(t.querySelectorAll(e))},usi_dom.get_first_element=function(e,t){if(""===(e||""))return null;if(t=t||document,"[object Array]"!==Object.prototype.toString.call(e))return t.querySelector(e);for(var n=null,r=0;r<e.length;r++){var i=e[r];if(null!=(n=usi_dom.get_first_element(i,t)))break}return n},usi_dom.get_element_text_no_children=function(e,t){var n="";if(null==t&&(t=!1),null!=(e=e||document)&&null!=e.childNodes)for(var r=0;r<e.childNodes.length;++r)3===e.childNodes[r].nodeType&&(n+=e.childNodes[r].textContent);return!0===t&&(n=usi_dom.clean_string(n)),n.trim()},usi_dom.clean_string=function(e){return"string"!=typeof e?void 0:(e=(e=(e=(e=(e=(e=(e=e.replace(/[\u2010-\u2015\u2043]/g,"-")).replace(/[\u2018-\u201B]/g,"'")).replace(/[\u201C-\u201F]/g,'"')).replace(/\u2024/g,".")).replace(/\u2025/g,"..")).replace(/\u2026/g,"...")).replace(/\u2044/g,"/")).replace(/[^\x20-\xFF\u0100-\u017F\u0180-\u024F\u20A0-\u20CF]/g,"").trim()},usi_dom.string_to_decimal=function(e){var t=null;if("string"==typeof e)try{var n=parseFloat(e.replace(/[^0-9\.-]+/g,""));!1===isNaN(n)&&(t=n)}catch(r){usi_commons.log("Error: "+r.message)}return t},usi_dom.string_to_integer=function(e){var t=null;if("string"==typeof e)try{var n=parseInt(e.replace(/[^0-9-]+/g,""));!1===isNaN(n)&&(t=n)}catch(r){usi_commons.log("Error: "+r.message)}return t},usi_dom.get_absolute_url=function(){var e;return function(t){return(e=e||document.createElement("a")).href=t,e.href}}(),usi_dom.format_currency=function(e,t,n){var r="";return isNaN(e)&&(e=usi_dom.currency_to_decimal(e)),!1===isNaN(e)&&("object"==typeof Intl&&"function"==typeof Intl.NumberFormat?(t=t||"en-US",n=n||{style:"currency",currency:"USD"},r=Number(e).toLocaleString(t,n)):r=e),r},usi_dom.currency_to_decimal=function(e){return 0==e.indexOf("&")&&-1!=e.indexOf(";")?e=e.substring(e.indexOf(";")+1):-1!=e.indexOf("&")&&-1!=e.indexOf(";")&&(e=e.substring(0,e.indexOf("&"))),isNaN(e)&&(e=e.replace(/[^0-9,.]/g,"")),e.indexOf(",")==e.length-3&&(-1!=e.indexOf(".")&&(e=e.replace(".","")),e=e.replace(",",".")),e=e.replace(/[^0-9.]/g,"")},usi_dom.to_decimal_places=function(e,t){if(null==e||"number"!=typeof e||null==t||"number"!=typeof t)return null;if(0==t)return parseFloat(Math.round(e));for(var n=10,r=1;r<t;r++)n*=10;return parseFloat(Math.round(e*n)/n)},usi_dom.trim_string=function(e,t,n){return n=n||"",(e=e||"").length>t&&(e=e.substring(0,t),""!==n&&(e+=n)),e},usi_dom.attach_event=function(e,t,n){var r=usi_dom.find_supported_element(e,n);usi_dom.detach_event(e,t,r),r.addEventListener?r.addEventListener(e,t,!1):r.attachEvent("on"+e,t)},usi_dom.detach_event=function(e,t,n){var r=usi_dom.find_supported_element(e,n);r.removeEventListener?r.removeEventListener(e,t,!1):r.detachEvent("on"+e,t)},usi_dom.find_supported_element=function(e,t){return(t=t||document)===window?window:!0===usi_dom.is_event_supported(e,t)?t:t===document?window:usi_dom.find_supported_element(e,document)},usi_dom.is_event_supported=function(e,t){return null!=t&&void 0!==t["on"+e]},usi_dom.is_defined=function(e,t){if(null==e||""===(t||""))return!1;var n=!0,r=e;return t.split(".").forEach(function(e){!0===n&&(null==r||"object"!=typeof r||!1===r.hasOwnProperty(e)?n=!1:r=r[e])}),n},usi_dom.ready=function(e){void 0!==document.readyState&&"complete"===document.readyState?e():window.addEventListener?window.addEventListener("load",e,!0):window.attachEvent?window.attachEvent("onload",e):setTimeout(e,5e3)},usi_dom.fit_text=function(e,t){t||(t={});var n={multiLine:!0,minFontSize:.1,maxFontSize:20,widthOnly:!1},r={};for(var i in n)t.hasOwnProperty(i)?r[i]=t[i]:r[i]=n[i];var l=Object.prototype.toString.call(e);function o(e,t){a=e.innerHTML,d=parseInt(window.getComputedStyle(e,null).getPropertyValue("font-size"),10),c=(n=e,r=window.getComputedStyle(n,null),(n.clientWidth-parseInt(r.getPropertyValue("padding-left"),10)-parseInt(r.getPropertyValue("padding-right"),10))/d),u=(i=e,l=window.getComputedStyle(i,null),(i.clientHeight-parseInt(l.getPropertyValue("padding-top"),10)-parseInt(l.getPropertyValue("padding-bottom"),10))/d),c&&(t.widthOnly||u)||(t.widthOnly?usi_commons.log("Set a static width on the target element "+e.outerHTML):usi_commons.log("Set a static height and width on the target element "+e.outerHTML)),-1===a.indexOf("textFitted")?((o=document.createElement("span")).className="textFitted",o.style.display="inline-block",o.innerHTML=a,e.innerHTML="",e.appendChild(o)):o=e.querySelector("span.textFitted"),t.multiLine||(e.style["white-space"]="nowrap"),f=t.minFontSize,s=t.maxFontSize;for(var n,r,i,l,o,u,a,c,d,f,p,s,$=f,g=1e3;f<=s&&g>0;)g--,p=s+f-.1,o.style.fontSize=p+"em",o.scrollWidth/d<=c&&(t.widthOnly||o.scrollHeight/d<=u)?($=p,f=p+.1):s=p-.1;o.style.fontSize!==$+"em"&&(o.style.fontSize=$+"em")}"[object Array]"!==l&&"[object NodeList]"!==l&&"[object HTMLCollection]"!==l&&(e=[e]);for(var u=0;u<e.length;u++)o(e[u],r)});
if (typeof usi_aff === 'undefined') {
	usi_aff = {
		fix_linkshare: function() {
			try {
				if (usi_commons.gup("ranSiteID") != "") {
					usi_aff.log_url();
					if (location.href.indexOf("usi_email_id") != -1 || usi_cookies.get("usi_clicked_1") != null) {
						usi_cookies.del("usi_clicked_1");
						var now = new Date();
						var date = now.getUTCFullYear() + ((now.getUTCMonth() + 1 < 10 ? "0" : "") + (now.getUTCMonth() + 1)) + ((now.getUTCDate() < 10 ? "0" : "") + now.getDate());
						var time = (now.getUTCHours() < 10 ? "0" : "") + now.getUTCHours() + ((now.getUTCMinutes() < 10 ? "0" : "") + now.getUTCMinutes());
						usi_cookies.create_nonencoded_cookie("usi_rmStore", "ald:" + date + "_" + time + "|atrv:" + usi_commons.gup("ranSiteID"), usi_cookies.expire_time.month);
					}
				}
				if (usi_cookies.read_cookie("usi_rmStore") != null) {
					usi_cookies.create_nonencoded_cookie("rmStore", usi_cookies.read_cookie("usi_rmStore"), usi_cookies.expire_time.month);
					localStorage.setItem('rmStore', '{"/":"' + usi_cookies.read_cookie("usi_rmStore") + '"}');
				}
			} catch (err) {
				usi_commons.report_error(err);
			}
		},
		fix_cj: function() {
			try {
				if (usi_commons.gup("cjevent") != "" || usi_commons.gup("CJEVENT") != "") {
					usi_aff.log_url();
					usi_cookies.del("cjUser");
					var cjevent = usi_commons.gup("cjevent");
					if (cjevent == "") {
						cjevent = usi_commons.gup("CJEVENT");
					}
					if (location.href.indexOf("usi_email_id") != -1 || usi_cookies.get("usi_clicked_1") != null) {
						usi_cookies.del("usi_clicked_1");
						usi_cookies.create_nonencoded_cookie("usi_cjevent", cjevent, usi_cookies.expire_time.month, true);
					}
				}
				if (usi_cookies.read_cookie("usi_cjevent") != null) {
					usi_cookies.create_nonencoded_cookie("cjevent", usi_cookies.read_cookie("usi_cjevent"), usi_cookies.expire_time.month, true);
					usi_cookies.create_nonencoded_cookie("cjevent_dc", usi_cookies.read_cookie("usi_cjevent"), usi_cookies.expire_time.month, true);
					usi_cookies.create_nonencoded_cookie("cje", usi_cookies.read_cookie("usi_cjevent"), usi_cookies.expire_time.month, true);
					localStorage.setItem("cjevent", usi_cookies.read_cookie("usi_cjevent"));
					sessionStorage.setItem("cjevent", usi_cookies.read_cookie("usi_cjevent"));
				}
			} catch (err) {
				usi_commons.report_error(err);
			}
		},
		fix_sas: function() {
			try {
				if (usi_commons.gup("sscid") != "") {
					usi_aff.load_script("https://www.upsellit.com/launch/blank.jsp?aff_click_sas=" + encodeURIComponent(location.href));
					//usi_aff.log_url();
					if (location.href.indexOf("usi_email_id") != -1 || usi_cookies.get("usi_clicked_1") != null) {
						usi_cookies.del("usi_clicked_1");
						usi_cookies.create_nonencoded_cookie("usi_sscid", usi_commons.gup("sscid"), usi_cookies.expire_time.month);
					}
				}
				if (usi_cookies.read_cookie("usi_sscid") != null) {
					usi_cookies.create_nonencoded_cookie("sas_m_awin", "{\"clickId\":\"" + usi_cookies.read_cookie("usi_sscid")+ "\"}", usi_cookies.expire_time.month);
				}
			} catch (err) {
				usi_commons.report_error(err);
			}
		},
		fix_awin: function(id) {
			try {
				if (usi_commons.gup("awc") != "") {
					usi_aff.log_url();
					if (location.href.indexOf("usi_email_id") != -1 || usi_cookies.get("usi_clicked_1") != null) {
						usi_cookies.del("usi_clicked_1");
						usi_cookies.create_nonencoded_cookie("usi_awc", usi_commons.gup("awc"), usi_cookies.expire_time.month);
						usi_cookies.del("_aw_j_"+id);
					}
				}
				if (usi_cookies.read_cookie("usi_awc") != null) {
					usi_cookies.del("_aw_j_"+id);
					usi_cookies.create_nonencoded_cookie("AwinChannelCookie","aw",30*24*60*60,true);
					usi_cookies.create_nonencoded_cookie("AwinCookie","aw",30*24*60*60,true);
					usi_cookies.create_nonencoded_cookie("awin_source","aw",30*24*60*60,true);
					usi_cookies.create_nonencoded_cookie("_aw_m_"+id, usi_cookies.read_cookie("usi_awc"), usi_cookies.expire_time.month);
					usi_cookies.create_nonencoded_cookie("awc", usi_cookies.read_cookie("usi_awc"), usi_cookies.expire_time.month);
					if (typeof(AWIN) !== "undefined" && typeof(AWIN.Tracking) !== "undefined" && typeof(AWIN.Tracking.StorageProvider) !== "undefined") {
						AWIN.Tracking.StorageProvider.setAWC(id, usi_cookies.read_cookie("usi_awc"));
					}
				}
			} catch (err) {
				usi_commons.report_error(err);
			}
		},
		fix_pj: function() {
			try {
				if (usi_commons.gup("clickId") != "") {
					usi_aff.log_url();
					if (location.href.indexOf("usi_email_id") != -1 || usi_cookies.get("usi_clicked_1") != null) {
						usi_cookies.del("usi_clicked_1");
						var now = new Date();
						var usi_days = Math.floor(now / 8.64e7);
						usi_cookies.create_nonencoded_cookie('usi-pjn-click', '[{"id":"' + usi_commons.gup("clickId") + '","days":' + usi_days + ',"type":"p"}]', usi_cookies.expire_time.month);
					}
				}
				if (usi_cookies.read_cookie("usi-pjn-click") != null) {
					usi_cookies.create_nonencoded_cookie("pjn-click", usi_cookies.read_cookie("usi-pjn-click"), usi_cookies.expire_time.month);
					localStorage.setItem("pjnClickData", usi_cookies.read_cookie("usi-pjn-click"));
				}
			} catch (err) {
				usi_commons.report_error(err);
			}
		},
		fix_ir: function(id) {
			try {
				if (usi_commons.gup("irclickid") != "" || usi_commons.gup("clickid") != "") {
					usi_aff.log_url();
					if (location.href.indexOf("usi_email_id") != -1 || usi_cookies.get("usi_clicked_1") != null) {
						usi_cookies.del("usi_clicked_1");
						var usi_click = usi_commons.gup("irclickid");
						if (usi_click == "") {
							usi_click = usi_commons.gup("clickid");
						}
						var date_now = Date.now().toString();
						var cookie_value = date_now + "|-1|" + date_now + "|" + usi_click + "|";
						usi_cookies.create_nonencoded_cookie("usi_IR_" + id, cookie_value, usi_cookies.expire_time.month);
					}
				}
				if (usi_cookies.read_cookie("usi_IR_" + id) != null) {
					usi_cookies.create_nonencoded_cookie("IR_" + id, usi_cookies.read_cookie("usi_IR_" + id), usi_cookies.expire_time.month);
					usi_cookies.create_nonencoded_cookie("irclickid", usi_cookies.read_cookie("usi_IR_" + id).split("|")[3], usi_cookies.expire_time.month);
				}
			} catch (err) {
				usi_commons.report_error(err);
			}
		},
		fix_cf: function() {
			try {
				if (usi_commons.gup("cfclick") != "") {
					usi_aff.log_url();
					if (location.href.indexOf("usi_email_id") != -1 || usi_cookies.get("usi_clicked_1") != null) {
						usi_cookies.del("usi_clicked_1");
						usi_cookies.create_nonencoded_cookie("usi-cfjump-click", usi_commons.gup("cfclick"), usi_cookies.expire_time.month);
					}
				}
				if (usi_cookies.read_cookie("usi-cfjump-click") != null) {
					usi_cookies.create_nonencoded_cookie("cfjump-click", usi_cookies.read_cookie("usi-cfjump-click"), usi_cookies.expire_time.month);
					usi_cookies.create_nonencoded_cookie("cfclick", usi_cookies.read_cookie("usi-cfjump-click"), usi_cookies.expire_time.month);
				}
			} catch (err) {
				usi_commons.report_error(err);
			}
		},
		fix_avantlink:function() {
			try {
				if (usi_commons.gup("avad") != "") {
					usi_aff.log_url();
					if (location.href.indexOf("usi_email_id") != -1 || usi_cookies.get("usi_clicked_1") != null) {
						usi_cookies.del("usi_clicked_1");
						usi_cookies.create_nonencoded_cookie("usi_avad", usi_commons.gup("avad"), usi_cookies.expire_time.month);
						usi_aff.wait_for_avmws = function() {
							if (usi_cookies.get("avmws") != null) {
								usi_cookies.create_nonencoded_cookie("usi_avmws", usi_cookies.get("avmws"), usi_cookies.expire_time.month);
							} else {
								setTimeout(usi_aff.wait_for_avmws, 1000);
							}
						};
						usi_aff.wait_for_avmws();
					}
				}
				if (usi_cookies.read_cookie("usi_avmws") != null) {
					usi_cookies.create_nonencoded_cookie("avmws", usi_cookies.read_cookie("usi_avmws"), usi_cookies.expire_time.month);
				}
			} catch (err) {
				usi_commons.report_error(err);
			}
		},
		get_impact_pixel: function () {
			var pixel = "";
			try {
				var scripts = document.getElementsByTagName("script");
				for (var i = 0; i < scripts.length; i++) {
					var text = scripts[i].innerText;
					if (text && (text.indexOf("ire('trackConversion'") != -1 || text.indexOf('ire("trackConversion"') != -1)) {
						pixel = text.trim().replace(/\s/g, '')
						pixel = pixel.split("trackConversion")[1];
						pixel = pixel.split("});")[0];
						return pixel;
					}
				}
			} catch (err) {
				usi_commons.report_error(err);
			}
			return pixel;
		},
		log_url: function() {
			usi_aff.load_script("https://www.upsellit.com/launch/blank.jsp?aff_click=" + encodeURIComponent(location.href));
		},
		monitor_affiliate_pixel: function (callback) {
			try {
				var pixels = usi_aff.report_affiliate_pixels();
				if (pixels) {
					if (typeof callback === "function") callback(pixels);
					return usi_aff.parse_pixels(pixels);
				}
				setTimeout(function () {
					usi_aff.monitor_affiliate_pixel(callback);
				}, 1000);
			} catch (err) {
				usi_commons.report_error(err);
			}
		},
		parse_pixels: function(pixels){
			try {
				usi_aff.load_script("https://www.upsellit.com/launch/blank.jsp?pixel_found=" + encodeURIComponent(location.href) +"&"+pixels);
			} catch (err) {
				usi_commons.report_error(err);
			}
		},
		report_affiliate_pixels: function () {
			var params = '';
			try {
				var pixels = {
					cj: document.querySelector("[src*='emjcd.com']"),
					sas: document.querySelector("[src*='shareasale.com/sale.cfm']"),
					linkshare: document.querySelector("[src*='track.linksynergy.com']"),
					pj: document.querySelector("[src*='t.pepperjamnetwork.com/track']"),
					avant: document.querySelector("[src*='tracking.avantlink.com/ptcfp.php']"),
					ir: { src: usi_aff.get_impact_pixel() },
					awin1: document.querySelector("[src*='awin1.com/sread']"),
					awin2: document.querySelector("[src*='zenaps.com/sread.js']"),
					cf: document.querySelector("[src*='https://cfjump.'][src*='.com/track']"),
					saasler1: document.querySelector("[src*='engine.saasler.com']"),
					saasler2: document.querySelector("[src*='saasler-impact.herokuapp.com']")
				};
				for (var i in pixels) {
					if (pixels[i] && pixels[i].src) {
						params += '&' + i + '=' + encodeURIComponent(pixels[i].src);
					}
				}
			} catch (err) {
				usi_commons.report_error(err);
			}
			return params;
		},
		load_script: function(source) {
			try {
				var docHead = document.getElementsByTagName("head")[0];
				var newScript = document.createElement('script');
				newScript.type = 'text/javascript';
				newScript.src = source;
				docHead.appendChild(newScript);
			} catch(err) {
				usi_commons.report_error(err);
			}
		}
	}
}


    try {
		usi_app = {};
		usi_app.main = function () {
			try {
				usi_app.device = usi_commons.is_mobile ? "mobile" : "desktop";
				usi_app.url = new usi_url.URL();
				usi_app.force_date = usi_commons.gup_or_get_cookie('usi_force_date');

				usi_app.home_page = usi_app.url.host == "www.ipvanish.com" && usi_app.url.path.full == "/";
				usi_app.essential_page = usi_app.url.full.toLowerCase().indexOf("essential") != -1;
				usi_app.advanced_page = usi_app.url.full.toLowerCase().indexOf("advanced") != -1;
				usi_app.confirmation_page = usi_app.url.full.toLowerCase().indexOf("signup.ipvanish.com/confirm") != -1;
				usi_app.staging_page = usi_app.url.full.toLowerCase().indexOf("cpg-278.staging.ipvanish.com") != -1;
				usi_app.signup_page = usi_app.url.full.toLowerCase().indexOf("checkout.ipvanish.com") !== -1;
				usi_app.blog_page = usi_app.url.full.toLowerCase().indexOf("/blog/") != -1;
				usi_app.from_offer_page = document.referrer.indexOf("/offer") != -1;
				usi_app.suppressed_url = usi_app.url.full.indexOf("all-options") != -1;
				usi_app.link_checker_page = usi_app.url.full.toLowerCase().indexOf("/link-checker") != -1;
				usi_app.is_enabled = usi_commons.gup_or_get_cookie("usi_enable", usi_cookies.expire_time.day, true) != "";
                usi_app.test = usi_commons.gup_or_get_cookie("usi_test", usi_cookies.expire_time.day, true);
				
				if (usi_app.suppressed_url) {
					usi_commons.log("* * * Suppressed Url");
					usi_cookies.set("usi_suppress", "true", 24*60*60, true);
				}
                
				if (usi_app.confirmation_page || usi_cookies.value_exists("usi_suppress")) return;
				
				usi_aff.monitor_affiliate_pixel(function(){
					if (typeof USI_orderID == "undefined") {
						usi_commons.load_script("//www.upsellit.com/active/ipvanish_pixel.jsp");
					}
				});
				
				if (!usi_app.confirmation_interval) usi_app.start_confirmation_monitor();

                usi_app.campaign_date = usi_date.set_date();

                // suppressing traffic
				if (usi_commons.gup('offer_id') != "") {
					if (usi_commons.gup('offer_id') != "68" && usi_commons.gup('offer_id') != "74" && usi_commons.gup('offer_id') != "75") {
						usi_cookies.set("usi_suppressed_traffic", "1", usi_cookies.expire_time.week);
					}
				}
				if (usi_commons.gup('usi_coupon') != "") {
					usi_cookies.set("usi_coupon", usi_commons.gup('usi_coupon'), 86400 * 7);
				}
				if (usi_commons.gup('usi_couponcode') != "") {
					usi_cookies.set("usi_couponcode", usi_commons.gup('usi_couponcode'), 86400 * 7);
				}
				if (usi_cookies.get("usi_couponcode") != null || usi_cookies.get("usi_coupon") != null) {
					usi_app.apply_coupon();
				}
				if (usi_app.from_offer_page || usi_app.url.full.toLowerCase().indexOf("/offer") != -1) {
					usi_cookies.set("usi_ppc", "1", usi_cookies.expire_time.week, true);
				}
				if (usi_app.link_checker_page && usi_cookies.value_exists("usi_link_checker")) {
					var key = (Math.random() < 0.50) ? "_a" : "_b";
					if (document.querySelector("#ipvanish-link-checker-button") != null) {
						var link_checker_button = document.querySelector("#ipvanish-link-checker-button");
						usi_dom.attach_event("click", function () {
							usi_commons.load_view("cIPoS2PTMnSDE6i6O1iJHvY", "62505", usi_commons.device + key);
						}, link_checker_button);
					}
				}
				if (usi_app.home_page || usi_app.blog_page) {
					var key = "";
					if (usi_app.home_page) {
						key += "_hp";
					} else if (usi_app.blog_page) {
						key += "_bp";
					}
					
					usi_commons.load_view("krA7fU9BwhsEIqbM1HihTxQ", "62011", usi_commons.device + key + "_b");
				} else if (usi_app.signup_page && usi_cookies.get("usi_suppressed_traffic") == null) {
					if (usi_app.advanced_page) {
						var key = Math.random() > 0.5 ? "_b" : "_c";
						usi_commons.load_view("pIKqDGNNCtLRoyGdJL2xI16", "62265", usi_commons.device + key);
					} else if (usi_app.essential_page) {
						usi_commons.load_view("4Jdv5cXyYOGZDhsbMLm7Vp8", "62267", usi_commons.device);
					}
				}
			} catch(err) {
				usi_commons.report_error(err);
			}
		};
		usi_app.load_hound_pixel_delayed = function() {
			
			if (typeof USI_orderID == "undefined" && typeof USI_orderAmt == "undefined") {
				usi_commons.load_script("//www.upsellit.com/active/ipvanish_pixel.jsp");
			}
		};
		usi_app.load_hound_pixel = function() {
			setTimeout(usi_app.load_hound_pixel_delayed, 7500);
		};
		usi_app.check_for_their_pop = function() {
			try {
				if (document.getElementById("coupon-popup") != null && document.getElementById("coupon-popup").className.indexOf("fade in") != -1) {
					//Theirs is displaying, we nede to both kill and suppress ours
					if (typeof usi_js !== 'undefined' && typeof usi_js.cleanup === 'function') {
						usi_js.cleanup();
					}
				} else {
					setTimeout(usi_app.check_for_their_pop, 250);
				}
			} catch(err) {
				usi_commons.report_error(err);
			}
		};
		usi_app.find_checkout_button = function() {
			try {
				var usi_found = 0;
				if (document.getElementsByName('ccsubmit').length > 0) {
					usi_found = 1;
					var usi_buttons = document.getElementsByName('ccsubmit')[0];
					if (usi_buttons.addEventListener) {
						usi_buttons.addEventListener("click", usi_app.load_hound_pixel, false);
					} else if (usi_buttons.attachEvent) {
						var r = usi_buttons.attachEvent("onclick", usi_app.load_hound_pixel);
					}
				}
				if (document.getElementsByName('ppsubmit').length > 0) {
					usi_found = 1;
					var usi_buttons = document.getElementsByName('ppsubmit')[0];
					if (usi_buttons.addEventListener) {
						usi_buttons.addEventListener("click", usi_app.load_hound_pixel, false);
					} else if (usi_buttons.attachEvent) {
						var r = usi_buttons.attachEvent("onclick", usi_app.load_hound_pixel);
					}
				}
				if (usi_found == 0) {
					setTimeout(usi_app.find_checkout_button, 1000);
				}
			} catch(err) {
				usi_commons.report_error(err);
			}
		};
		usi_app.apply_coupon = function() {
			try {
				var usiCouponInput = document.getElementById('Coupon');
				if (usiCouponInput != null) {
					if (usi_cookies.get("usi_coupon") != null) {
						usiCouponInput.value = usi_cookies.get("usi_coupon");
						usi_cookies.del('usi_coupon');
					} else {
						usiCouponInput.value = usi_cookies.get("usi_couponcode");
						usi_cookies.del('usi_couponcode');
					}
				}
			} catch(err) {
				usi_commons.report_error(err);
			}
		};
		
	    usi_app.start_confirmation_monitor = function() {
		    try {
			    usi_commons.log("usi_app.start_confirmation_monitor()");
			    var monitor_confirmation = function() {
				    if (document.querySelector(".checkout-done-page__information-summary") != null && document.querySelector(".checkout-done-summary__container") != null) {
					    usi_commons.load_script("https://www.upsellit.com/active/ipvanish_pixel.jsp");
					    clearInterval(usi_app.confirmation_interval);
				    }
			    };
			    monitor_confirmation();
			    if (!usi_app.confirmation_interval) {
				    usi_app.confirmation_interval = setInterval(monitor_confirmation, 1000);
			    }
		    } catch(err) {
			    usi_commons.report_error(err);
		    }
	    };
        
	
	    usi_app.session_data_callback = function() {
		    usi_app.country = usi_commons.gup("usi_force_country") || usi_app.session_data.country;
		    usi_app.check_for_change = function(){
			    if (usi_app.current_page == undefined || usi_app.current_page != location.href) {
				    usi_app.current_page = location.href;
				    usi_dom.ready(function(){
					    try {
						    if (usi_app.country == 'au' || usi_app.country == 'be' || usi_app.country == 'dk' || usi_app.country == 'de' || usi_app.country == 'ie' || usi_app.country == 'nz' || usi_app.country == 'sg' || usi_app.country == 'za' || usi_app.country == 'ch' || usi_app.country == 'gb' || usi_app.country == 'us') {
							    usi_cookies.set("usi_link_checker", "1", usi_cookies.expire_time.day, true);
							    usi_app.main();
						    } else {
						    	return;
						    }
					    } catch (err) {
						    usi_commons.report_error(err);
					    }
				    });
				    usi_commons.log("USI: running main");
			    }
			    setTimeout(usi_app.check_for_change, 1000);
		    };
		    if (!usi_app.check_for_change_timeout_id) {
			    usi_app.check_for_change_timeout_id = setTimeout(usi_app.check_for_change, 1000);
		    }
	    };
	    usi_commons.load_session_data(true);
     
	} catch(err) {
		usi_commons.report_error(err);
	}
}
