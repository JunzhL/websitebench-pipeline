jQuery(document).ready(function($) {

  // Function to run the loading spinner sequence
  function runLoadingSequence(callback) {
    const wait = setInterval(function () {
      const $icon1 = $('#icon-1');
      const $icon2 = $('#icon-2');

      if ($icon1.length && $icon2.length) {
        clearInterval(wait);

        // Replace first spinner after 3 seconds
        setTimeout(function () {
          $icon1.attr('src', dwmPluginAssetsUrl + 'check.svg');
          $icon1.attr('alt', 'Done');

          // Replace second spinner after another 3 seconds
          setTimeout(function () {
            $icon2.attr('src', dwmPluginAssetsUrl + 'check.svg');
            $icon2.attr('alt', 'Done');

            // Call callback (e.g., AJAX) after both icons are done
            if (typeof callback === 'function') {
              callback();
            }
          }, 3000);

        }, 3000);
      }
    }, 100);
  }

  // Function to send the AJAX request, display all results
  function fetchBreachResults(email, $result) {
    $.post(dwm_ajax.ajax_url, {
      action: 'dwm_search',
      nonce: dwm_ajax.nonce,
      query: email
    }, function (response) {
      $result.empty();

      if (response.success && response.data.entries && response.data.entries.length > 0) {
        const $card = $($('#tpl-breach-card').html());
        const $rows = $card.find('.breach-rows');

        response.data.entries.forEach(function (entry) {
          const companyName = entry.database_name || 'Unknown';
          // const breachDate = entry.breach_date || 'Unknown';
          const breachDate = entry.breach_date
            ? formatMonthYear(entry.breach_date)
            : "Unknown";

          const labelMap = {
            ip_address: 'IP Address',
            username: 'Usernames',
            hashed_password: 'Hashed Password',
            dob: 'Day of Birthday'
          };

          const compromisedKeys = Object.keys(entry).filter(function (key) {
            return !['id', 'email', 'database_name', 'breach_date'].includes(key);
          });

          const compromisedData = compromisedKeys.map(function (key) {
            return labelMap[key] || key.charAt(0).toUpperCase() + key.slice(1);
          }).join(', ') || 'N/A';

          const row = `
            <div class="breach-row">
              <div class="breach-cell">${companyName}</div>
              <div class="breach-cell">${breachDate}</div>
              <div class="breach-cell">${compromisedData}</div>
            </div>
          `;
          $rows.append(row);
        });

        const breachCount = response.data.entries.length;
        $card.find('.footer-note').html(
          `Your email address has been exposed in ${breachCount} known breach${breachCount > 1 ? 'es' : ''} circulating on the dark web. Change your passwords immediately and enable two-factor authentication wherever possible.`
        );

        $result.html($card);

        $('#alert-triangle').attr('src', dwmPluginAssetsUrl + 'alert-triangle.svg');

      } else if (response.success && response.data.entries && response.data.entries.length === 0) {
        const template = $('#tpl-no-breach').html();
        $result.html(template);
        // $('#dwm-btn-new-check').show();
        $('.email-check-container').hide();

        $('#check-circle').attr('src', dwmPluginAssetsUrl + 'check-circle.svg');
      } else {
        // render error message
        const template = $('#tpl-error').html();
        $result.html(template);
        $('#alert-triangle').attr('src', dwmPluginAssetsUrl + 'alert-triangle.svg');
      }

    }).fail(function () {
        const template = $('#tpl-error').html();
        $result.html(template);
        $('#alert-triangle').attr('src', dwmPluginAssetsUrl + 'alert-triangle.svg');
      // $result.html('<p class="error">Something went wrong. Please try again later.</p>');
    });
  }

  // Function to send the AJAX request, filter by unique Entries
  // function fetchBreachResults(email, $result) {
  //   $.post(dwm_ajax.ajax_url, {
  //     action: 'dwm_search',
  //     nonce: dwm_ajax.nonce,
  //     query: email
  //   }, function (response) {
  //     $result.empty();

  //     if (response.success && response.data.entries && response.data.entries.length > 0) {
  //       const $card = $($('#tpl-breach-card').html());
  //       const $rows = $card.find('.breach-rows');

  //       const uniqueEntries = [];
  //       const seen = new Set();

  //       response.data.entries.forEach(function (entry) {
  //         const key = `${entry.database_name}|${entry.breach_date}`;
  //         if (seen.has(key)) {
  //           return; // Skip duplicates
  //         }
  //         seen.add(key);
  //         uniqueEntries.push(entry);
  //       });

  //       uniqueEntries.forEach(function (entry) {
  //         const companyName = entry.database_name || 'Unknown';
  //         const breachDate = entry.breach_date || 'Unknown';

  //         const labelMap = {
  //           username: 'Usernames',
  //           hashed_password: 'Hashed Password',
  //           dob: 'Day of Birthday'
  //         };

  //         const compromisedKeys = Object.keys(entry).filter(function (key) {
  //           return !['id', 'email', 'database_name', 'breach_date'].includes(key);
  //         });

  //         const compromisedData = compromisedKeys.map(function (key) {
  //           return labelMap[key] || key.charAt(0).toUpperCase() + key.slice(1);
  //         }).join(', ') || 'N/A';

  //         const row = `
  //           <div class="breach-row">
  //             <div class="breach-cell">${companyName}</div>
  //             <div class="breach-cell">${breachDate}</div>
  //             <div class="breach-cell">${compromisedData}</div>
  //           </div>
  //         `;
  //         $rows.append(row);
  //       });

  //       const breachCount = uniqueEntries.length;
  //       $card.find('.footer-note').html(
  //         `Your email address has been exposed in ${breachCount} known breach${breachCount > 1 ? 'es' : ''} circulating on the dark web. Change your passwords immediately and enable two-factor authentication wherever possible.`
  //       );

  //       $result.html($card);
  //       $('#dwm-btn-new-check').show();
  //       // $('.email-check-container').hide();

  //       $('#alert-triangle').attr('src', dwmPluginAssetsUrl + 'alert-triangle.svg');

  //     } else {
  //       const template = $('#tpl-no-breach').html();
  //       $result.html(template);
  //       $('#dwm-btn-new-check').show();
  //       $('.email-check-container').hide();

  //       $('#check-circle').attr('src', dwmPluginAssetsUrl + 'check-circle.svg');
  //     }

  //   }).fail(function () {
  //     $result.html('<p class="error">Something went wrong. Please try again later.</p>');
  //   });
  // }



  // Main click handler
  $('#dwm-btn').on('click keypress', function (e) {
    if (e.type === 'click' || (e.type === 'keypress' && e.which === 13)) {
      const email = $('#dwm-input').val().trim();
      const $result = $('#dwm-result');
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

      if (!email || !emailRegex.test(email)) {
        $('#dwm-error').show();
        return;
      }

      $('.email-check-container').hide();
      $('#dwm-error').hide();

      const loadingTemplate = $('#tpl-loading').html();
      $result.html(loadingTemplate);

      $('#icon-1').attr('src', dwmPluginAssetsUrl + 'spinner.gif');
      $('#icon-2').attr('src', dwmPluginAssetsUrl + 'spinner.gif');

      // Run spinner animation first, then perform the request
      runLoadingSequence(function () {
        fetchBreachResults(email, $result);
      });
    }
  });

  // New check handler
  $('#dwm-btn-new-check').on('click', function (e) {
    if (e.type === 'click' || (e.type === 'keypress' && e.which === 13)) {
      $('#dwm-input').val('');
      $('#dwm-error').hide();
      $('#dwm-result').empty();
      $('#dwm-btn-new-check').hide();
      $('.email-check-container').show();

      $('html, body').animate({
        scrollTop: $('#dwm-btn').offset().top - 300
      }, 500);
    }
  });

  function formatMonthYear(isoDate) {
    const MONTHS = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'
    ];

    // Check if input matches the expected YYYY-MM-DD format
    if (typeof isoDate !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) {
      return isoDate; // Return the input unchanged if format is invalid
    }

    const [year, month] = isoDate.split('-');
    const monthIndex = parseInt(month, 10) - 1;

    return `${MONTHS[monthIndex]} ${year}`;
  }


});
