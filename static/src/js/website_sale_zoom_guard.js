/** @odoo-module **/

import { WebsiteSale } from "@website_sale/js/website_sale";

if (WebsiteSale && typeof WebsiteSale.include === "function") {
    WebsiteSale.include({
        _ensureZoomOdooPlugin() {
            const candidates = [];
            const global$ = window.jQuery || window.$;

            if (global$ && global$.fn) {
                candidates.push(global$.fn);
            }
            if (this.$el && this.$el.constructor && this.$el.constructor.prototype) {
                candidates.push(this.$el.constructor.prototype);
            }

            for (const proto of candidates) {
                if (typeof proto.zoomOdoo !== "function") {
                    proto.zoomOdoo = function () {
                        return this;
                    };
                }
            }
        },

        _startZoom() {
            this._ensureZoomOdooPlugin();
            return this._super(...arguments);
        },
    });
}
