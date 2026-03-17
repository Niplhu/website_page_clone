from odoo import models


class WebsitePage(models.Model):
    _inherit = "website.page"

    def action_open_clone_wizard(self):
        self.ensure_one()
        action = self.env.ref("website_page_clone.action_website_page_clone_wizard").read()[0]
        action["context"] = {
<<<<<<< HEAD
            "active_model": "website.page",
            "active_id": self.id,
            "default_source_page_id": self.id,
=======
>>>>>>> ac08f3c837d4f92a32837a5bd9fb1484fd2b5893
            "default_source_website_id": self.website_id.id,
            "default_target_website_id": self.website_id.id,
        }
        return action
