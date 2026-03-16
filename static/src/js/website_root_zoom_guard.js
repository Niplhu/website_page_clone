/** @odoo-module **/

import { WebsiteRoot } from "@website/js/content/website_root";

if (WebsiteRoot && typeof WebsiteRoot.include === "function") {
    WebsiteRoot.include({
        start() {
            const $zoomableImages = this.$('.zoomable img[data-zoom]');
            if ($zoomableImages && typeof $zoomableImages.zoomOdoo !== "function") {
                const proto = $zoomableImages.constructor && $zoomableImages.constructor.prototype;
                if (proto && typeof proto.zoomOdoo !== "function") {
                    proto.zoomOdoo = function () {
                        return this;
                    };
                }
            }
            return this._super(...arguments);
        },
    });
}
