
window.usi_session_data = {
    ip:'129.97.124.110',
    country :'ca',
    state:'ON',
    city:'Waterloo',
    postal :'N2L', 
    lng :'-80.5164', 
    lat :'43.4668',
    isp:'University of Waterloo',
    metro:'-1'
    
}
usi_set_session_data = function() {
    if (typeof(usi_app) !== "undefined") {
        usi_app.session_data = window.usi_session_data;
        usi_cookies.set_json("usi_session_data", usi_app.session_data, 24*60*60);
        if (typeof(usi_app.session_data_callback) !== "undefined") {
            usi_app.session_data_callback();
        }
    } else {
        setTimeout(usi_set_session_data, 500);
    }
};
usi_set_session_data();
