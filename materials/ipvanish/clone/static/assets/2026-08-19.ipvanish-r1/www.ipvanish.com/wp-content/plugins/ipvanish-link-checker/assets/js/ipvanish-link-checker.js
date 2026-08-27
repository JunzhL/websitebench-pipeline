const IpvlcLinkCheckerModule = (function($) {
  let timeoutIDs = []; // Store all timeout IDs in an array

  const ipvlcMainContentDiv = $(".ipvlc-main-content");
  const ipvlcLinkAnalysisContentDiv = $("#link-analysis-content");
  const ipvlcLinkAnalysisLoadingDiv = $("#link-analysis-loading");
  const ipvlcLinkAnalysisErrorContainer = $(".link-analysis__error-container");
  const ipvlcLinkAnalysisErrorDiv = $("#link-analysis-error-container");
  const ipvlcInputField = $("#ipvanish-link-checker-input");
  const ipvlcErrorField = $("#ipvanish-link-checker-input-error");
  const ipvlcCheckButton = $("#ipvanish-link-checker-button").prop(
    "disabled",
    true
  );
  const ipvlcSubmitFeedbackButton = $("#submit-feedback");
  const ipvlcAnotherCheckButton = $("#ipvanish-another-link-button");
  const ipvlcAnotherCheckButtonError = $("#ipvanish-another-link-button-error");
  const ipvlcSearchContainerDiv = $("#link-analysis__search-container");
  const ipvlcThumbsDownIcon = $("#thumbs-down-icon");
  const ipvlcThumbsUpIcon = $("#thumbs-up-icon");
  const ipvlcTextareaSection = $(".link-analysis__card-report-form");
  const ipvlcImprovementFeedbackInput = $("#improvement-feedback");
  const ipvlcFeedbackCheckboxSection = $(
    ".link-analysis__card-report-form-group--checkbox"
  );
  const ipvlcIncorrectDetectioncheckbox = $("#incorrect-detection");
  const ipvlcThanksMessage = $(".link-analysis__card-report-form-group--thanks");

  let inputUrl = "";
  let sanitizedFeedbackValue = "";
  let feedbackType = "";
  let incorrectDetection = false;
  let linkAnalysis = {};

  function init() {
    ipvlcMainContentDiv.append(
      ipvlcLinkAnalysisContentDiv,
      ipvlcLinkAnalysisLoadingDiv,
      ipvlcLinkAnalysisErrorContainer
    );

    // Attach event listeners
    ipvlcInputField.on("input", ipvlc_handleInput);
    ipvlcImprovementFeedbackInput.on("input", ipvlc_handleFeedbackInput);
    ipvlcIncorrectDetectioncheckbox.click(ipvlc_toggleIncorrectDetectionStatus);
    ipvlcCheckButton.click(ipvlc_sendUrlForAnalysis);
    ipvlcAnotherCheckButton.click(ipvlc_resetViewAndFeedbackSection);
    ipvlcAnotherCheckButtonError.click(ipvlc_resetViewAndFeedbackSection);
    ipvlcInputField.keypress(handleKeyPress);
    ipvlcThumbsDownIcon.click(showNegativeFeedbackSection);
    ipvlcThumbsUpIcon.click(showPositiveFeedbackSection);
    ipvlcSubmitFeedbackButton.click(ipvlc_submitFeedback);
  }

  function ipvlc_handleInput() {
    inputUrl = ipvlcInputField.val();
    ipvlcErrorField.toggle(inputUrl === "");
    ipvlcCheckButton.prop("disabled", inputUrl === "");
  }

  function ipvlc_handleFeedbackInput() {
    sanitizedFeedbackValue = $.trim(
      ipvlcImprovementFeedbackInput.val().replace(/(<([^>]+)>)/gi, "")
    );
  }

  function ipvlc_toggleIncorrectDetectionStatus() {
    incorrectDetection = !incorrectDetection;
  }

  async function ipvlc_sendUrlForAnalysis() {
    ipvlcLinkAnalysisErrorContainer.hide();
    ipvlcLinkAnalysisContentDiv.hide();
    ipvlcSearchContainerDiv.hide();
    ipvlcMainContentDiv.show().css("display", "flex");

    ipvlc_resetLoadingView();
    ipvlcLinkAnalysisLoadingDiv.show().css("display", "flex");
    ipvlc_animateListItems();

    // After the Check Link button is clicked the page will auto scroll to the loading section
    const scrollTopPosition =
      $(ipvlcLinkAnalysisLoadingDiv).offset().top - 140;

    $("html, body").animate(
      {
        scrollTop: scrollTopPosition,
      },
      {
        duration: 2000, // Animation speed (in milliseconds)
        easing: "swing",
      }
    );

    try {
      const response = await ipvlc_makeAjaxRequest(
        ipv_link_checker_vars.ajax_url,
        {
          action: "ipvanish_link_checker_ajax_handler",
          url: inputUrl,
          nonce: ipv_link_checker_vars.nonce
        }
      );

      if (response && response.success === true) {
        if(!response.data.error) {
          ipvlc_handleSuccess(response.data);
        } else if (response.data.error !== "") {
          if(response.data.verdict === Verdict.UNKNOWN) {
            handleError(response.data.error);
          } else if(response.data.verdict > 0) {
            ipvlc_handleSuccess(response.data);
          }
        }
      } else {
        handleError(response);
      }
    } catch (error) {
      handleError(error);
    } finally {
      const lastItem = $(".list-item:last-child");
      lastItem.find(".list-item__icon").attr("src", function (_, currentSrc) {
        const basePath = currentSrc.substring(0, currentSrc.lastIndexOf("/"));
        lastItem
          .find(".list-item__icon")
          .attr("src", `${basePath}/check.svg`)
          .removeClass("spinner");
      });

      // Hide the loading section
      ipvlcLinkAnalysisLoadingDiv.hide();
      ipvlc_resetLoadingView();
    }
  }

  function ipvlc_handleSuccess(data) {
    IpvlcLinkAnalyzerModule.ipvlc_handleResponse(data);
    linkAnalysis = data;
    ipvlc_displayAnalysisResult();
}

function ipvlc_displayAnalysisResult() {
    ipvlcMainContentDiv.show().css("display", "flex");
    ipvlcLinkAnalysisContentDiv.show().css("display", "flex");
}

  function ipvlc_resetViewAndFeedbackSection() {
    ipvlc_resetLoadingView();
    ipvlc_resetFeedbackSection();
    ipvlcInputField.val("");
    ipvlcSearchContainerDiv.show().css("display", "flex");
    let scrollTopPosition = $(ipvlcSearchContainerDiv).offset().top - 140;

    $("html, body").animate(
      {
        scrollTop: scrollTopPosition,
      },
      {
        duration: 800,
        easing: "swing",
      }
    );
  }

  function handleKeyPress(e) {
    if (e.key === "Enter") {
      ipvlc_sendUrlForAnalysis();
    }
  }

  function showNegativeFeedbackSection() {
    feedbackType = "negative";
    ipvlcTextareaSection.show().css("display", "flex");
    ipvlcImprovementFeedbackInput.attr(
      "placeholder",
      "Please share how we could improve this tool"
    );
    ipvlcThumbsDownIcon.addClass("active");
    ipvlcThumbsUpIcon.removeClass("active");
    ipvlcImprovementFeedbackInput.val("");
    ipvlcIncorrectDetectioncheckbox.prop("checked", false);
    ipvlcFeedbackCheckboxSection.show().css("display", "flex");
    ipvlcThanksMessage.hide();
  }

  function showPositiveFeedbackSection() {
    feedbackType = "positive";
    ipvlcTextareaSection.show().css("display", "flex");
    ipvlcImprovementFeedbackInput.attr(
      "placeholder",
      "Thank you for providing feedback"
    );
    ipvlcThumbsUpIcon.addClass("active");
    ipvlcThumbsDownIcon.removeClass("active");
    ipvlcImprovementFeedbackInput.val("");
    ipvlcIncorrectDetectioncheckbox.prop("checked", false);
    ipvlcFeedbackCheckboxSection.hide();
    ipvlcThanksMessage.hide();
  }

  async function ipvlc_submitFeedback() {
    ipvlcTextareaSection.hide();
    ipvlcThumbsDownIcon.removeClass("active");
    ipvlcThumbsUpIcon.removeClass("active");
    const linkFeedback = linkAnalysis["links"]["feedback"];

    try {
      const response = await ipvlc_makeAjaxRequest(
        ipv_link_checker_vars.ajax_url,
        {
          action: "ipvanish_link_checker_feedback",
          feedbackLink: linkFeedback,
          type: feedbackType,
          incorrectDetection: incorrectDetection,
          feedbackValue: sanitizedFeedbackValue,
          nonce: ipv_link_checker_vars.nonce,
        }
      );

      if (response && response.success === true) {          
        ipvlcThanksMessage.show();
      } else {
        handleError(response.data);
      }
    } catch (error) {
      handleError(error);
    } finally {
      incorrectDetection = false;
      ipvlcImprovementFeedbackInput.val("");
      sanitizedFeedbackValue = "";
      ipvlcIncorrectDetectioncheckbox.prop("checked", false);
    }
  }

  function ipvlc_makeAjaxRequest(url, data, type = "POST") {
    return new Promise((resolve, reject) => {
      $.ajax({
        url: url,
        type: type,
        data: data,
        beforeSend: function (xhr) {
          xhr.setRequestHeader("X-WP-Nonce", ipv_link_checker_vars.nonce);
        },
        success: resolve,
        error: reject,
        complete: function () {},
      });
    });
  }

  function handleError(error) {
    const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

    const errorMessage = (() => {
  
      // Check if 'error.display' exists, else uses the error itself
      const errorText = error.display ?? (typeof error === 'string' ? error : 'Unknown Error');
      const formattedError = capitalize(errorText);
      
      return `Link analysis terminated with an error <br><br><span style='font-weight:700'>${formattedError}</span>`;
    })();
  
    $(".link-analysis__error-message").html(errorMessage);
    ipvlcLinkAnalysisErrorContainer.show().css("display", "flex");
    ipvlcLinkAnalysisErrorDiv.show().css("display", "flex");
  }

  function ipvlc_resetFeedbackSection() {
    // Remove 'active' class from both thumbs icons if they exist
    $("#thumbs-up-icon, #thumbs-down-icon").each(function() {
      if ($(this).length) {
        $(this).removeClass("active");
      }
    });
  
    if ($(".link-analysis__card-report-form-group--checkbox").length) {
      $(".link-analysis__card-report-form-group--checkbox").hide();
    }
  
    if ($("#incorrect-detection").length) {
      $("#incorrect-detection").prop('checked', false);
    }
  
    if ($(".link-analysis__card-report-form").length) {
      $(".link-analysis__card-report-form").hide();
    }

    ipvlcThanksMessage.hide();
  }
  

  function ipvlc_resetLoadingView() {
    const basePath = $(".list-item .list-item__icon").attr("src").replace(/\/[^/]*$/, "");
    $(".list-item .list-item__icon")
      .attr("src", `${basePath}/gray-circle.svg`)
      .removeClass("spinner");
  }

  // Animate the list of items
  function ipvlc_animateListItems() {
    // Clear all existing timeouts before starting new animations
    ipvlc_clearTimeouts(); // Clear existing timeouts
    const listItems = $(".list-item");
    const totalItems = listItems.length;
    let itemsProcessed = 0;

    listItems.each(function (index, item) {
      const timeoutId = setTimeout(function () {
        $(item)
          .find(".list-item__icon")
          .attr("src", function (_, currentSrc) {
            const basePath = currentSrc.substring(
              0,
              currentSrc.lastIndexOf("/")
            );
            $(item)
              .find(".list-item__icon")
              .attr("src", `${basePath}/spinner.gif`)
              .addClass("spinner");
          });
      }, index * 3000);

      timeoutIDs.push(timeoutId);

      // Skip last item; it stops loading upon request completion.
      if (index === totalItems - 1) return;

      const timeoutId2 = setTimeout(function () {
          $(item)
            .find(".list-item__icon")
            .attr("src", function (_, currentSrc) {
              const basePath = currentSrc.substring(
                0,
                currentSrc.lastIndexOf("/")
              );
              $(item)
                .find(".list-item__icon")
                .attr("src", `${basePath}/check.svg`)
                .removeClass("spinner");
            });

          itemsProcessed++;
      }, (index + 1) * 3000);
   
      timeoutIDs.push(timeoutId2);
    });
  }

  function ipvlc_clearTimeouts() {
    timeoutIDs.forEach(id => clearTimeout(id));
    timeoutIDs = [];
  }

  return {
    init: init,
  };
})(jQuery);

// Initialize the module
jQuery(document).ready(function($) {
  IpvlcLinkCheckerModule.init();
});