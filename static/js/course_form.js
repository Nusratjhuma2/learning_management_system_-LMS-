/* ===== COURSE FORM PAGE JS — Live Pricing & Discount Preview ===== */
document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    var isFreeToggle = document.getElementById('id_is_free');
    var pricingContainer = document.getElementById('pricingFieldsContainer');
    var priceInput = document.getElementById('id_price');
    var discountPriceInput = document.getElementById('id_discount_price');

    var livePricingPreview = document.getElementById('livePricingPreview');
    var previewEffectivePrice = document.getElementById('previewEffectivePrice');
    var previewOriginalPrice = document.getElementById('previewOriginalPrice');
    var previewDiscountBadge = document.getElementById('previewDiscountBadge');
    var previewSavings = document.getElementById('previewSavings');
    var pricingAlert = document.getElementById('pricingAlert');

    function updatePricingState() {
        if (!isFreeToggle) return;
        var isFree = isFreeToggle.checked;

        if (isFree) {
            if (pricingContainer) pricingContainer.style.opacity = '0.5';
            if (priceInput) priceInput.disabled = true;
            if (discountPriceInput) discountPriceInput.disabled = true;
            if (livePricingPreview) livePricingPreview.classList.add('d-none');
            if (pricingAlert) pricingAlert.classList.add('d-none');
        } else {
            if (pricingContainer) pricingContainer.style.opacity = '1';
            if (priceInput) priceInput.disabled = false;
            if (discountPriceInput) discountPriceInput.disabled = false;
            calculateLivePricing();
        }
    }

    function calculateLivePricing() {
        if (!priceInput || (isFreeToggle && isFreeToggle.checked)) return;

        var price = parseFloat(priceInput.value) || 0;
        var discountPrice = parseFloat(discountPriceInput ? discountPriceInput.value : 0) || 0;

        if (pricingAlert) {
            pricingAlert.classList.add('d-none');
            pricingAlert.textContent = '';
        }

        if (price <= 0) {
            if (livePricingPreview) livePricingPreview.classList.add('d-none');
            return;
        }

        if (livePricingPreview) livePricingPreview.classList.remove('d-none');

        if (discountPrice > 0) {
            if (discountPrice >= price) {
                if (pricingAlert) {
                    pricingAlert.textContent = 'Promotional discount price ($' + discountPrice.toFixed(2) + ') must be strictly lower than standard price ($' + price.toFixed(2) + ').';
                    pricingAlert.classList.remove('d-none');
                }
                if (previewEffectivePrice) previewEffectivePrice.textContent = '$' + price.toFixed(2);
                if (previewOriginalPrice) previewOriginalPrice.classList.add('d-none');
                if (previewDiscountBadge) previewDiscountBadge.classList.add('d-none');
                if (previewSavings) previewSavings.classList.add('d-none');
            } else {
                var savings = (price - discountPrice).toFixed(2);
                var percent = Math.round(((price - discountPrice) / price) * 100);

                if (previewEffectivePrice) previewEffectivePrice.textContent = '$' + discountPrice.toFixed(2);
                if (previewOriginalPrice) {
                    previewOriginalPrice.textContent = '$' + price.toFixed(2);
                    previewOriginalPrice.classList.remove('d-none');
                }
                if (previewDiscountBadge) {
                    previewDiscountBadge.textContent = percent + '% OFF';
                    previewDiscountBadge.classList.remove('d-none');
                }
                if (previewSavings) {
                    previewSavings.textContent = 'Save $' + savings;
                    previewSavings.classList.remove('d-none');
                }
            }
        } else {
            if (previewEffectivePrice) previewEffectivePrice.textContent = '$' + price.toFixed(2);
            if (previewOriginalPrice) previewOriginalPrice.classList.add('d-none');
            if (previewDiscountBadge) previewDiscountBadge.classList.add('d-none');
            if (previewSavings) previewSavings.classList.add('d-none');
        }
    }

    if (isFreeToggle) {
        isFreeToggle.addEventListener('change', updatePricingState);
    }
    if (priceInput) {
        priceInput.addEventListener('input', calculateLivePricing);
    }
    if (discountPriceInput) {
        discountPriceInput.addEventListener('input', calculateLivePricing);
    }

    // Initialize state on page load
    updatePricingState();
});
