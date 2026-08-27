/**
 * User IP and Location JavaScript - Enhanced with security and performance fixes
 * Fixes: Race conditions, multiple API calls, timeouts, error handling, cache compatibility
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        TIMEOUT: 10000, // 10 seconds timeout
        RETRY_ATTEMPTS: 2,
        RETRY_DELAY: 1000, // 1 second
        CACHE_DURATION: 300000, // 5 minutes in milliseconds
        DEBUG: false
    };

    // Singleton API manager to prevent multiple calls and race conditions
    class UserIPLocationAPI {
        constructor() {
            this.dataPromise = null;
            this.isProcessing = false;
            this.cache = {
                data: null,
                timestamp: null
            };
        }

        /**
         * Get location data with caching and error handling
         * @returns {Promise} Promise that resolves to location data
         */
        async getLocationData() {
            // Return cached data if still valid
            if (this.cache.data && this.cache.timestamp && 
                (Date.now() - this.cache.timestamp < CONFIG.CACHE_DURATION)) {
                if (CONFIG.DEBUG) console.log('UserIPLocation: Using cached data');
                return this.cache.data;
            }

            // Return existing promise if already fetching
            if (this.dataPromise) {
                if (CONFIG.DEBUG) console.log('UserIPLocation: Returning existing promise');
                return this.dataPromise;
            }

            // Create new promise for API call
            this.dataPromise = this.fetchWithRetry();
            
            try {
                const data = await this.dataPromise;
                // Cache the successful result
                this.cache.data = data;
                this.cache.timestamp = Date.now();
                return data;
            } catch (error) {
                // Reset promise on error so next call can retry
                this.dataPromise = null;
                throw error;
            }
        }

        /**
         * Fetch data with timeout and retry logic
         * @returns {Promise} Promise that resolves to location data
         */
        async fetchWithRetry(attempt = 1) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), CONFIG.TIMEOUT);

                // Add cache-busting parameter to prevent caching
                const url = new URL(userIpLocationData.apiUrl);
                url.searchParams.set('_t', Date.now());
                url.searchParams.set('_r', Math.random().toString(36).substr(2, 9));

                const response = await fetch(url.toString(), {
                    cache: 'no-store', // Force no caching
                    signal: controller.signal,
                    headers: {
                        'Cache-Control': 'no-cache, no-store, must-revalidate',
                        'Pragma': 'no-cache',
                        'Expires': '0'
                    }
                });

                clearTimeout(timeoutId);

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const data = await response.json();

                if (!data.status || data.status !== 'success') {
                    throw new Error(data.message || 'API returned unsuccessful status');
                }

                if (CONFIG.DEBUG) console.log('UserIPLocation: API call successful', data);
                return data;

            } catch (error) {
                if (CONFIG.DEBUG) console.warn(`UserIPLocation: Attempt ${attempt} failed:`, error.message);

                // Retry logic
                if (attempt < CONFIG.RETRY_ATTEMPTS && 
                    (error.name === 'AbortError' || error.message.includes('fetch'))) {
                    
                    if (CONFIG.DEBUG) console.log(`UserIPLocation: Retrying in ${CONFIG.RETRY_DELAY}ms...`);
                    await new Promise(resolve => setTimeout(resolve, CONFIG.RETRY_DELAY));
                    return this.fetchWithRetry(attempt + 1);
                }

                // Final error handling
                const errorMessage = error.name === 'AbortError' 
                    ? 'Request timeout - please check your connection'
                    : error.message || 'Failed to retrieve location data';
                
                throw new Error(errorMessage);
            }
        }

        /**
         * Clear cache (useful for testing)
         */
        clearCache() {
            this.cache.data = null;
            this.cache.timestamp = null;
            this.dataPromise = null;
        }
    }

    // Create singleton instance
    const apiManager = new UserIPLocationAPI();

    /**
     * Process placeholders in input field values (OptimizePress compatibility)
     * @param {Element} context - DOM element to search for input fields with placeholders
     */
    async function processInputFieldPlaceholders(context) {
        // Find input fields and textareas that contain placeholder spans in their values
        const inputFields = context.querySelectorAll('input[value*="user-ip-placeholder"]:not(.user-ip-input-processed)');
        const textareas = context.querySelectorAll('textarea:not(.user-ip-input-processed)');
        
        // Filter textareas that contain placeholder spans
        const textareasWithPlaceholders = Array.from(textareas).filter(textarea => 
            textarea.value && textarea.value.includes('user-ip-placeholder')
        );
        
        const allFields = [...inputFields, ...textareasWithPlaceholders];
        
        if (allFields.length === 0) {
            return;
        }

        if (CONFIG.DEBUG) console.log(`UserIPLocation: Processing ${allFields.length} form field placeholders`);

        try {
            const data = await apiManager.getLocationData();
            
            allFields.forEach(input => {
                try {
                    let value = input.value;
                    
                    // Skip if value is empty or doesn't contain placeholders
                    if (!value || !value.includes('user-ip-placeholder')) {
                        return;
                    }
                    
                    // Decode HTML entities first (OptimizePress encodes them)
                    const tempElement = document.createElement('div');
                    tempElement.innerHTML = value;
                    const decodedValue = tempElement.textContent || tempElement.innerText || value;
                    
                    // Create a temporary DOM element to parse the HTML (XSS-safe)
                    const tempDiv = document.createElement('div');
                    
                    // Only parse if it contains our specific placeholder class to prevent XSS
                    if (decodedValue.includes('user-ip-placeholder')) {
                        tempDiv.innerHTML = decodedValue;
                    } else {
                        // If it doesn't contain our placeholder, don't parse as HTML
                        return;
                    }
                    
                    // Find placeholder spans in the temporary element
                    const placeholders = tempDiv.querySelectorAll('.user-ip-placeholder');
                    
                    placeholders.forEach(placeholder => {
                        const type = placeholder.dataset.type;
                        let replacementValue = data[type] || '';
                        
                        // Handle special cases for mobile, proxy, hosting text
                        if (type === 'mobile' || type === 'proxy' || type === 'hosting') {
                            replacementValue = data[type + '_text'] || '';
                        }
                        
                        // Sanitize the replacement value to prevent XSS
                        if (typeof replacementValue === 'string') {
                            replacementValue = replacementValue.replace(/[<>&"']/g, function(match) {
                                const escapeMap = {
                                    '<': '&lt;',
                                    '>': '&gt;',
                                    '&': '&amp;',
                                    '"': '&quot;',
                                    "'": '&#x27;'
                                };
                                return escapeMap[match];
                            });
                        }
                        
                        // Replace the placeholder span with the actual value as text node (XSS-safe)
                        placeholder.replaceWith(document.createTextNode(String(replacementValue)));
                    });
                    
                    // Update the input field value with the processed content
                    const finalValue = tempDiv.textContent || tempDiv.innerText || '';
                    input.value = finalValue;
                    input.classList.add('user-ip-input-processed');
                    
                    if (CONFIG.DEBUG) {
                        console.log(`UserIPLocation: Processed form field placeholder for ${input.name || input.id || 'unnamed field'}`);
                        console.log('Original value:', value);
                        console.log('Final value:', finalValue);
                    }
                } catch (error) {
                    console.error('UserIPLocation: Error processing form field placeholder:', error);
                    input.classList.add('user-ip-input-error');
                    if (CONFIG.DEBUG) {
                        console.log('Failed field:', input);
                        console.log('Original value:', input.value);
                    }
                }
            });

        } catch (error) {
            console.error('UserIPLocation: API Error for input fields:', error.message);
            
            // Handle failed form fields gracefully
            allFields.forEach(input => {
                input.classList.add('user-ip-input-error');
                // Clear the placeholder HTML and leave empty or use fallback
                input.value = '';
            });
        }
    }

    /**
     * Process placeholders in the given context
     * @param {Element} context - DOM element to search for placeholders
     */
    async function processPlaceholders(context) {
        // Prevent processing if already in progress
        if (apiManager.isProcessing) {
            if (CONFIG.DEBUG) console.log('UserIPLocation: Already processing, skipping');
            return;
        }

        const placeholders = context.querySelectorAll('.user-ip-placeholder:not(.user-ip-processed):not(.user-ip-error)');
        if (placeholders.length === 0) {
            return;
        }

        if (CONFIG.DEBUG) console.log(`UserIPLocation: Processing ${placeholders.length} placeholders`);

        // Mark as processing to prevent race conditions
        apiManager.isProcessing = true;
        placeholders.forEach(el => el.classList.add('user-ip-processing'));

        try {
            const data = await apiManager.getLocationData();
            
            placeholders.forEach(el => {
                try {
                    const type = el.dataset.type;
                    let value = data[type] || '';

                    if (type === 'flag') {
                        const countryCode = data.countryCode ? data.countryCode.toLowerCase() : 'unknown';
                        const flagUrl = userIpLocationData.flagsUrl + countryCode + '.png';
                        const height = el.dataset.height || 'auto';
                        const width = el.dataset.width || 'auto';
                        const verticalAlign = el.dataset.verticalAlign || 'middle';

                        const img = document.createElement('img');
                        img.src = flagUrl;
                        img.alt = data.country || 'Country Flag';
                        img.style.height = height;
                        img.style.width = width;
                        img.style.verticalAlign = verticalAlign;
                        img.classList.add('user-ip-flag');
                        
                        // Handle image load errors
                        img.onerror = function() {
                            if (CONFIG.DEBUG) console.warn('UserIPLocation: Flag image failed to load:', flagUrl);
                            this.src = userIpLocationData.flagsUrl + 'unknown.png';
                        };
                        
                        el.replaceWith(img);
                    } else if (type === 'mobile' || type === 'proxy' || type === 'hosting') {
                        value = data[type + '_text'] || '';
                        // Sanitize value to prevent XSS
                        if (typeof value === 'string') {
                            value = value.replace(/[<>&"']/g, function(match) {
                                const escapeMap = {
                                    '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#x27;'
                                };
                                return escapeMap[match];
                            });
                        }
                        el.replaceWith(document.createTextNode(String(value)));
                    } else {
                        // Sanitize value to prevent XSS
                        if (typeof value === 'string') {
                            value = value.replace(/[<>&"']/g, function(match) {
                                const escapeMap = {
                                    '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#x27;'
                                };
                                return escapeMap[match];
                            });
                        }
                        el.replaceWith(document.createTextNode(String(value)));
                    }

                    if (CONFIG.DEBUG) console.log(`UserIPLocation: Processed ${type} placeholder`);
                } catch (error) {
                    console.error('UserIPLocation: Error processing placeholder:', error);
                    el.classList.add('user-ip-error');
                    el.replaceWith(document.createTextNode(''));
                }
            });

        } catch (error) {
            console.error('UserIPLocation: API Error:', error.message);
            
            // Handle failed placeholders gracefully
            placeholders.forEach(el => {
                el.classList.remove('user-ip-processing');
                el.classList.add('user-ip-error');
                
                // Show fallback content instead of removing
                const fallbackText = el.dataset.fallback || '';
                el.replaceWith(document.createTextNode(fallbackText));
            });
        } finally {
            // Always reset processing flag
            apiManager.isProcessing = false;
            placeholders.forEach(el => {
                if (el.parentNode) { // Check if element still exists
                    el.classList.remove('user-ip-processing');
                    el.classList.add('user-ip-processed');
                }
            });
        }
    }

    /**
     * Process conditional content based on user location
     * @param {Element} context - DOM element to search for conditional content
     */
    async function processConditionalContent(context) {
        const conditionals = context.querySelectorAll('.user-ip-conditional:not(.user-ip-conditional-processed)');
        if (conditionals.length === 0) {
            return;
        }

        if (CONFIG.DEBUG) console.log(`UserIPLocation: Processing ${conditionals.length} conditional blocks`);

        try {
            const data = await apiManager.getLocationData();
            
            conditionals.forEach(el => {
                try {
                    const conditionsStr = el.dataset.conditions;
                    if (!conditionsStr) {
                        // No conditions, show content
                        el.style.display = '';
                        el.classList.add('user-ip-conditional-processed');
                        return;
                    }

                    const conditions = JSON.parse(conditionsStr);
                    const shouldShow = evaluateConditions(conditions, data);

                    if (shouldShow) {
                        el.style.display = '';
                        if (CONFIG.DEBUG) console.log('UserIPLocation: Showing conditional content', conditions);
                    } else {
                        el.remove();
                        if (CONFIG.DEBUG) console.log('UserIPLocation: Hiding conditional content', conditions);
                    }

                    el.classList.add('user-ip-conditional-processed');
                } catch (error) {
                    console.error('UserIPLocation: Error processing conditional:', error);
                    // On error, show the content (fail-safe)
                    el.style.display = '';
                    el.classList.add('user-ip-conditional-processed');
                }
            });

        } catch (error) {
            console.error('UserIPLocation: API Error for conditionals:', error.message);
            // On API error, show all conditional content (fail-safe)
            conditionals.forEach(el => {
                el.style.display = '';
                el.classList.add('user-ip-conditional-processed');
            });
        }
    }

    /**
     * Evaluate conditions against location data
     * @param {Object} conditions - Conditions to evaluate
     * @param {Object} data - Location data
     * @returns {boolean} Whether conditions are met
     */
    function evaluateConditions(conditions, data) {
        const conditionMap = {
            'country': 'countryCode',
            'country_not': 'countryCode',
            'region': 'region',
            'region_not': 'region',
            'city': 'city',
            'city_not': 'city',
        };

        for (const [conditionKey, conditionValue] of Object.entries(conditions)) {
            const dataKey = conditionMap[conditionKey];
            if (!dataKey) continue;

            const values = conditionValue.split(',').map(v => v.trim().toLowerCase());
            const userValue = (data[dataKey] || '').toLowerCase();
            const isNotCondition = conditionKey.includes('_not');
            const isMatch = values.includes(userValue);

            // If a 'not' condition matches, or a normal condition does not match, then we hide.
            if ((isNotCondition && isMatch) || (!isNotCondition && !isMatch)) {
                return false;
            }
        }

        return true;
    }

    /**
     * Debounced processor to handle rapid DOM changes
     */
    let processingTimeout;
    function debouncedProcess(context) {
        clearTimeout(processingTimeout);
        processingTimeout = setTimeout(() => {
            processPlaceholders(context);
            processConditionalContent(context);
            processInputFieldPlaceholders(context); // Added this line
        }, 100);
    }

    /**
     * Initialize the plugin
     */
    function init() {
        // Process initial content
        processPlaceholders(document.body);
        processConditionalContent(document.body);
        processInputFieldPlaceholders(document.body); // Added this line

        // Set up MutationObserver for dynamic content
        if (window.MutationObserver) {
            const observer = new MutationObserver(mutations => {
                let shouldProcess = false;

                for (const mutation of mutations) {
                    if (mutation.addedNodes.length) {
                        for (const node of mutation.addedNodes) {
                            if (node.nodeType === Node.ELEMENT_NODE) {
                                // Check if the node itself is a placeholder/conditional or contains them
                                if (node.matches && (
                                    node.matches('.user-ip-placeholder') || 
                                    node.matches('.user-ip-conditional') ||
                                    node.matches('input[value*="user-ip-placeholder"]') ||
                                    node.matches('textarea')
                                )) {
                                    shouldProcess = true;
                                    break;
                                } else if (node.querySelector && (
                                    node.querySelector('.user-ip-placeholder') || 
                                    node.querySelector('.user-ip-conditional') ||
                                    node.querySelector('input[value*="user-ip-placeholder"]') ||
                                    node.querySelector('textarea')
                                )) {
                                    shouldProcess = true;
                                    break;
                                }
                            }
                        }
                    }
                    if (shouldProcess) break;
                }

                if (shouldProcess) {
                    debouncedProcess(document.body);
                }
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });

            if (CONFIG.DEBUG) console.log('UserIPLocation: MutationObserver initialized');
        }

        // Expose API for debugging/testing
        if (CONFIG.DEBUG) {
            window.userIPLocationAPI = apiManager;
        }
        
        // Expose debugging functions for OptimizePress compatibility
        window.userIPLocationDebug = {
            processInputFields: () => processInputFieldPlaceholders(document.body),
            findInputsWithPlaceholders: () => {
                const inputs = document.querySelectorAll('input[value*="user-ip-placeholder"]');
                const textareas = Array.from(document.querySelectorAll('textarea')).filter(t => 
                    t.value && t.value.includes('user-ip-placeholder')
                );
                console.log('Found inputs with placeholders:', inputs);
                console.log('Found textareas with placeholders:', textareas);
                return [...inputs, ...textareas];
            },
            enableDebug: () => {
                CONFIG.DEBUG = true;
                console.log('UserIPLocation: Debug mode enabled');
            }
        };
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    if (CONFIG.DEBUG) console.log('UserIPLocation: Cache-compatible script loaded');
})(); 