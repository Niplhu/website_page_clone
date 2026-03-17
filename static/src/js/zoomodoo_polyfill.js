/** @odoo-module **/

(function () {
    "use strict";

    const patchedFns = new WeakSet();

    const patchProto = (proto, dollarFn) => {
        if (!proto) {
            return;
        }
        if (typeof proto.hasScrollableContent !== "function") {
            proto.hasScrollableContent = function () {
                return !!(this.length && this[0].scrollHeight > this[0].clientHeight);
            };
        }
        if (typeof proto.isScrollable !== "function") {
            proto.isScrollable = function () {
                if (!this.length) {
                    return false;
                }
                const overflow = this.css ? this.css("overflow-y") : "visible";
                const el = this[0];
                const doc = el && el.ownerDocument;
                const scrollingEl = doc && doc.scrollingElement;
                return overflow === "auto" || overflow === "scroll" || (overflow === "visible" && el === scrollingEl);
            };
        }
        if (typeof proto.getScrollingElement !== "function") {
            proto.getScrollingElement = function (doc = window.document) {
                const scrollingEl = doc.scrollingElement || doc.documentElement || doc.body;
                return dollarFn(scrollingEl);
            };
        }
        if (typeof proto.getScrollingTarget !== "function") {
            proto.getScrollingTarget = function (contextItem = window.document) {
                const isElement = (obj) => obj && obj.nodeType === Node.ELEMENT_NODE;
                const isJQueryLike = (obj) => obj && ("jquery" in obj);
                const $scrollingElement = isElement(contextItem)
                    ? dollarFn(contextItem)
                    : isJQueryLike(contextItem)
                    ? contextItem
                    : dollarFn().getScrollingElement(contextItem);
                const doc = $scrollingElement[0] && $scrollingElement[0].ownerDocument;
                if (!doc) {
                    return $scrollingElement;
                }
                return $scrollingElement.is(doc.scrollingElement)
                    ? dollarFn(doc.defaultView)
                    : $scrollingElement;
            };
        }
        if (typeof proto.zoomOdoo !== "function") {
            proto.zoomOdoo = function () {
                return this;
            };
        }
    };

    const patchDollarFn = (dollarFn) => {
        if (typeof dollarFn !== "function" || patchedFns.has(dollarFn)) {
            return;
        }
        const protos = new Set();
        if (dollarFn.fn) {
            protos.add(dollarFn.fn);
        }
        if (dollarFn.prototype) {
            protos.add(dollarFn.prototype);
        }
        try {
            const instance = dollarFn();
            if (instance && instance.constructor && instance.constructor.prototype) {
                protos.add(instance.constructor.prototype);
            }
        } catch (_err) {
            // Ignore probing errors and patch available prototypes only.
        }
        for (const proto of protos) {
            patchProto(proto, dollarFn);
        }
        patchedFns.add(dollarFn);
    };

    const installGlobalWatcher = (globalName) => {
        let currentValue = window[globalName];
        if (typeof currentValue === "function") {
            patchDollarFn(currentValue);
        }
        try {
            Object.defineProperty(window, globalName, {
                configurable: true,
                enumerable: true,
                get() {
                    return currentValue;
                },
                set(value) {
                    currentValue = value;
                    if (typeof value === "function") {
                        patchDollarFn(value);
                        if (!window.$ && globalName === "jQuery") {
                            window.$ = value;
                        }
                        if (!window.jQuery && globalName === "$") {
                            window.jQuery = value;
                        }
                    }
                },
            });
        } catch (_err) {
            // If redefining globals fails, polling fallback below will still patch.
        }
    };

    const applyPolyfill = () => {
        const functionsToPatch = [window.jQuery, window.$].filter((fn) => typeof fn === "function");
        if (!functionsToPatch.length) {
            return false;
        }

        for (const dollarFn of functionsToPatch) {
            patchDollarFn(dollarFn);
        }
        return true;
    };

    installGlobalWatcher("jQuery");
    installGlobalWatcher("$");

    let attempts = 0;
    const maxAttempts = 1200;
    const timer = window.setInterval(function () {
        attempts += 1;
        if (applyPolyfill() || attempts >= maxAttempts) {
            window.clearInterval(timer);
        }
    }, 50);

    applyPolyfill();
})();
