const IpvlcLinkAnalyzerModule = (function($) { 

  const verdictColors = {
    0: "#6FBC44", // Unknown
    1: "#F04438", // Malicious
    2: "#FF8800", // Suspect
    3: "#6FBC44", // Whitelisted
  };

  function ipvlc_handleResponse(linkAnalysis) {
    if (!linkAnalysis) return;

    // Clear previous contents
    ipvlc_resetValues();
    // Update UI based on response
    ipvlc_updateUI(linkAnalysis);
  }
  
  // Clear previous contents
  function ipvlc_resetValues() {
    $('#link-analysis-message').text("");
    $('#link-analysis-title').text("");
    $('#screenshot').empty();
    $(".ipv-final-link").hide();
    $(".link-analysis-card__body").css("background-color", "#FFF");
    $(".result-categories").hide();
    $(".result-features .link-analysis__row-label h3").text("");
    $("#category-list").empty();
    $("#ipv-final-link").empty();
    $("#ipv-initial-link").empty();
    // $("#link-analysis__card-report").hide();
    $("#link-analysis-card__screenshot").hide();
    $(".result-classification").hide();    
    $("#link-analysis-classification").text("");
    $(".link-analysis__error-message").html("");
    $(".ipvlcTextareaSection").hide();
    $(".result-features").hide();
    $("#feature-list").empty();
  }

  // update UI based on the response
  function ipvlc_updateUI(linkAnalysis) {
    const { categories, classification, features, landing_url, links, original_url, screenshot, verdict } = linkAnalysis;

    const verdictTitles = {
      0: "No Threats Detected", // Unknown
      1: "Harmful Link Detected", // Malicious
      2: "Warning: Potentially Harmful URL", // Suspect
      3: "No Threats Detected", // Whitelisted
    };

    const verdictMessages = {
      0: "We did not detect malicious activity in our analysis. This URL appears to be safe.", // Unknown
      1: "", // Malicious
      2: "", // Suspect
      3: "We did not detect malicious activity in our analysis. This URL appears to be safe.", // Whitelisted
    };

    $('#link-analysis-title').text(verdictTitles[verdict]);
    $('#link-analysis-message').text(verdictMessages[verdict]);

    ipvlc_updateStatusIcon(verdict);
    ipvlc_updateBackgroundIcon(verdict);

    if (!$.isEmptyObject(classification) && verdict !== Verdict.WHITELISTED) {
      headerMessage = verdict === Verdict.MALICIOUS ? "Known Malicious URL" : "";
      $("#link-analysis-classification").text(classification.join(", "));
      $(".result-classification").find(".header-title").text(headerMessage);
      $(".result-classification").show().css({
        'display' : 'flex',
        'border-bottom-color' : verdictColors[verdict]
     });
    }

    if (original_url) {
      const sanitized_original_url = sanitizeURL(original_url);
      $(".ipv-initial-link").show().css("display", "flex");
      $("#ipv-initial-link").text(sanitized_original_url).on("copy", handleCopy);
      $("#ipv-initial-link").attr("title", sanitized_original_url);
    }

    if (landing_url) {
      $(".ipv-final-link").show().css("display", "flex");
      $("#ipv-final-link").html(landing_url).on('copy', handleCopy);
      $("#ipv-final-link").attr("title", landing_url);
    }

    if ($.isArray(features) && features.length > 0) {
      const lowerCaseFeatures = features.map(sentence => sentence.toLowerCase());
      let filteredFeatures = new Set(lowerCaseFeatures);
      // Capitalize the first letter of each sentence in filteredFeatures
      filteredFeatures = Array.from(filteredFeatures).map(sentence => {
        return sentence.charAt(0).toUpperCase() + sentence.slice(1);
      });

      ipvlc_updateFeatures(filteredFeatures, verdict);
    }


    if (categories && categories.length > 0) {
      const categoryList = categories.filter(category => category).map(category => category.toLowerCase());

      if (categoryList.length > 0) {
        ipvlc_updateCategories(categoryList, verdict);
      }
    }

    if (screenshot && screenshot !== "") {
      let imgElement = $("<img>").attr("src", "data:image/png;base64," + screenshot);
      $("#screenshot").append(imgElement);
      $("#link-analysis-card__screenshot").show().css("display", "flex");
    }
  }

  function ipvlc_updateStatusIcon(verdict) {
    // Unknown, Malicious, Suspect, Whitelisted
    const imageNameMap = ["safe-circle.png", "malicious-circle.png", "suspect-circle.svg", "safe-circle.png"];
    const newImageName = imageNameMap[verdict] || "safe-circle.png";    
    $("#status-header-icon").attr("src", function (_, currentSrc) {
      const basePath = currentSrc.substring(0, currentSrc.lastIndexOf("/"));
      $("#status-header-icon").attr("src", `${basePath}/${newImageName}`);
    });
  }

  function ipvlc_updateBackgroundIcon(verdict) {
    // Unknown, Malicious, Suspect, Whitelisted
    const backgroundColorMap = ["#EAFAE3", "#FEE4E2", "#FFF0DE", "#EAFAE3"];
    const backgroundColor = backgroundColorMap[verdict];
    if (backgroundColor) {
      $(".link-analysis-card__body").css("background-color", backgroundColor);
    }
  }

  function ipvlc_updateCategories(categoryList, verdict) {

      const categoriesDiv = $("#category-list");
      const verdictBackgroundColor = verdictColors[verdict];

      let hasValidCategory = false;

      categoryList.forEach(function (category) {
        if (IconMapping.hasOwnProperty(category) && CATEGORY_DESCRIPTION_MAP.hasOwnProperty(category)) {
          const categoryDiv = $("<div>", { class: "category" });
          const categoryCircle = $("<div>", { class: "category-circle" });
          const categoryName = $("<span>").text(CATEGORY_DESCRIPTION_MAP[category]);
          const categoryIconClass = IconMapping[category];
          const categoryIcon = $("<i>", { class: "fa-solid " + categoryIconClass });
      
          categoryCircle.append(categoryIcon);
          categoryDiv.append(categoryCircle, categoryName);
      
          if (DeeplinkCategoryTitle.hasOwnProperty(category)) {
            let categoryTitle = DeeplinkCategoryTitle[category];
            categoryDiv.attr('title', categoryTitle);
          }

          categoriesDiv.append(categoryDiv);
      
          if (verdictBackgroundColor) {
            categoryCircle.css("background-color", verdictBackgroundColor);
          }

          hasValidCategory = true;
        }
      });
      
      if(hasValidCategory) {
        $(".result-categories").show().css({
          'display' : 'flex',
          'border-bottom-color' : verdictColors[verdict]
       });
      } else {
        $(".result-categories").hide();
      }
  }

  function ipvlc_updateFeatures(features, verdict) {
    // Unknown, Malicious, Suspect, Whitelisted
    const imageNameMap = ["unknown-check.svg", "malicious-check.svg", "suspect-check.svg", , "unknown-check.svg"];
    const imageName = imageNameMap[verdict] || "unknown-check.svg";

    const featureTitles = {
      0: "Detected Features", // Unknown
      1: "Malicious Features", // Malicious
      2: "Suspicious Features", // Suspect
      3: "Detected Features", // Whitelisted
    };

    const featuresContainer = $("#feature-list");
    featuresContainer.empty(); // Clear previous contents

    features.forEach(function (feature) {
      featuresContainer.removeClass("one-column");
      featuresContainer.addClass("two-columns");
      const listItem = $("<li>").html(
        `</li><img src="${ipv_link_checker_vars.plugin_path}/assets/images/${imageName}" class="checkmark" style="margin-right:19px;"></img><span class="feature">${feature}</span>`
      );
      featuresContainer.append(listItem);
      if (features.length === 1) {
        featuresContainer.removeClass("two-columns");
        featuresContainer.addClass("one-column");
      }
    });      

    const featuresTitle = featureTitles[verdict] ? featureTitles[verdict] : "Detected Features";      

    $(".result-features .link-analysis__row-label h3").text(featuresTitle);
    $(".result-features").show().css({
      'display' : 'grid',
      'border-bottom-color' : verdictColors[verdict]
    });    
  }

  // Open modal on image click
  $(".link-analysis__row-value #screenshot").click(function () {
    let imgSrc = $(this).find("img").attr("src");
    $("#modal-img").attr("src", imgSrc);
    $("#modal").css("display", "block");
  });

  // Close modal when clicking close button or outside the modal
  $(".close, .modal").click(function () {
    $("#modal").css("display", "none");
  });

  // Prevent modal from closing when clicking inside it
  $(".modal-content").click(function (e) {
    e.stopPropagation();
  });

  // Prevent user from copying the URL
  function handleCopy(e) {
    e.preventDefault();
    const $errorMessage = $('.copy-disabled-message');
    $errorMessage.fadeIn().css("display", "flex");
    setTimeout(() => $errorMessage.fadeOut(), 3000);
  }

  // Function to check for repeated sentences
  function hasRepeatedSentences(sentences) {
    const uniqueSentences = new Set(sentences);
    return uniqueSentences.size !== sentences.length;
  }

  function sanitizeURL(url) {
    return url.replace(/[&<>"']/g, function(match) {
      const escapeMap = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      };
      return escapeMap[match];
    });
  }


  $(".link-analysis__button--cta").click(function(){    
    var url = ipv_link_checker_vars.get_ipvanish_url;    
    window.open(url, "_blank");
  });
  
  return {
    ipvlc_handleResponse: ipvlc_handleResponse,
  };
})(jQuery);
