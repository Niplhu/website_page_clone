from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WebsiteCloneWizard(models.TransientModel):
    _name = "website.clone.wizard"
    _description = "Asistente de clonado de sitios web"

    source_website_id = fields.Many2one("website", required=True, string="Sitio web origen")

    target_mode = fields.Selection(
        [("existing", "Sitio existente"), ("new", "Crear sitio nuevo")],
        default="new",
        required=True,
        string="Modo destino",
    )
    target_website_id = fields.Many2one("website", string="Sitio web destino")

    new_website_name = fields.Char(string="Nombre del nuevo sitio")
    new_website_domain = fields.Char(string="Dominio del nuevo sitio")
    new_website_company_id = fields.Many2one("res.company", string="Compania del nuevo sitio")

    clone_ecommerce = fields.Boolean(default=True, string="Clonar configuracion ecommerce")
    copy_translations = fields.Boolean(default=True, string="Copiar traducciones")
    replace_target_content = fields.Boolean(
        default=True,
        string="Reemplazar contenido del destino",
        help="Si se activa, se reemplazan las paginas, menus, vistas QWeb especificas del sitio y redirecciones del destino.",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        active_model = self.env.context.get("active_model")
        active_id = self.env.context.get("active_id")

        if not values.get("source_website_id") and active_model == "website" and active_id:
            values["source_website_id"] = active_id
        elif not values.get("source_website_id") and active_model == "website.page" and active_id:
            page = self.env["website.page"].sudo().browse(active_id)
            values["source_website_id"] = page.website_id.id

        source_website = self.env["website"].browse(values.get("source_website_id"))
        if source_website:
            values.setdefault("new_website_name", _("%s (Copia)") % source_website.name)
            if "company_id" in source_website._fields:
                values.setdefault("new_website_company_id", source_website.company_id.id)
        return values

    @api.onchange("source_website_id")
    def _onchange_source_website_id(self):
        for wizard in self:
            if not wizard.source_website_id:
                continue
            wizard.new_website_name = wizard.new_website_name or _("%s (Copia)") % wizard.source_website_id.name
            if "company_id" in wizard.source_website_id._fields and not wizard.new_website_company_id:
                wizard.new_website_company_id = wizard.source_website_id.company_id

    def _create_target_website(self):
        self.ensure_one()
        if not (self.new_website_name or "").strip():
            raise UserError(_("El nombre es obligatorio para crear el nuevo sitio web."))

        values = {"name": self.new_website_name.strip()}
        if "company_id" in self.env["website"]._fields:
            values["company_id"] = (
                self.new_website_company_id.id
                if self.new_website_company_id
                else self.source_website_id.company_id.id
            )
        if self.new_website_domain:
            values["domain"] = self.new_website_domain.strip()

        return self.env["website"].sudo().create(values)

    def action_clone(self):
        self.ensure_one()
        if not self.source_website_id:
            raise UserError(_("Selecciona un sitio web origen."))

        if self.target_mode == "existing":
            if not self.target_website_id:
                raise UserError(_("Selecciona un sitio web destino."))
            target_website = self.target_website_id.sudo()
        else:
            target_website = self._create_target_website()

        result = self.env["website.clone.service"].clone_website(
            source_website=self.source_website_id,
            target_website=target_website,
            copy_translations=self.copy_translations,
            clone_ecommerce=self.clone_ecommerce,
            replace_target_content=self.replace_target_content,
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sitio web clonado"),
                "message": _("%s paginas clonadas en %s.") % (result["pages"], result["target_website"].name),
                "type": "success",
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": "website",
                    "res_id": result["target_website"].id,
                    "views": [[False, "form"]],
                    "view_mode": "form",
                },
            },
        }
