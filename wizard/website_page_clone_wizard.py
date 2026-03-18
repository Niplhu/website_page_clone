import logging
import re
from urllib.parse import urlsplit, urlunsplit

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class WebsitePageCloneWizard(models.TransientModel):
    _name = "website.page.clone.wizard"
    _description = "Asistente de clonado de paginas web"

    COMPLETE_MODE_FIELD_DEFAULTS = {
        "copy_shop": True,
        "copy_shop_settings": True,
        "copy_shop_pricelists": True,
        "copy_shop_categories": True,
        "copy_shop_products": True,
    }

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
    copy_shop_pricelists = fields.Boolean(default=True, string="Usar tarifas existentes")
    copy_shop_categories = fields.Boolean(default=True, string="Clonar categorias de tienda")
    copy_shop_products = fields.Boolean(default=True, string="Usar productos existentes")
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

    @classmethod
    def _get_complete_mode_defaults(cls):
        return dict(cls.COMPLETE_MODE_FIELD_DEFAULTS)

    def _set_new_website_defaults_from_website(self, website, values=None, only_missing=False):
        if not website:
            return values if values is not None else {}

        defaults = {
            "new_website_name": _("%s (Copia)") % website.name,
        }
        if "company_id" in website._fields:
            defaults["new_website_company_id"] = website.company_id.id

        if values is None:
            for field_name, field_value in defaults.items():
                if not only_missing or not self[field_name]:
                    self[field_name] = field_value
            return defaults

        for field_name, field_value in defaults.items():
            if not only_missing or not values.get(field_name):
                values.setdefault(field_name, field_value)
        return values

    def _set_complete_mode_defaults(self):
        self.ensure_one()
        self.update({
            "target_mode": "new",
            "target_website_id": False,
            "new_name": False,
            "new_url": False,
            **self._get_complete_mode_defaults(),
        })

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
            for field_name, default_value in self._get_complete_mode_defaults().items():
                vals.setdefault(field_name, default_value)

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
            self._set_new_website_defaults_from_website(source_website, values=vals, only_missing=True)
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
                wizard._set_complete_mode_defaults()
                if wizard.source_website_id:
                    wizard._set_new_website_defaults_from_website(wizard.source_website_id)
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
                wizard._set_new_website_defaults_from_website(wizard.source_website_id)

    @api.constrains("source_mode", "source_page_id", "source_website_id", "target_mode", "target_website_id")
    def _check_clone_scope(self):
        for wizard in self:
            if wizard.source_mode == "custom" and not wizard.source_page_id:
                raise UserError(_("La pagina origen es obligatoria en modo custom."))
            if wizard.source_mode == "complete" and not wizard.source_website_id:
                raise UserError(_("El sitio web donante es obligatorio en modo completa."))

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

        if "is_published" in target_page._fields and "is_published" in source_page._fields:
            target_page.sudo().write({
                "is_published": bool(source_page.is_published if publish is None else publish)
            })

        if "page_ids" in new_view._fields:
            new_view.write({"page_ids": [(6, 0, [target_page.id])]})

        if self.copy_seo:
            self._apply_seo_values(source_page, target_page)
        if self.copy_menu:
            self._copy_menus(source_page, target_page, target_website)
        if self.copy_translations:
            self._copy_translations(source_page, target_page, source_view, new_view)

        return target_page

    def _collect_menu_tree(self, root_menu):
        menu_model = self.env["website.menu"].sudo()
        menus = menu_model.browse()
        queue = root_menu
        while queue:
            menus |= queue
            children = menu_model.search([("parent_id", "in", queue.ids)], order="sequence,id")
            queue = children - menus
        return menus.sorted(key=lambda menu: (menu.parent_id.id or 0, menu.sequence, menu.id))

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

    def _build_page_url_map(self, page_map):
        url_map = {}
        page_model = self.env["website.page"].sudo()
        for source_page_ref, target_page in page_map.items():
            source_page = source_page_ref
            if isinstance(source_page_ref, int):
                source_page = page_model.browse(source_page_ref).exists()

            source_url = source_page.url if source_page else False
            target_url = target_page.url if hasattr(target_page, "url") else False
            if source_url and target_url and source_url not in url_map:
                url_map[source_url] = target_url
        return url_map

    def _remap_internal_url(self, url, url_map):
        if not url or not url_map:
            return url

        split_url = urlsplit(url)
        source_path = split_url.path or ""
        if not source_path.startswith("/"):
            return url

        target_path = url_map.get(source_path)
        if not target_path:
            return url

        return urlunsplit((
            split_url.scheme,
            split_url.netloc,
            target_path,
            split_url.query,
            split_url.fragment,
        ))

    def _website_setting_fields(self):
        return [
            "language_ids",
            "default_lang_id",
            "social_facebook",
            "social_twitter",
            "social_linkedin",
            "social_youtube",
            "social_instagram",
            "contact_us_button_url",
            "google_analytics_key",
            "plausible_shared_key",
        ]

    def _copy_website_settings(self, source_website, target_website, url_map=None):
        vals = {}
        for field_name in self._website_setting_fields():
            target_field = target_website._fields.get(field_name)
            source_field = source_website._fields.get(field_name)
            if not source_field or not target_field:
                continue
            if getattr(target_field, "readonly", False) or getattr(target_field, "compute", False):
                continue
            if getattr(target_field, "related", False):
                continue
            if target_field.type in ("one2many", "binary"):
                continue
            if target_field.type == "many2one":
                vals[field_name] = source_website[field_name].id or False
            elif target_field.type == "many2many":
                vals[field_name] = [(6, 0, source_website[field_name].ids)]
            else:
                vals[field_name] = source_website[field_name]
                if field_name == "contact_us_button_url":
                    vals[field_name] = self._remap_internal_url(vals[field_name], url_map)
        if vals:
            target_website.sudo().write(vals)
        _logger.info(
            "Website settings cloned: source_website_id=%s target_website_id=%s fields=%s",
            source_website.id,
            target_website.id,
            len(vals),
        )

    def _page_priority_key(self, page, source_website_id):
        return (
            0 if page.website_id.id == source_website_id else 1,
            0 if page.website_id else 1,
            page.id,
        )

    def _select_effective_pages(self, pages, source_website):
        effective_pages = self.env["website.page"].sudo().browse()
        pages_by_url = {}

        for page in pages:
            if page.website_id and page.website_id.id != source_website.id:
                continue
            pages_by_url.setdefault(page.url or False, self.env["website.page"].sudo().browse())
            pages_by_url[page.url or False] |= page

        for _url, candidates in pages_by_url.items():
            ordered_candidates = candidates.sorted(
                key=lambda page: self._page_priority_key(page, source_website.id)
            )
            if ordered_candidates:
                effective_pages |= ordered_candidates[:1]

        return effective_pages.sorted(key=lambda page: page.id)

    def _collect_source_pages_for_website(self, source_website):
        page_model = self.env["website.page"].sudo()
        menu_model = self.env["website.menu"].sudo()

        pages = page_model.search([("website_id", "=", source_website.id)])
        source_menus = menu_model.search([("website_id", "=", source_website.id)])
        pages |= source_menus.mapped("page_id").filtered(
            lambda page: not page.website_id or page.website_id.id == source_website.id
        )

        shared_urls = [
            url for url in source_menus.mapped("url")
            if url and url.startswith("/") and url not in ("/shop", "/shop/cart", "/shop/checkout")
        ]
        if shared_urls:
            pages |= page_model.search([
                ("url", "in", list(set(shared_urls))),
                ("website_id", "in", [False, source_website.id]),
            ])

        homepage = page_model.search([
            ("url", "=", "/"),
            ("website_id", "=", source_website.id),
        ], limit=1)
        if not homepage:
            homepage = page_model.search([
                ("url", "=", "/"),
                ("website_id", "=", False),
            ], limit=1)
        pages |= homepage

        source_page_views = self.env["ir.ui.view"].sudo().search([
            ("website_id", "in", [False, source_website.id]),
            ("page_ids", "!=", False),
        ])
        pages |= source_page_views.mapped("page_ids").filtered(
            lambda page: not page.website_id or page.website_id.id == source_website.id
        )

        effective_pages = self._select_effective_pages(pages, source_website)
        _logger.info(
            "Effective source pages resolved: website_id=%s pages=%s",
            source_website.id,
            [(page.id, page.url, page.website_id.id if page.website_id else False) for page in effective_pages],
        )
        return effective_pages

    def _resolve_target_page_for_source_page(self, source_page, target_website, page_map=None):
        page_map = page_map or {}
        if source_page.id in page_map:
            return page_map[source_page.id]

        page_model = self.env["website.page"].sudo()
        target_page = page_model.search([
            ("url", "=", source_page.url),
            ("website_id", "=", target_website.id),
        ], limit=1)
        if target_page:
            return target_page

        return page_model.search([
            ("url", "=", source_page.url),
            ("website_id", "=", False),
        ], limit=1)

    def _mapped_page_ids(self, source_pages, target_website, page_map=None):
        mapped_pages = self.env["website.page"].sudo().browse()
        for source_page in source_pages:
            target_page = self._resolve_target_page_for_source_page(
                source_page,
                target_website,
                page_map=page_map,
            )
            if target_page:
                mapped_pages |= target_page
        return mapped_pages

    def _clone_website_rewrites(self, source_website, target_website, page_map=None):
        if "website.rewrite" not in self.env:
            return

        rewrite_model = self.env["website.rewrite"].sudo()
        source_rewrites = rewrite_model.search([("website_id", "=", source_website.id)])
        url_map = self._build_page_url_map(page_map or {})
        cloned = 0
        for source_rewrite in source_rewrites:
            defaults = {"website_id": target_website.id}
            target_url_to = self._remap_internal_url(source_rewrite.url_to, url_map)
            duplicate = rewrite_model.search([
                ("website_id", "=", target_website.id),
                ("url_from", "=", source_rewrite.url_from),
            ], limit=1)
            if duplicate:
                duplicate.write({
                    "url_to": target_url_to,
                    "redirect_type": source_rewrite.redirect_type,
                })
            else:
                defaults["url_to"] = target_url_to
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

    def _collect_page_bound_views(self, source_website, source_pages, include_shop=True):
        view_model = self.env["ir.ui.view"].sudo()
        domain = [
            ("website_id", "in", [False, source_website.id]),
            ("page_ids", "in", source_pages.ids),
        ]
        if "type" in view_model._fields:
            domain.append(("type", "=", "qweb"))

        source_views = view_model.search(domain, order="inherit_id,id")
        main_page_view_ids = set(source_pages.mapped("view_id").ids)
        page_bound_views = view_model.browse()
        for view in source_views:
            if view.id in main_page_view_ids:
                continue
            if not include_shop and self._is_shop_related_view(view):
                continue
            page_bound_views |= view
        return page_bound_views

    def _clone_page_bound_views(self, source_website, target_website, page_map, include_shop=True):
        source_pages = self.env["website.page"].sudo().browse(list(page_map.keys()))
        source_views = self._collect_page_bound_views(
            source_website,
            source_pages,
            include_shop=include_shop,
        )
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
                "key": self._get_unique_view_key(source_view, target_website.id),
            }
            mapped_pages = self._mapped_page_ids(source_view.page_ids, target_website, page_map=page_map)
            if "page_ids" in source_view._fields:
                defaults["page_ids"] = [(6, 0, mapped_pages.ids)]

            target_view = source_view.copy(default=defaults)
            view_map[source_view.id] = target_view

            if self.copy_translations and source_view.arch_db:
                self._copy_translated_field_values(source_view, target_view, "arch_db")

        for source_view in ordered_source_views:
            inherit_view = source_view.inherit_id
            if inherit_view and inherit_view.id in view_map:
                inherit_view = view_map[inherit_view.id]
            if inherit_view:
                view_map[source_view.id].sudo().write({"inherit_id": inherit_view.id})

        _logger.info(
            "Page-bound views cloned: source_website_id=%s target_website_id=%s include_shop=%s count=%s",
            source_website.id,
            target_website.id,
            include_shop,
            len(ordered_source_views),
        )

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

    def _collect_source_menus_for_website(self, source_website):
        root_menu = False
        for field_name in ("menu_id", "home_menu_id", "homepage_menu_id"):
            if field_name in source_website._fields and source_website[field_name]:
                root_menu = source_website[field_name]
                break

        if root_menu:
            menus = self._collect_menu_tree(root_menu)
            if menus:
                return menus

        return self.env["website.menu"].sudo().search(
            [("website_id", "=", source_website.id)],
            order="parent_id,sequence,id",
        )

    def _clone_complete_menu_tree(self, source_website, target_website, page_map):
        menu_model = self.env["website.menu"].sudo()
        source_menus = self._collect_source_menus_for_website(source_website)
        menu_map = {}
        url_map = self._build_page_url_map(page_map)

        for source_menu in source_menus:
            parent_menu = menu_map.get(source_menu.parent_id.id)
            vals = {
                "name": source_menu.name,
                "website_id": target_website.id,
                "sequence": source_menu.sequence,
                "parent_id": parent_menu.id if parent_menu else False,
                "url": self._remap_internal_url(source_menu.url, url_map),
            }
            if source_menu.page_id:
                target_page = page_map.get(source_menu.page_id.id)
                vals["page_id"] = target_page.id if target_page else False
            if "new_window" in source_menu._fields:
                vals["new_window"] = source_menu.new_window
            if "is_visible" in source_menu._fields:
                vals["is_visible"] = source_menu.is_visible
            menu_map[source_menu.id] = menu_model.create(vals)

        website_vals = {}
        for field_name in ("menu_id", "home_menu_id", "homepage_menu_id"):
            if field_name not in source_website._fields or field_name not in target_website._fields:
                continue
            source_menu = source_website[field_name]
            target_menu = menu_map.get(source_menu.id)
            if target_menu:
                website_vals[field_name] = target_menu.id
        if website_vals:
            target_website.sudo().write(website_vals)

        _logger.info(
            "Website menus cloned: source_website_id=%s target_website_id=%s count=%s names=%s",
            source_website.id,
            target_website.id,
            len(source_menus),
            source_menus.mapped("name"),
        )
        return menu_map

    def _clone_complete_pages(self, source_website, target_website):
        source_pages = self._collect_source_pages_for_website(source_website)
        if not source_pages:
            raise UserError(_("El sitio web donante seleccionado no tiene paginas para clonar."))

        page_map = {}
        target_page = self.env["website.page"]
        _logger.info(
            "Source pages collected for clone: website_id=%s pages=%s",
            source_website.id,
            [(page.id, page.url, page.website_id.id) for page in source_pages],
        )
        for source_page in source_pages:
            target_page = self._clone_single_page(source_page, target_website)
            page_map[source_page.id] = target_page
            _logger.info(
                "Page cloned: source_page_id=%s source_url=%s target_page_id=%s target_url=%s published=%s",
                source_page.id,
                source_page.url,
                target_page.id,
                target_page.url,
                getattr(target_page, "is_published", False),
            )
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

    def _is_record_compatible_with_website(self, record, target_website):
        if not record:
            return True

        if "company_id" in record._fields and record.company_id:
            target_company = target_website.company_id if "company_id" in target_website._fields else False
            if target_company and record.company_id != target_company:
                return False

        if "website_id" in record._fields and record.website_id and record.website_id != target_website:
            return False

        if "website_ids" in record._fields and record.website_ids and target_website not in record.website_ids:
            return False

        return True

    def _filter_compatible_records(self, records, target_website):
        return records.filtered(lambda record: self._is_record_compatible_with_website(record, target_website))

    def _copy_shop_settings(self, source_website, target_website, pricelist_map=None, url_map=None):
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
                if mapped_pricelist and self._is_record_compatible_with_website(mapped_pricelist, target_website):
                    vals[field_name] = mapped_pricelist.id
                elif self._is_record_compatible_with_website(source_pricelist, target_website):
                    vals[field_name] = source_pricelist.id
                continue

            if field_name == "pricelist_ids" and target_field.type == "many2many":
                source_ids = source_website[field_name].ids
                mapped_ids = [pricelist_map[pid].id for pid in source_ids if pid in pricelist_map]
                compatible_pricelists = self._filter_compatible_records(
                    self.env["product.pricelist"].sudo().browse(mapped_ids or source_ids),
                    target_website,
                )
                vals[field_name] = [(6, 0, compatible_pricelists.ids)]
                continue

            if field_name == "shop_placeholder_image" and target_field.type == "binary":
                vals[field_name] = source_website[field_name]
                continue

            if target_field.type == "many2one":
                source_record = source_website[field_name]
                if self._is_record_compatible_with_website(source_record, target_website):
                    vals[field_name] = source_record.id or False
                continue

            if target_field.type == "many2many":
                source_records = self._filter_compatible_records(source_website[field_name], target_website)
                vals[field_name] = [(6, 0, source_records.ids)]
                continue

            prepared = self._prepare_write_value(target_field, source_website[field_name])
            if prepared is False and target_field.type in ("one2many", "binary"):
                continue
            if field_name == "contact_us_button_url":
                prepared = self._remap_internal_url(prepared, url_map)
            vals[field_name] = prepared
        if vals:
            target_website.sudo().write(vals)

    def _shop_view_key_prefixes(self):
        return ("website_sale.", "website_payment.", "payment.")

    def _is_shop_page(self, page):
        return bool(page and page.url and page.url.startswith("/shop"))

    def _shop_toggle_view_keys(self):
        """Editor toggle views that must mirror *effective* active state."""
        return (
            "website_sale.header_hide_empty_cart_link",
            "website_sale.search",
            "website_sale.sort",
            "website_sale.add_grid_or_list_option",
            "website_sale.products_categories",
            "website_sale.products_categories_top",
            "website_sale.products_categories_list_collapsible",
            "website_sale.products_attributes",
            "website_sale.products_attributes_top",
            "website_sale.filter_products_price",
            "website_sale.filter_products_tags",
            "website_sale.products_design_cards",
            "website_sale.products_design_thumbs",
            "website_sale.products_design_grid",
            "website_sale.products_thumb_4_3",
            "website_sale.products_thumb_4_5",
            "website_sale.products_thumb_2_3",
            "website_sale.products_thumb_cover",
            "website_sale.products_add_to_cart",
            "website_sale.products_description",
            "website_sale.extra_info",
            "website_sale.suggested_products_list",
            "website_sale.reduction_code",
            "website_sale.accept_terms_and_conditions",
            "website_sale.address_b2b",
            "website_sale.product_buy_now",
        )

    def _shop_header_bridge_view_keys(self):
        return (
            "website_sale.template_header_mobile",
            "website_sale.template_header_default",
            "website_sale.template_header_hamburger",
            "website_sale.template_header_stretch",
            "website_sale.template_header_vertical",
            "website_sale.template_header_search",
            "website_sale.template_header_sales_one",
            "website_sale.template_header_sales_two",
            "website_sale.template_header_sales_three",
            "website_sale.template_header_sales_four",
            "website_sale.template_header_sidebar",
            "website_sale.template_header_boxed",
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
        domain = [("website_id", "in", [False, source_website.id])]
        if "type" in view_model._fields:
            domain.append(("type", "=", "qweb"))

        source_views = view_model.search(domain, order="inherit_id,id")
        shop_views = view_model.browse()
        keyed_views = {}
        for view in source_views:
            if "page_ids" in view._fields and view.page_ids and not any(
                self._is_shop_page(page) for page in view.page_ids
            ):
                continue
            if not self._is_shop_related_view(view):
                continue
            if self._is_shop_toggle_view_key(view.key):
                continue
            if view.key:
                current_view = keyed_views.get(view.key)
                if not current_view or (
                    view.website_id and view.website_id.id == source_website.id and not current_view.website_id
                ):
                    keyed_views[view.key] = view
                continue
            shop_views |= view

        for view in keyed_views.values():
            shop_views |= view
        return shop_views

    def _get_website_view_by_key(self, website, key):
        website_scoped = website.with_context(website_id=website.id)
        try:
            return website_scoped.viewref(key)
        except ValueError:
            return self.env["ir.ui.view"].sudo()

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

                _logger.info(
                    "Shop toggle synced: key=%s source_website_id=%s target_website_id=%s active=%s",
                    key,
                    source_website.id,
                    target_website.id,
                    source_state,
                )

    def _sync_shop_header_bridge_views(self, source_website, target_website):
        for key in self._shop_header_bridge_view_keys():
            source_view = self._get_website_specific_view_by_key(source_website, key)
            if not source_view:
                source_view = self._get_website_view_by_key(source_website, key)
            if not source_view:
                continue

            target_view = self._ensure_target_website_view(target_website, key)
            if not target_view:
                continue

            source_state = bool(
                source_website.with_context(website_id=source_website.id).is_view_active(key)
            )

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

            _logger.info(
                "Shop header bridge synced: key=%s source_website_id=%s target_website_id=%s active=%s",
                key,
                source_website.id,
                target_website.id,
                source_state,
            )

    def _ensure_cart_link_visibility(self, source_website, target_website):
        view_model = self.env["ir.ui.view"].sudo()
        key = "website_page_clone.force_header_cart_link_%s" % target_website.id
        target_view = view_model.search([
            ("website_id", "=", target_website.id),
            ("key", "=", key),
        ], limit=1)

        arch_db = """
<xpath expr="//t[@t-set='show_cart']" position="replace">
    <t t-set="show_cart" t-value="True"/>
</xpath>
        """.strip()

        vals = {
            "name": "Force cart visibility",
            "type": "qweb",
            "key": key,
            "website_id": target_website.id,
            "inherit_id": self.env.ref("website_sale.header_cart_link").id,
            "arch_db": arch_db,
            "active": True,
            "priority": 9999,
        }

        if target_view:
            target_view.write(vals)
        else:
            view_model.create(vals)

        _logger.info(
            "Forced cart visibility on target website: source_website_id=%s target_website_id=%s",
            source_website.id,
            target_website.id,
        )

    def _forced_header_cart_specs(self):
        return [
            (
                "website.template_header_mobile",
                "//ul[hasclass('o_header_mobile_buttons_wrap')]//li",
                "before",
                """
<t t-call="website_sale.header_cart_link">
    <t t-set="_icon" t-value="True"/>
    <t t-set="_link_class" t-value="'o_navlink_background_hover btn position-relative rounded-circle border-0 p-1 text-reset'"/>
    <t t-set="_badge_class" t-value="'position-absolute top-0 end-0 mt-n1 me-n1 rounded-pill'"/>
</t>
                """.strip(),
            ),
            (
                "website.template_header_default",
                "//t[@t-call='website.placeholder_header_search_box']",
                "before",
                """
<t t-call="website_sale.header_cart_link">
    <t t-set="_icon" t-value="True"/>
    <t t-set="_link_class" t-value="'o_navlink_background btn position-relative rounded-circle p-1 text-center text-reset'"/>
    <t t-set="_badge_class" t-value="'position-absolute top-0 end-0 mt-n1 me-n1 rounded-pill'"/>
</t>
                """.strip(),
            ),
            (
                "website.template_header_hamburger",
                "//t[@t-call='portal.placeholder_user_sign_in']",
                "before",
                """
<t t-call="website_sale.header_cart_link">
    <t t-set="_icon" t-value="True"/>
    <t t-set="_link_class" t-value="'o_navlink_background_hover btn position-relative rounded-pill p-1 text-reset'"/>
    <t t-set="_badge_class" t-value="'position-absolute top-0 end-0 mt-n1 me-n1 rounded'"/>
</t>
                """.strip(),
            ),
            (
                "website.template_header_stretch",
                "//t[@t-call='website.placeholder_header_social_links']",
                "before",
                """
<t t-call="website_sale.header_cart_link">
    <t t-set="_icon" t-value="True"/>
    <t t-set="_item_class" t-value="'border-start o_border_contrast'"/>
    <t t-set="_link_class" t-value="'o_navlink_background_hover btn position-relative d-flex align-items-center h-100 rounded-0 p-2 text-reset'"/>
    <t t-set="_badge_class" t-value="'rounded'"/>
</t>
                """.strip(),
            ),
            (
                "website.template_header_vertical",
                "//t[@t-call='portal.placeholder_user_sign_in']",
                "before",
                """
<t t-call="website_sale.header_cart_link">
    <t t-set="_icon" t-value="True"/>
    <t t-set="_link_class" t-value="'o_navlink_background btn position-relative rounded-circle p-1 text-reset'"/>
    <t t-set="_badge_class" t-value="'position-absolute top-0 end-0 mt-n1 me-n1 rounded-pill'"/>
</t>
                """.strip(),
            ),
            (
                "website.template_header_search",
                "//t[@t-call='portal.placeholder_user_sign_in']",
                "before",
                """
<t t-call="website_sale.header_cart_link">
    <t t-set="_text" t-value="True"/>
    <t t-set="_item_class" t-value="'border-start o_border_contrast'"/>
    <t t-set="_link_class" t-value="'o_navlink_background_hover btn btn-sm d-flex align-items-center gap-1 h-100 rounded-0 p-2 text-reset'"/>
    <t t-set="_badge_class" t-value="'rounded'"/>
</t>
                """.strip(),
            ),
            (
                "website.template_header_sales_one",
                "//t[@t-call='portal.user_dropdown']",
                "before",
                """
<t t-call="website_sale.header_cart_link">
    <t t-set="_icon" t-value="True"/>
    <t t-set="_link_class" t-value="'btn position-relative rounded-circle p-1 text-reset o_navlink_background'"/>
    <t t-set="_badge_class" t-value="'position-absolute top-0 end-0 mt-n1 me-n1 rounded-pill'"/>
</t>
                """.strip(),
            ),
            (
                "website.template_header_sales_two",
                "//t[@t-call='portal.placeholder_user_sign_in']",
                "before",
                """
<t t-call="website_sale.header_cart_link">
    <t t-set="_icon" t-value="True"/>
    <t t-set="_text" t-value="True"/>
    <t t-set="_icon_wrap_class" t-value="'position-relative me-2 rounded-circle border p-2 bg-o-color-3 o_border_contrast'"/>
    <t t-set="_link_class" t-value="'btn d-flex align-items-center fw-bold text-reset o_navlink_background_hover'"/>
    <t t-set="_badge_class" t-value="'position-absolute top-0 end-0 mt-n1 me-n1 rounded-pill'"/>
    <t t-set="_text_class" t-value="'small'"/>
</t>
                """.strip(),
            ),
            (
                "website.template_header_sales_three",
                "//t[@t-call='website.placeholder_header_language_selector']",
                "before",
                """
<t t-call="website_sale.header_cart_link">
    <t t-set="_text" t-value="True"/>
    <t t-set="_item_class" t-value="'position-relative'"/>
    <t t-set="_link_class" t-value="'nav-link d-flex flex-row-reverse align-items-center text-uppercase fw-bold'"/>
    <t t-set="_icon_wrap_class" t-value="'d-contains'"/>
    <t t-set="_badge_class" t-value="'top-0 d-block ms-2'"/>
</t>
                """.strip(),
            ),
            (
                "website.template_header_sales_four",
                "//t[@t-call='website.placeholder_header_call_to_action']",
                "before",
                """
<t t-call="website_sale.header_cart_link">
    <t t-set="_icon" t-value="True"/>
    <t t-set="_link_class" t-value="'o_navlink_background_hover btn position-relative rounded-pill p-1 text-reset'"/>
    <t t-set="_badge_class" t-value="'position-absolute top-0 end-0 mt-n1 me-n1 rounded-pill'"/>
</t>
                """.strip(),
            ),
            (
                "website.template_header_sidebar",
                "//t[@t-call='website.placeholder_header_brand']",
                "after",
                """
<div class="d-flex ms-auto mb-0">
    <t t-call="website_sale.header_cart_link">
        <t t-set="_icon" t-value="True"/>
        <t t-set="_link_class" t-value="'o_navlink_background_hover btn position-relative p-1 rounded-circle text-reset'"/>
        <t t-set="_badge_class" t-value="'position-absolute top-0 end-0 rounded-pill mt-n1 me-n1'"/>
    </t>
</div>
                """.strip(),
            ),
            (
                "website.template_header_boxed",
                "//t[@t-call='website.placeholder_header_search_box']",
                "before",
                """
<t t-call="website_sale.header_cart_link">
    <t t-set="_icon" t-value="True"/>
    <t t-set="_link_class" t-value="'o_navlink_background btn position-relative rounded-circle p-1 text-center text-reset'"/>
    <t t-set="_badge_class" t-value="'position-absolute top-0 end-0 mt-n1 me-n1 rounded-pill'"/>
</t>
                """.strip(),
            ),
        ]

    def _force_cart_in_active_headers(self, target_website):
        view_model = self.env["ir.ui.view"].sudo()
        for template_xmlid, xpath_expr, position, snippet in self._forced_header_cart_specs():
            inherit_view = self.env["ir.ui.view"].sudo().search([
                ("website_id", "=", target_website.id),
                ("key", "=", template_xmlid),
            ], limit=1)
            if not inherit_view:
                try:
                    inherit_view = self.env.ref(template_xmlid)
                except ValueError:
                    continue

            key = "website_page_clone.force_%s_%s" % (template_xmlid.replace(".", "_"), target_website.id)
            target_view = view_model.search([
                ("website_id", "=", target_website.id),
                ("key", "=", key),
            ], limit=1)

            arch_db = "<xpath expr=\"%s\" position=\"%s\">%s</xpath>" % (
                xpath_expr,
                position,
                snippet,
            )
            vals = {
                "name": "Force cart in %s" % template_xmlid,
                "type": "qweb",
                "key": key,
                "website_id": target_website.id,
                "inherit_id": inherit_view.id,
                "arch_db": arch_db,
                "active": True,
                "priority": 10000,
            }
            if target_view:
                target_view.write(vals)
            else:
                view_model.create(vals)

            _logger.info(
                "Forced cart injection synced: target_website_id=%s template=%s",
                target_website.id,
                template_xmlid,
            )

    def _clone_shop_custom_views(self, source_website, target_website, page_map=None):
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
                if "page_ids" in source_view._fields:
                    mapped_pages = self._mapped_page_ids(
                        source_view.page_ids,
                        target_website,
                        page_map=page_map,
                    )
                    write_vals["page_ids"] = [(6, 0, mapped_pages.ids)]
                target_view.write(write_vals)
            else:
                defaults = {
                    "website_id": target_website.id,
                    "key": source_view.key,
                }
                if "page_ids" in source_view._fields:
                    mapped_pages = self._mapped_page_ids(
                        source_view.page_ids,
                        target_website,
                        page_map=page_map,
                    )
                    defaults["page_ids"] = [(6, 0, mapped_pages.ids)]
                target_view = source_view.copy(default=defaults)

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
        reused_global_pricelists = 0
        shared_specific_pricelists = 0
        cloned_specific_pricelists = 0
        skipped_pricelists = 0
        for source_pricelist in source_pricelists:
            if "website_id" in source_pricelist._fields:
                if not source_pricelist.website_id:
                    pricelist_map[source_pricelist.id] = source_pricelist
                    reused_global_pricelists += 1
                    continue
                if source_pricelist.website_id.id == target_website.id:
                    pricelist_map[source_pricelist.id] = source_pricelist
                    shared_specific_pricelists += 1
                    continue
                if source_pricelist.website_id == source_website:
                    defaults = {"website_id": target_website.id}
                    if "company_id" in source_pricelist._fields and "company_id" in target_website._fields:
                        defaults["company_id"] = target_website.company_id.id or False
                    cloned_pricelist = source_pricelist.copy(default=defaults)
                    pricelist_map[source_pricelist.id] = cloned_pricelist
                    cloned_specific_pricelists += 1
                    continue
                skipped_pricelists += 1
                continue

            pricelist_map[source_pricelist.id] = source_pricelist
            reused_global_pricelists += 1
        _logger.info(
            "Pricelists processed: source_website_id=%s target_website_id=%s reused_global=%s shared_specific=%s cloned_specific=%s skipped=%s",
            source_website.id,
            target_website.id,
            reused_global_pricelists,
            shared_specific_pricelists,
            cloned_specific_pricelists,
            skipped_pricelists,
        )
        return pricelist_map

    def _clone_specific_shop_product(self, source_product, target_website, category_map):
        defaults = {}
        if "website_id" in source_product._fields:
            defaults["website_id"] = target_website.id
        if "public_categ_ids" in source_product._fields:
            mapped_categ_ids = [
                category_map[cid].id for cid in source_product.public_categ_ids.ids if cid in category_map
            ]
            defaults["public_categ_ids"] = [(6, 0, mapped_categ_ids or source_product.public_categ_ids.ids)]
        cloned_product = source_product.copy(default=defaults)
        publish_vals = {}
        if "website_published" in source_product._fields:
            publish_vals["website_published"] = source_product.website_published
        if "is_published" in source_product._fields:
            publish_vals["is_published"] = source_product.is_published
        if publish_vals:
            cloned_product.sudo().write(publish_vals)
        return cloned_product

    def _get_source_shop_products(self, source_website):
        template_model = self.env["product.template"].sudo()
        domain = [("sale_ok", "=", True)]

        has_website_ids = "website_ids" in template_model._fields
        has_website_id = "website_id" in template_model._fields
        if has_website_ids and has_website_id:
            domain += [
                "|",
                "|",
                ("website_ids", "in", source_website.id),
                ("website_id", "=", source_website.id),
                "&",
                ("website_ids", "=", False),
                ("website_id", "=", False),
            ]
        elif has_website_ids:
            domain += ["|", ("website_ids", "in", source_website.id), ("website_ids", "=", False)]
        elif has_website_id:
            domain += ["|", ("website_id", "=", source_website.id), ("website_id", "=", False)]

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
            existing_category = self.env["product.public.category"].sudo().search([
                ("website_id", "=", target_website.id),
                ("name", "=", source_category.name),
                ("parent_id", "=", parent_clone.id if parent_clone else False),
            ], limit=1)
            if existing_category:
                category_map[source_category.id] = existing_category
                continue
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

    def _clone_shop_products(self, source_products, source_website, target_website, category_map):
        product_map = {}
        reused_global_products = 0
        linked_products = 0
        cloned_specific_products = 0
        skipped_products = 0
        for source_product in source_products:
            vals = {}
            is_global_product = False

            if "website_ids" in source_product._fields:
                current_website_ids = set(source_product.website_ids.ids)
                is_global_product = not current_website_ids
                if current_website_ids and target_website.id not in current_website_ids:
                    current_website_ids.add(target_website.id)
                    vals["website_ids"] = [(6, 0, list(current_website_ids))]
            elif "website_id" in source_product._fields:
                is_global_product = not bool(source_product.website_id)
                if source_product.website_id and source_product.website_id.id == source_website.id:
                    cloned_product = self._clone_specific_shop_product(
                        source_product,
                        target_website,
                        category_map,
                    )
                    product_map[source_product.id] = cloned_product
                    cloned_specific_products += 1
                    continue
                elif source_product.website_id and source_product.website_id.id != target_website.id:
                    skipped_products += 1
            else:
                is_global_product = True

            if not is_global_product and "public_categ_ids" in source_product._fields:
                mapped_categ_ids = [
                    category_map[cid].id for cid in source_product.public_categ_ids.ids if cid in category_map
                ]
                merged_categ_ids = set(source_product.public_categ_ids.ids)
                merged_categ_ids.update(mapped_categ_ids)
                vals["public_categ_ids"] = [(6, 0, list(merged_categ_ids))]
            if not is_global_product and "website_published" in source_product._fields:
                vals["website_published"] = source_product.website_published
            if not is_global_product and "is_published" in source_product._fields:
                vals["is_published"] = source_product.is_published

            if vals:
                source_product.sudo().write(vals)
                linked_products += 1
            elif is_global_product:
                reused_global_products += 1
            product_map[source_product.id] = source_product
        _logger.info(
            "Products processed: source_website_id=%s target_website_id=%s reused_global=%s shared_specific=%s cloned_specific=%s skipped=%s",
            source_website.id,
            target_website.id,
            reused_global_products,
            linked_products,
            cloned_specific_products,
            skipped_products,
        )
        return product_map

    def _clone_shop_data(self, source_website, target_website, page_map=None):
        source_products = self._get_source_shop_products(source_website)
        category_map = {}
        pricelist_map = {}
        url_map = self._build_page_url_map(page_map or {})

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
            self._copy_shop_settings(source_website, target_website, pricelist_map, url_map=url_map)
            self._clone_shop_custom_views(source_website, target_website, page_map=page_map)
            self._sync_shop_header_bridge_views(source_website, target_website)
            self._sync_shop_toggle_views(source_website, target_website)
        if self.copy_shop_categories:
            category_map = self._clone_shop_categories(source_website, target_website, source_products)
        if self.copy_shop_products:
            self._clone_shop_products(source_products, source_website, target_website, category_map)
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

        if self.source_mode == "complete" and self.target_mode != "new":
            self.write({"target_mode": "new", "target_website_id": False})
        if self.source_mode == "complete" and self.copy_shop and not self.copy_shop_products:
            self.write({"copy_shop_products": True})

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

            target_page, page_map = self._clone_complete_pages(source_website, target_website)
            self._clone_page_bound_views(source_website, target_website, page_map, include_shop=self.copy_shop)
            self._clone_complete_menu_tree(source_website, target_website, page_map)
            self._copy_website_settings(
                source_website,
                target_website,
                url_map=self._build_page_url_map(page_map),
            )
            self._clone_website_custom_views(source_website, target_website, include_shop=self.copy_shop)
            self._clone_website_rewrites(source_website, target_website, page_map=page_map)
        else:
            source_page = self._resolve_source_page()
            target_page = self._clone_single_page(
                source_page,
                target_website,
                name=self.new_name or _("%s (Copia)") % self.source_page_id.name,
                url=self.new_url or self.source_page_id.url,
                publish=self.publish,
            )
            page_map = {source_page.id: target_page}

        if self.copy_shop:
            self._clone_shop_data(source_website, target_website, page_map=page_map)

        if self.source_mode == "complete":
            return {
                "type": "ir.actions.act_url",
                "url": "/web#id=%s&model=website&view_type=form" % target_website.id,
                "target": "self",
            }

        return {
            "type": "ir.actions.act_url",
            "url": "/web#id=%s&model=website.page&view_type=form" % target_page.id,
            "target": "self",
        }
