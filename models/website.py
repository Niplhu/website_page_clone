from odoo import models


class Website(models.Model):
    _inherit = "website"

    def action_open_clone_wizard(self):
        self.ensure_one()
        action = self.env.ref("website_page_clone.action_website_clone_wizard").read()[0]
        action["context"] = {
            "active_model": "website",
            "active_id": self.id,
            "active_ids": [self.id],
            "default_source_mode": "complete",
            "default_source_website_id": self.id,
        }
        return action
