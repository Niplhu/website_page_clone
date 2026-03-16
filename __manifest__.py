{
    "name": "Clonador de paginas web",
    "summary": "Clona paginas web y configuracion de eCommerce entre sitios",
    "version": "18.0.1.0.0",
    "category": "Website/Website",
    "author": "Foredu Solutions S.L.",
    "license": "LGPL-3",
    "depends": ["website", "website_sale"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/website_page_clone_wizard_views.xml",
        "views/website_page_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            ("prepend", "website_page_clone/static/src/js/zoomodoo_polyfill.js"),
            "website_page_clone/static/src/js/website_root_zoom_guard.js",
            "website_page_clone/static/src/js/website_sale_zoom_guard.js",
        ],
        "web.assets_frontend_lazy": [
            ("prepend", "website_page_clone/static/src/js/zoomodoo_polyfill.js"),
            "website_page_clone/static/src/js/website_root_zoom_guard.js",
            "website_page_clone/static/src/js/website_sale_zoom_guard.js",
        ],
    },
    "installable": True,
    "application": False,
}
