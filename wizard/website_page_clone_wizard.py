import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class WebsitePageCloneWizard(models.TransientModel):
    _name = "website.page.clone.wizard"
    _description = "Asistente de clonado de paginas web"

    source_mode = fields.Selection(
        [("custom", "Custom"), ("complete", "Completa")],
        default="custom",
        required=True,
        string="Modo origen",
    )
    source_page_id = fields.Many2one("website.page", string="Pagina origen")
    source_website_id = fields.Many2one("website", string="Sitio web donante")
    target_mode = fields.Selection(
        [("existing", "Sitio existente"), ("new", "Crear sitio nuevo")],
        default="existing",
        required=True,
        string="Modo destino",
    )
    target_website_id = fields.Many2one("website", string="Sitio destino")
    new_website_name = fields.Char(string="Nombre del nuevo sitio")
    new_website_domain = fields.Char(string="Dominio del nuevo sitio")
    new_website_company_id = fields.Many2one("res.company", string="Compania del nuevo sitio")
    new_name = fields.Char(string="Nuevo nombre de pagina")
    new_url = fields.Char(string="Nueva URL")

    copy_menu = fields.Boolean(default=True, string="Copiar menus")
    copy_seo = fields.Boolean(default=True, string="Copiar SEO")
    copy_translations = fields.Boolean(default=True, string="Copiar traducciones")
    copy_shop = fields.Boolean(default=True, string="Clonar tienda")
    copy_shop_settings = fields.Boolean(default=True, string="Clonar ajustes de tienda")
    copy_shop_pricelists = fields.Boolean(default=True, string="Clonar tarifas")
    copy_shop_categories = fields.Boolean(default=True, string="Clonar categorias de tienda")
    copy_shop_products = fields.Boolean(default=True, string="Clonar productos de tienda")
    publish = fields.Boolean(default=False, string="Publicar pagina clonada")

    @api.model
    def _get_context_source_page_id(self):
        ctx = self.env.context
        if ctx.get("active_model") != "website.page":
            return False

        active_ids = [page_id for page_id in (ctx.get("active_ids") or []) if page_id]
        if len(active_ids) > 1:
            raise UserError(_(
                "Debes seleccionar una unica pagina origen para abrir el asistente de clonacion."
            ))
        if len(active_ids) == 1:
            return active_ids[0]
        return ctx.get("active_id") or False

    @api.model
    def _get_context_source_website_id(self):
        ctx = self.env.context
        if ctx.get("active_model") != "website":
            return False

        active_ids = [website_id for website_id in (ctx.get("active_ids") or []) if website_id]
        if len(active_ids) > 1:
            raise UserError(_(
                "Debes seleccionar un unico sitio web origen para abrir el asistente de clonacion."
            ))
        if len(active_ids) == 1:
            return active_ids[0]
        return ctx.get("active_id") or False

    @api.model
    def default_get(self, field_list):
        vals = super().default_get(field_list)
        source_page_id = vals.get("source_page_id") or self.env.context.get("default_source_page_id")
        source_website_id = vals.get("source_website_id") or self.env.context.get("default_source_website_id")
        context_source_page_id = self._get_context_source_page_id()
        context_source_website_id = self._get_context_source_website_id()

        if not source_website_id and context_source_website_id:
            source_website_id = context_source_website_id
            vals.setdefault("source_website_id", source_website_id)
            vals.setdefault("source_mode", "complete")
            vals.setdefault("copy_shop", True)
            vals.setdefault("copy_shop_settings", True)
            vals.setdefault("copy_shop_pricelists", True)
            vals.setdefault("copy_shop_categories", True)
            vals.setdefault("copy_shop_products", True)

        if vals.get("source_mode") == "complete":
            vals["source_page_id"] = False

        if not source_page_id and context_source_page_id:
            source_page_id = context_source_page_id
            vals.setdefault("source_page_id", source_page_id)

        if source_page_id:
            source_page = self.env["website.page"].sudo().browse(source_page_id).exists()
            if not source_page:
                raise UserError(_("La pagina origen seleccionada ya no existe."))
            vals.setdefault("source_website_id", source_page.website_id.id)
            vals.setdefault("new_name", _("%s (Copia)") % source_page.name)
            vals.setdefault("new_url", self._get_unique_url(source_page.url or "/new-page", vals.get("target_website_id") or source_page.website_id.id))
            if "is_published" in source_page._fields:
                vals.setdefault("publish", bool(source_page.is_published))

        source_website = self.env["website"].browse(vals.get("source_website_id") or source_website_id)
        if source_website:
            vals.setdefault("new_website_name", _("%s (Copia)") % source_website.name)
            if "company_id" in source_website._fields:
                vals.setdefault("new_website_company_id", source_website.company_id.id)
        return vals

    @api.onchange("source_page_id", "target_website_id")
    def _onchange_source_page(self):
        for wizard in self:
            if not wizard.source_page_id:
                continue
            if wizard.source_mode == "custom":
                wizard.source_website_id = wizard.source_page_id.website_id
            wizard.new_name = wizard.new_name or _("%s (Copia)") % wizard.source_page_id.name
            wizard.new_website_name = wizard.new_website_name or _("%s (Copia)") % wizard.source_page_id.website_id.name
            if "company_id" in wizard.source_page_id.website_id._fields and not wizard.new_website_company_id:
                wizard.new_website_company_id = wizard.source_page_id.website_id.company_id
            base_url = wizard.source_page_id.url or "/new-page"
            target_website_id = wizard.target_website_id.id or wizard.source_page_id.website_id.id
            wizard.new_url = wizard._get_unique_url(base_url, target_website_id)

    @api.onchange("source_mode")
    def _onchange_source_mode(self):
        for wizard in self:
            if wizard.source_mode == "complete":
                if wizard.source_page_id and not wizard.source_website_id:
                    wizard.source_website_id = wizard.source_page_id.website_id
                wizard.source_page_id = False
                wizard.target_mode = "new"
                wizard.target_website_id = False
                wizard.new_name = False
                wizard.new_url = False
                wizard.copy_shop = True
                wizard.copy_shop_settings = True
                wizard.copy_shop_pricelists = True
                wizard.copy_shop_categories = True
                wizard.copy_shop_products = True
                if wizard.source_website_id:
                    wizard.new_website_name = _("%s (Copia)") % wizard.source_website_id.name
                    if "company_id" in wizard.source_website_id._fields:
                        wizard.new_website_company_id = wizard.source_website_id.company_id
                continue

            if wizard.source_page_id:
                wizard.source_website_id = wizard.source_page_id.website_id

    @api.onchange("source_website_id")
    def _onchange_source_website(self):
        for wizard in self:
            if not wizard.source_website_id:
                continue

            if wizard.source_mode == "custom":
                if wizard.source_page_id and wizard.source_page_id.website_id != wizard.source_website_id:
                    wizard.source_page_id = False
            else:
                wizard.source_page_id = False
                wizard.new_website_name = _("%s (Copia)") % wizard.source_website_id.name
                if "company_id" in wizard.source_website_id._fields:
                    wizard.new_website_company_id = wizard.source_website_id.company_id

    @api.constrains("source_mode", "source_page_id", "source_website_id", "target_mode", "target_website_id")
    def _check_clone_scope(self):
        for wizard in self:
            if wizard.source_mode == "custom" and not wizard.source_page_id:
                raise UserError(_("La pagina origen es obligatoria en modo custom."))
            if wizard.source_mode == "complete" and not wizard.source_website_id:
                raise UserError(_("El sitio web donante es obligatorio en modo completa."))
            if wizard.source_mode == "complete" and wizard.target_mode == "existing":
                raise UserError(_(
                    "Para garantizar un clon 1:1 del sitio web completo, el destino debe ser un sitio nuevo."
                ))

    def _resolve_source_page(self):
        self.ensure_one()
        source_page = self.source_page_id.sudo().exists()
        if not source_page:
            raise UserError(_("Debes seleccionar una pagina origen valida."))
        if self.source_website_id and source_page.website_id != self.source_website_id:
            raise UserError(_(
                "La pagina seleccionada no pertenece al sitio web donante indicado."
            ))
        return source_page

    def _resolve_source_view(self, source_page):
        self.ensure_one()
        source_page.ensure_one()
        source_view = source_page.view_id.sudo().exists()
        if not source_view:
            raise UserError(_("La pagina seleccionada no tiene una vista asociada."))
        if "page_ids" in source_view._fields and source_view.page_ids and source_page not in source_view.page_ids:
            raise UserError(_(
                "La vista asociada no corresponde con la pagina seleccionada."
            ))
        return source_view

    def _resolve_source_website(self):
        self.ensure_one()
        if self.source_mode == "complete":
            source_website = self.source_website_id.sudo().exists()
            if not source_website:
                raise UserError(_("Debes seleccionar un sitio web donante valido."))
            return source_website
        return self._resolve_source_page().website_id.sudo()

    def _cleanup_new_website_pages(self, target_website):
        page_model = self.env["website.page"].sudo()
        menu_model = self.env["website.menu"].sudo()

        pages = page_model.search([("website_id", "=", target_website.id)])
        if pages:
            menus = menu_model.search(
                [
                    ("website_id", "=", target_website.id),
                    "|",
                    ("page_id", "in", pages.ids),
                    "&",
                    ("url", "=", "/"),
                    ("parent_id", "!=", False),
                ]
            )
            if menus:
                menus.unlink()
            pages.unlink()

    def _clone_single_page(self, source_page, target_website, name=None, url=None, publish=None):
        source_view = self._resolve_source_view(source_page)
        new_view = self._copy_view(source_page, target_website, source_view=source_view)
        desired_url = url or source_page.url or "/new-page"
        final_url = self._get_unique_url(desired_url, target_website.id)

        page_vals = {
            "name": name or source_page.name,
            "url": final_url,
            "website_id": target_website.id,
            "view_id": new_view.id,
        }

        if "is_published" in source_page._fields:
            page_vals["is_published"] = bool(source_page.is_published if publish is None else publish)

        target_page = self.env["website.page"].sudo().create(page_vals)

        if "page_ids" in new_view._fields:
            new_view.write({"page_ids": [(6, 0, [target_page.id])]})

        if self.copy_seo:
            self._apply_seo_values(source_page, target_page)
        if self.copy_menu:
            self._copy_menus(source_page, target_page, target_website)
        if self.copy_translations:
            self._copy_translations(source_page, target_page, source_view, new_view)

        return target_page

    def _create_target_website(self, source_website):
        if not (self.new_website_name or "").strip():
            raise UserError(_("El nombre del nuevo sitio es obligatorio al crear un sitio web nuevo."))

        website_model = self.env["website"].sudo()
        vals = {"name": self.new_website_name.strip()}

        if "domain" in website_model._fields and self.new_website_domain:
            vals["domain"] = self.new_website_domain.strip()

        if "company_id" in website_model._fields:
            company_id = self.new_website_company_id.id if self.new_website_company_id else source_website.company_id.id
            vals["company_id"] = company_id

        return website_model.create(vals)

    def _cleanup_new_website_home(self, target_website):
        page_model = self.env["website.page"].sudo()
        menu_model = self.env["website.menu"].sudo()

        default_home_pages = page_model.search(
            [("website_id", "=", target_website.id), ("url", "=", "/")]
        )
        if not default_home_pages:
            return

        home_page_ids = default_home_pages.ids
        home_menus = menu_model.search(
            [
                ("website_id", "=", target_website.id),
                "|",
                ("page_id", "in", home_page_ids),
                "&",
                ("url", "=", "/"),
                ("parent_id", "!=", False),
            ]
        )

        if home_menus:
            home_menus.unlink()
        default_home_pages.unlink()

    def _slugify(self, value):
        slug = (value or "").strip().lower().replace(" ", "-")
        filtered = [ch for ch in slug if ch.isalnum() or ch in ("-", "_", "/")]
        result = "".join(filtered)
        if not result.startswith("/"):
            result = "/%s" % result if result else "/new-page"
        return result

    def _get_unique_url(self, desired_url, website_id):
        page_model = self.env["website.page"].sudo()
        base = self._slugify(desired_url)
        candidate = base
        index = 1
        while page_model.search_count([("url", "=", candidate), ("website_id", "=", website_id)]):
            index += 1
            candidate = "%s-%s" % (base, index)
        return candidate

    def _get_unique_view_key(self, source_view, website_id):
        view_model = self.env["ir.ui.view"].sudo()
        root_key = source_view.key or "website_page_clone.view"
        key = "%s.clone_%s" % (root_key, website_id)
        index = 1
        while view_model.search_count([("key", "=", key)]):
            index += 1
            key = "%s.clone_%s_%s" % (root_key, website_id, index)
        return key

    def _copy_view(self, source_page, target_website, source_view=None):
        source_view = (source_view or source_page.view_id).sudo().exists()
        if not source_view:
            raise UserError(_("La pagina seleccionada no tiene una vista asociada."))

        defaults = {
            "name": _("%s (Copia)") % (source_view.name or source_page.name),
            "key": self._get_unique_view_key(source_view, target_website.id),
        }
        if "website_id" in source_view._fields:
            defaults["website_id"] = target_website.id
        if "page_ids" in source_view._fields:
            defaults["page_ids"] = [(5, 0, 0)]

        return source_view.copy(default=defaults)

    def _apply_seo_values(self, source_page, target_page):
        seo_fields = [
            "website_meta_title",
            "website_meta_description",
            "website_meta_keywords",
            "seo_name",
            "website_meta_og_img",
            "website_indexed",
        ]
        values = {}
        for field_name in seo_fields:
            if field_name in source_page._fields and field_name in target_page._fields:
                values[field_name] = source_page[field_name]
        if values:
            target_page.write(values)

    def _find_root_menu(self, website):
        return self.env["website.menu"].sudo().search(
            [("website_id", "=", website.id), ("parent_id", "=", False)],
            order="sequence,id",
            limit=1,
        )

    def _find_parent_menu_candidate(self, source_parent, target_website):
        menu_model = self.env["website.menu"].sudo()
        if not source_parent:
            return self._find_root_menu(target_website)

        parent_domain = [("website_id", "=", target_website.id), ("name", "=", source_parent.name)]

        if source_parent.url:
            menu = menu_model.search(parent_domain + [("url", "=", source_parent.url)], limit=1)
            if menu:
                return menu

        return menu_model.search(parent_domain, order="sequence,id", limit=1) or self._find_root_menu(target_website)

    def _copy_menus(self, source_page, target_page, target_website):
        menu_model = self.env["website.menu"].sudo()
        source_menus = menu_model.search(
            [("website_id", "=", source_page.website_id.id), ("page_id", "=", source_page.id)],
            order="parent_id,sequence,id",
        )
        for source_menu in source_menus:
            parent_menu = self._find_parent_menu_candidate(source_menu.parent_id, target_website)
            vals = {
                "name": source_menu.name,
                "website_id": target_website.id,
                "parent_id": parent_menu.id if parent_menu else False,
                "sequence": source_menu.sequence,
                "page_id": target_page.id,
            }
            if "new_window" in source_menu._fields:
                vals["new_window"] = source_menu.new_window
            menu_model.create(vals)

    def _translation_lang_codes(self):
        langs = self.env["res.lang"].sudo().search([("active", "=", True)])
        return langs.mapped("code")

    def _copy_translated_field_values(self, source_record, target_record, field_name):
        if field_name not in source_record._fields or field_name not in target_record._fields:
            return

        source_field = source_record._fields[field_name]
        target_field = target_record._fields[field_name]
        if not getattr(source_field, "translate", False):
            return
        if getattr(target_field, "readonly", False):
            return

        for lang_code in self._translation_lang_codes():
            value = source_record.with_context(lang=lang_code)[field_name]
            target_record.with_context(lang=lang_code).write({field_name: value})

    def _copy_model_translations(self, source_record, target_record):
        for field_name, field in source_record._fields.items():
            if not getattr(field, "translate", False):
                continue
            if field_name not in target_record._fields:
                continue
            self._copy_translated_field_values(source_record, target_record, field_name)

    def _copy_translations(self, source_page, target_page, source_view, target_view):
        self._copy_model_translations(source_page, target_page)
        self._copy_translated_field_values(source_view, target_view, "arch_db")

    def _website_setting_blacklist(self):
        return {
            "id",
            "name",
            "domain",
            "company_id",
            "homepage_url",
            "menu_id",
            "home_menu_id",
            "homepage_menu_id",
            "create_uid",
            "create_date",
            "write_uid",
            "write_date",
            "__last_update",
        }

    def _copy_website_settings(self, source_website, target_website):
        vals = {}
        blacklist = self._website_setting_blacklist()
        for field_name, target_field in target_website._fields.items():
            source_field = source_website._fields.get(field_name)
            if not source_field or field_name in blacklist:
                continue
            if getattr(target_field, "readonly", False) or getattr(target_field, "compute", False):
                continue
            if getattr(target_field, "related", False):
                continue
            if target_field.type == "one2many":
                continue
            if target_field.type == "many2one":
                vals[field_name] = source_website[field_name].id or False
            elif target_field.type == "many2many":
                vals[field_name] = [(6, 0, source_website[field_name].ids)]
            else:
                vals[field_name] = source_website[field_name]
        if vals:
            target_website.sudo().write(vals)
        _logger.info(
            "Website settings cloned: source_website_id=%s target_website_id=%s fields=%s",
            source_website.id,
            target_website.id,
            len(vals),
        )

    def _clone_website_rewrites(self, source_website, target_website):
        if "website.rewrite" not in self.env:
            return

        rewrite_model = self.env["website.rewrite"].sudo()
        source_rewrites = rewrite_model.search([("website_id", "=", source_website.id)])
        cloned = 0
        for source_rewrite in source_rewrites:
            defaults = {"website_id": target_website.id}
            duplicate = rewrite_model.search([
                ("website_id", "=", target_website.id),
                ("url_from", "=", source_rewrite.url_from),
            ], limit=1)
            if duplicate:
                duplicate.write({
                    "url_to": source_rewrite.url_to,
                    "redirect_type": source_rewrite.redirect_type,
                })
            else:
                source_rewrite.copy(default=defaults)
            cloned += 1
        _logger.info(
            "Website redirects cloned: source_website_id=%s target_website_id=%s count=%s",
            source_website.id,
            target_website.id,
            cloned,
        )

    def _collect_website_custom_views(self, source_website, include_shop=True):
        view_model = self.env["ir.ui.view"].sudo()
        domain = [("website_id", "=", source_website.id)]
        if "type" in view_model._fields:
            domain.append(("type", "=", "qweb"))

        source_views = view_model.search(domain, order="inherit_id,id")
        custom_views = view_model.browse()
        for view in source_views:
            if "page_ids" in view._fields and view.page_ids:
                continue
            if not include_shop and self._is_shop_related_view(view):
                continue
            custom_views |= view
        return custom_views

    def _cleanup_target_website_views(self, target_website, include_shop=True):
        target_views = self._collect_website_custom_views(target_website, include_shop=include_shop)
        if target_views:
            target_views.unlink()

    def _clone_website_custom_views(self, source_website, target_website, include_shop=True):
        source_views = self._collect_website_custom_views(source_website, include_shop=include_shop)
        if not source_views:
            return

        source_ids = set(source_views.ids)

        def _depth(view):
            depth = 0
            parent = view.inherit_id
            while parent and parent.id in source_ids:
                depth += 1
                parent = parent.inherit_id
            return depth

        ordered_source_views = sorted(source_views, key=lambda view: (_depth(view), view.id))
        view_map = {}

        for source_view in ordered_source_views:
            defaults = {
                "website_id": target_website.id,
                "key": source_view.key,
            }
            if "page_ids" in source_view._fields:
                defaults["page_ids"] = [(5, 0, 0)]
            target_view = source_view.copy(default=defaults)
            view_map[source_view.id] = target_view

            if self.copy_translations and source_view.arch_db:
                self._copy_translated_field_values(source_view, target_view, "arch_db")

        for source_view in ordered_source_views:
            target_view = view_map[source_view.id]
            inherit_view = source_view.inherit_id
            if inherit_view and inherit_view.id in view_map:
                inherit_view = view_map[inherit_view.id]
            if inherit_view:
                target_view.write({"inherit_id": inherit_view.id})
        _logger.info(
            "Website custom views cloned: source_website_id=%s target_website_id=%s include_shop=%s count=%s",
            source_website.id,
            target_website.id,
            include_shop,
            len(ordered_source_views),
        )

    def _cleanup_target_website_menus(self, target_website):
        self.env["website.menu"].sudo().search([
            ("website_id", "=", target_website.id),
        ]).unlink()

    def _clone_complete_menu_tree(self, source_website, target_website, page_map):
        menu_model = self.env["website.menu"].sudo()
        source_menus = menu_model.search(
            [("website_id", "=", source_website.id)],
            order="parent_id,sequence,id",
        )
        menu_map = {}

        for source_menu in source_menus:
            parent_menu = menu_map.get(source_menu.parent_id.id)
            vals = {
                "name": source_menu.name,
                "website_id": target_website.id,
                "sequence": source_menu.sequence,
                "parent_id": parent_menu.id if parent_menu else False,
                "url": source_menu.url,
            }
            if source_menu.page_id:
                target_page = page_map.get(source_menu.page_id.id)
                vals["page_id"] = target_page.id if target_page else False
            if "new_window" in source_menu._fields:
                vals["new_window"] = source_menu.new_window
            if "is_visible" in source_menu._fields:
                vals["is_visible"] = source_menu.is_visible
            menu_map[source_menu.id] = menu_model.create(vals)
        _logger.info(
            "Website menus cloned: source_website_id=%s target_website_id=%s count=%s",
            source_website.id,
            target_website.id,
            len(source_menus),
        )

    def _clone_complete_pages(self, source_website, target_website):
        source_pages = self.env["website.page"].sudo().search(
            [("website_id", "=", source_website.id)],
            order="id",
        )
        if not source_pages:
            raise UserError(_("El sitio web donante seleccionado no tiene paginas para clonar."))

        page_map = {}
        target_page = self.env["website.page"]
        for source_page in source_pages:
            target_page = self._clone_single_page(source_page, target_website)
            page_map[source_page.id] = target_page
        _logger.info(
            "Website pages cloned: source_website_id=%s target_website_id=%s count=%s",
            source_website.id,
            target_website.id,
            len(source_pages),
        )
        return target_page, page_map

    def _shop_setting_fields(self):
        """Website fields cloned when `copy_shop_settings` is enabled.

        These are explicit website-level settings (not template toggle views).
        Toggle views are synchronized separately to avoid activating options
        that are not effectively enabled on the source website.
        """
        return [
            "add_to_cart_action",
            "account_on_checkout",
            "auth_signup_uninvited",
            "enabled_portal_reorder_button",
            "shop_ppg",
            "shop_ppr",
            "shop_default_sort",
            "shop_gap",
            "shop_placeholder_image",
            "shop_products_per_page",
            "shop_categories_order",
            "shop_page_size",
            "shop_b2b_pricelist",
            "prevent_zero_price_sale",
            "prevent_zero_price_sale_text",
            "show_line_subtotals_tax_selection",
            "contact_us_button_url",
            "cart_recovery_mail_template_id",
            "cart_abandoned_delay",
            "send_abandoned_cart_email",
            "salesperson_id",
            "product_page_image_layout",
            "product_page_image_width",
            "product_page_image_spacing",
            "product_page_grid_columns",
            "ecommerce_access",
            "currency_id",
            "pricelist_id",
            "pricelist_ids",
            "fiscal_position_id",
            "fiscal_position_ids",
            "payment_provider_ids",
            "delivery_carrier_ids",
            "salesteam_id",
        ]

    def _prepare_write_value(self, field, value):
        if field.type == "many2one":
            return value.id or False
        if field.type == "many2many":
            return [(6, 0, value.ids)]
        if field.type in ("one2many", "binary"):
            return False
        return value

    def _copy_shop_settings(self, source_website, target_website, pricelist_map=None):
        pricelist_map = pricelist_map or {}
        vals = {}
        for field_name in self._shop_setting_fields():
            source_field = source_website._fields.get(field_name)
            target_field = target_website._fields.get(field_name)
            if not source_field or not target_field:
                continue
            if getattr(target_field, "readonly", False) or getattr(target_field, "compute", False):
                continue

            if field_name in ("pricelist_id", "shop_b2b_pricelist") and target_field.type == "many2one":
                source_pricelist = source_website[field_name]
                mapped_pricelist = pricelist_map.get(source_pricelist.id)
                vals[field_name] = mapped_pricelist.id if mapped_pricelist else source_pricelist.id
                continue

            if field_name == "pricelist_ids" and target_field.type == "many2many":
                source_ids = source_website[field_name].ids
                mapped_ids = [pricelist_map[pid].id for pid in source_ids if pid in pricelist_map]
                vals[field_name] = [(6, 0, mapped_ids or source_ids)]
                continue

            prepared = self._prepare_write_value(target_field, source_website[field_name])
            if prepared is False and target_field.type in ("one2many", "binary"):
                continue
            vals[field_name] = prepared
        if vals:
            target_website.sudo().write(vals)

    def _shop_view_key_prefixes(self):
        return ("website_sale.", "website_payment.", "payment.")

    def _shop_toggle_view_keys(self):
        """Editor toggle views that must mirror *effective* active state."""
        return (
            "website_sale.extra_info",
            "website_sale.suggested_products_list",
            "website_sale.reduction_code",
            "website_sale.accept_terms_and_conditions",
            "website_sale.address_b2b",
            "website_sale.product_buy_now",
        )

    def _is_shop_toggle_view_key(self, key):
        return bool(key) and key in self._shop_toggle_view_keys()

    def _is_shop_related_view(self, view):
        prefixes = self._shop_view_key_prefixes()
        seen = set()
        current = view
        while current and current.id not in seen:
            seen.add(current.id)
            key = (current.key or "").strip()
            if key.startswith(prefixes):
                return True
            current = current.inherit_id
        return False

    def _collect_shop_custom_views(self, source_website):
        view_model = self.env["ir.ui.view"].sudo()
        domain = [("website_id", "=", source_website.id)]
        if "type" in view_model._fields:
            domain.append(("type", "=", "qweb"))

        source_views = view_model.search(domain, order="inherit_id,id")
        shop_views = view_model.browse()
        for view in source_views:
            if "page_ids" in view._fields and view.page_ids:
                continue
            if not self._is_shop_related_view(view):
                continue
            if self._is_shop_toggle_view_key(view.key):
                continue
            shop_views |= view
        return shop_views

    def _get_website_view_by_key(self, website, key):
        website_scoped = website.with_context(website_id=website.id)
        return website_scoped.viewref(key)

    def _get_website_specific_view_by_key(self, website, key):
        return self.env["ir.ui.view"].sudo().search(
            [
                ("website_id", "=", website.id),
                ("key", "=", key),
            ],
            limit=1,
        )

    def _ensure_target_website_view(self, target_website, key):
        """Return a website-specific view record for `key` on target website."""
        view_model = self.env["ir.ui.view"].sudo()
        website_view = view_model.search(
            [
                ("website_id", "=", target_website.id),
                ("key", "=", key),
            ],
            limit=1,
        )
        if website_view:
            return website_view

        base_view = self._get_website_view_by_key(target_website, key)
        if not base_view:
            return view_model

        return base_view.sudo().copy(default={
            "website_id": target_website.id,
            "key": key,
        })

    def _sync_shop_toggle_views(self, source_website, target_website):
        """Sync checkout/editor toggle options using effective source state.

        This prevents false positives where target keeps stale website views and
        ends up enabling options not active in source.
        """
        for key in self._shop_toggle_view_keys():
            # Prefer website-specific source customization; fallback to base view.
            source_view = self._get_website_specific_view_by_key(source_website, key)
            if not source_view:
                source_view = self._get_website_view_by_key(source_website, key)
            if not source_view:
                continue

            source_state = bool(
                source_website.with_context(website_id=source_website.id).is_view_active(key)
            )
            target_view = self._ensure_target_website_view(target_website, key)
            if target_view:
                write_vals = {
                    "name": source_view.name,
                    "priority": source_view.priority,
                    "active": source_state,
                }
                if source_view.arch_db:
                    write_vals["arch_db"] = source_view.arch_db
                target_view.write(write_vals)

                if self.copy_translations:
                    self._copy_translated_field_values(source_view, target_view, "arch_db")

    def _clone_shop_custom_views(self, source_website, target_website):
        source_views = self._collect_shop_custom_views(source_website)
        if not source_views:
            return

        self._cleanup_legacy_shop_clone_views(target_website)

        source_ids = set(source_views.ids)

        def _depth(view):
            depth = 0
            parent = view.inherit_id
            while parent and parent.id in source_ids:
                depth += 1
                parent = parent.inherit_id
            return depth

        ordered_source_views = sorted(source_views, key=lambda view: (_depth(view), view.id))
        view_map = {}

        for source_view in ordered_source_views:
            target_view = self.env["ir.ui.view"].sudo().search(
                [
                    ("website_id", "=", target_website.id),
                    ("key", "=", source_view.key),
                ],
                limit=1,
            )

            if target_view:
                write_vals = {
                    "name": source_view.name,
                    "priority": source_view.priority,
                    "active": source_view.active,
                }
                if source_view.arch_db:
                    write_vals["arch_db"] = source_view.arch_db
                target_view.write(write_vals)
            else:
                target_view = source_view.copy(default={
                    "website_id": target_website.id,
                    "key": source_view.key,
                })

            view_map[source_view.id] = target_view

            if self.copy_translations:
                self._copy_translated_field_values(source_view, target_view, "arch_db")

        for source_view in ordered_source_views:
            inherit_view = source_view.inherit_id
            if inherit_view.id in view_map:
                inherit_view = view_map[inherit_view.id]
            if inherit_view:
                view_map[source_view.id].sudo().write({"inherit_id": inherit_view.id})

    def _cleanup_legacy_shop_clone_views(self, target_website):
        view_model = self.env["ir.ui.view"].sudo()
        legacy_views = view_model.search([
            ("website_id", "=", target_website.id),
            ("type", "=", "qweb"),
            ("key", "like", ".clone_%s" % target_website.id),
        ])

        if not legacy_views:
            return

        pattern = re.compile(r"\.clone_%s(?:_\d+)?$" % target_website.id)
        legacy_views = legacy_views.filtered(
            lambda view: bool(view.key)
            and bool(pattern.search(view.key))
            and ("page_ids" not in view._fields or not view.page_ids)
            and self._is_shop_related_view(view)
        )

        if legacy_views:
            legacy_views.unlink()

    def _get_source_pricelists(self, source_website):
        pricelists = self.env["product.pricelist"].sudo().browse()
        if "pricelist_id" in source_website._fields:
            pricelists |= source_website.pricelist_id
        if "pricelist_ids" in source_website._fields:
            pricelists |= source_website.pricelist_ids
        return pricelists

    def _clone_shop_pricelists(self, source_website, target_website):
        pricelist_map = {}
        source_pricelists = self._get_source_pricelists(source_website)
        for source_pricelist in source_pricelists:
            defaults = {"name": source_pricelist.name}
            if "website_id" in source_pricelist._fields:
                defaults["website_id"] = target_website.id
            cloned_pricelist = source_pricelist.copy(default=defaults)
            pricelist_map[source_pricelist.id] = cloned_pricelist
            if self.copy_translations:
                self._copy_model_translations(source_pricelist, cloned_pricelist)
        _logger.info(
            "Shop pricelists cloned: source_website_id=%s target_website_id=%s count=%s",
            source_website.id,
            target_website.id,
            len(source_pricelists),
        )
        return pricelist_map

    def _get_source_shop_products(self, source_website):
        template_model = self.env["product.template"].sudo()
        domain = [("sale_ok", "=", True)]

        has_website_ids = "website_ids" in template_model._fields
        has_website_id = "website_id" in template_model._fields
        if has_website_ids and has_website_id:
            domain += ["|", ("website_ids", "in", source_website.id), ("website_id", "=", source_website.id)]
        elif has_website_ids:
            domain += [("website_ids", "in", source_website.id)]
        elif has_website_id:
            domain += [("website_id", "=", source_website.id)]

        return template_model.search(domain, order="id")

    def _collect_shop_categories(self, source_products, source_website):
        category_model = self.env["product.public.category"].sudo()
        categories = category_model.browse()

        for template in source_products:
            if "public_categ_ids" in template._fields:
                categories |= template.public_categ_ids

        if "website_id" in category_model._fields:
            categories |= category_model.search([("website_id", "=", source_website.id)])

        stack = categories
        while stack:
            parents = stack.mapped("parent_id")
            parents = parents - categories
            if not parents:
                break
            categories |= parents
            stack = parents

        return categories

    def _sort_categories_by_depth(self, categories):
        def _depth(category):
            depth = 0
            parent = category.parent_id
            while parent:
                depth += 1
                parent = parent.parent_id
            return depth

        return sorted(categories, key=lambda cat: (_depth(cat), cat.id))

    def _clone_shop_categories(self, source_website, target_website, source_products):
        category_map = {}
        source_categories = self._collect_shop_categories(source_products, source_website)
        if not source_categories:
            return category_map

        for source_category in self._sort_categories_by_depth(source_categories):
            parent_clone = category_map.get(source_category.parent_id.id)
            defaults = {
                "name": source_category.name,
                "parent_id": parent_clone.id if parent_clone else False,
            }
            if "website_id" in source_category._fields:
                defaults["website_id"] = target_website.id
            cloned_category = source_category.copy(default=defaults)
            category_map[source_category.id] = cloned_category
            if self.copy_translations:
                self._copy_model_translations(source_category, cloned_category)
        _logger.info(
            "Shop categories cloned: source_website_id=%s target_website_id=%s count=%s",
            source_website.id,
            target_website.id,
            len(source_categories),
        )
        return category_map

    def _clone_shop_products(self, source_products, target_website, category_map):
        product_map = {}
        for source_product in source_products:
            defaults = {"name": source_product.name}
            if "website_id" in source_product._fields:
                defaults["website_id"] = target_website.id
            if "website_ids" in source_product._fields:
                defaults["website_ids"] = [(6, 0, [target_website.id])]
            if "public_categ_ids" in source_product._fields:
                if category_map:
                    defaults["public_categ_ids"] = [
                        (6, 0, [category_map[cid].id for cid in source_product.public_categ_ids.ids if cid in category_map])
                    ]
                else:
                    defaults["public_categ_ids"] = [(6, 0, source_product.public_categ_ids.ids)]
            if "website_published" in source_product._fields:
                defaults["website_published"] = source_product.website_published
            if "is_published" in source_product._fields:
                defaults["is_published"] = source_product.is_published

            cloned_product = source_product.copy(default=defaults)
            product_map[source_product.id] = cloned_product
            if self.copy_translations:
                self._copy_model_translations(source_product, cloned_product)
        _logger.info(
            "Shop products cloned: target_website_id=%s count=%s",
            target_website.id,
            len(source_products),
        )
        return product_map

    def _clone_shop_data(self, source_website, target_website):
        source_products = self._get_source_shop_products(source_website)
        category_map = {}
        pricelist_map = {}

        _logger.info(
            "Starting shop clone: source_website_id=%s target_website_id=%s source_products=%s copy_shop_settings=%s copy_shop_pricelists=%s copy_shop_categories=%s copy_shop_products=%s",
            source_website.id,
            target_website.id,
            len(source_products),
            self.copy_shop_settings,
            self.copy_shop_pricelists,
            self.copy_shop_categories,
            self.copy_shop_products,
        )

        if self.copy_shop_pricelists:
            pricelist_map = self._clone_shop_pricelists(source_website, target_website)

        if self.copy_shop_settings:
            self._copy_shop_settings(source_website, target_website, pricelist_map)
            self._clone_shop_custom_views(source_website, target_website)
            self._sync_shop_toggle_views(source_website, target_website)
        if self.copy_shop_categories:
            category_map = self._clone_shop_categories(source_website, target_website, source_products)
        if self.copy_shop_products:
            self._clone_shop_products(source_products, target_website, category_map)
        _logger.info(
            "Shop clone completed: source_website_id=%s target_website_id=%s pricelists=%s categories=%s products=%s",
            source_website.id,
            target_website.id,
            len(pricelist_map),
            len(category_map),
            len(source_products) if self.copy_shop_products else 0,
        )

    def action_clone_page(self):
        self.ensure_one()

        _logger.info(
            "Clone request: source_mode=%s source_page_id=%s source_website_id=%s target_mode=%s target_website_id=%s active_ids=%s copy_shop=%s copy_shop_settings=%s copy_shop_pricelists=%s copy_shop_categories=%s copy_shop_products=%s",
            self.source_mode,
            self.source_page_id.id,
            self.source_website_id.id,
            self.target_mode,
            self.target_website_id.id,
            self.env.context.get("active_ids"),
            self.copy_shop,
            self.copy_shop_settings,
            self.copy_shop_pricelists,
            self.copy_shop_categories,
            self.copy_shop_products,
        )

        if self.source_mode == "custom" and not self.source_page_id:
            raise UserError(_("La pagina origen es obligatoria en modo custom."))
        if self.source_mode == "complete" and not self.source_website_id:
            raise UserError(_("El sitio web donante es obligatorio en modo completa."))

        source_website = self._resolve_source_website()

        if self.target_mode == "new":
            target_website = self._create_target_website(source_website)
        else:
            target_website = self.target_website_id.sudo()

        if not target_website:
            raise UserError(_("El sitio destino es obligatorio."))
        if target_website.id == source_website.id:
            raise UserError(_("El sitio origen y el sitio destino deben ser distintos."))

        if self.target_mode == "new" and self.source_mode == "complete":
            self._cleanup_new_website_pages(target_website)
        elif self.target_mode == "new" and self.source_mode == "custom" and self.source_page_id.url == "/":
            self._cleanup_new_website_home(target_website)

        if self.source_mode == "complete":
            if self.target_mode == "new":
                self._cleanup_target_website_views(target_website, include_shop=self.copy_shop)
                self._cleanup_target_website_menus(target_website)

            self._copy_website_settings(source_website, target_website)
            target_page, page_map = self._clone_complete_pages(source_website, target_website)
            self._clone_complete_menu_tree(source_website, target_website, page_map)
            self._clone_website_custom_views(source_website, target_website, include_shop=self.copy_shop)
            self._clone_website_rewrites(source_website, target_website)
        else:
            target_page = self._clone_single_page(
                self._resolve_source_page(),
                target_website,
                name=self.new_name or _("%s (Copia)") % self.source_page_id.name,
                url=self.new_url or self.source_page_id.url,
                publish=self.publish,
            )

        if self.copy_shop:
            self._clone_shop_data(source_website, target_website)

        return {
            "type": "ir.actions.act_url",
            "url": "/web#id=%s&model=website.page&view_type=form" % target_page.id,
            "target": "self",
        }
