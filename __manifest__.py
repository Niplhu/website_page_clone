{
    "name": "Clonador de Sitios Web 1:1",
    "summary": "Clona sitios web y configuracion ecommerce en la misma base de datos",
    "version": "18.0.2.0.0",
    "category": "Website/Website",
    "author": "Foredu Solutions S.L.",
    "license": "LGPL-3",
    "depends": ["website", "website_sale"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/website_clone_wizard_views.xml",
        "views/website_clone_actions.xml",
    ],
    "installable": True,
    "application": False,
}
