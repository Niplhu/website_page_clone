from odoo import _, api, models
from odoo.exceptions import UserError


class WebsiteCloneService(models.AbstractModel):
    _name = "website.clone.service"
    _description = "Website Clone Service"

    def clone_website(
        self,
        source_website,
        target_website,
        copy_translations=True,
        clone_ecommerce=True,
        replace_target_content=True,
    ):
        source_website = source_website.sudo()
        target_website = target_website.sudo()

        if source_website == target_website:
            raise UserError(_("El sitio web origen y destino deben ser distintos."))

        if replace_target_content:
            self._cleanup_target_website(target_website, cleanup_ecommerce=clone_ecommerce)

        self._copy_website_settings(source_website, target_website, copy_translations=copy_translations)
        self._clone_non_page_qweb_views(source_website, target_website, copy_translations=copy_translations)
        page_map = self._clone_pages(source_website, target_website, copy_translations=copy_translations)
        self._clone_menus(source_website, target_website, page_map, copy_translations=copy_translations)
        self._clone_rewrites(source_website, target_website)

        if clone_ecommerce:
            pricelist_map = self._clone_pricelists(source_website, target_website, copy_translations=copy_translations)
            self._apply_pricelist_mapping(source_website, target_website, pricelist_map)
            self._copy_ecommerce_extra_fields(source_website, target_website)

        return {
            "pages": len(page_map),
            "target_website": target_website,
        }

    def _cleanup_target_website(self, target_website, cleanup_ecommerce=True):
        menu_model = self.env["website.menu"].sudo()

        pages = self.env["website.page"].sudo().search([("website_id", "=", target_website.id)])
        if pages:
            pages.unlink()

        menus = menu_model.search([
            ("website_id", "=", target_website.id),
            ("id", "!=", target_website.menu_id.id),
        ])
        if menus:
            menus.unlink()

        rewrites = self.env["website.rewrite"].sudo().with_context(active_test=False).search([
            ("website_id", "=", target_website.id)
        ])
        if rewrites:
            rewrites.unlink()

        view_model = self.env["ir.ui.view"].sudo().with_context(active_test=False)
        view_domain = [("website_id", "=", target_website.id)]
        if "type" in view_model._fields:
            view_domain.append(("type", "=", "qweb"))
        views = view_model.search(view_domain)
        if "page_ids" in view_model._fields:
            views = views.filtered(lambda v: not v.page_ids)
        if views:
            views.unlink()

        if cleanup_ecommerce and "website_id" in self.env["product.pricelist"]._fields:
            pricelists = self.env["product.pricelist"].sudo().with_context(active_test=False).search([
                ("website_id", "=", target_website.id)
            ])
            if pricelists:
                pricelists.unlink()

    def _copy_website_settings(self, source_website, target_website, copy_translations=True):
        excluded = {
            "id",
            "display_name",
            "create_uid",
            "create_date",
            "write_uid",
            "write_date",
            "__last_update",
            "name",
            "domain",
            "company_id",
            "user_id",
            "menu_id",
            "domain_punycode",
            "favicon",
        }
        values = self._prepare_write_values(source_website, target_website, excluded=excluded)
        if values:
            target_website.sudo().write(values)
        if copy_translations:
            self._copy_model_translations(source_website, target_website)

    def _clone_pages(self, source_website, target_website, copy_translations=True):
        source_pages = self.env["website.page"].sudo().search([
            ("website_id", "=", source_website.id)
        ], order="id")
        if not source_pages:
            raise UserError(_("El sitio web origen no tiene paginas para clonar."))

        page_map = {}
        for source_page in source_pages:
            source_view = source_page.view_id.sudo()
            if not source_view:
                continue

            new_view = source_view.copy(default={
                "website_id": target_website.id,
                "key": source_view.key,
                "name": source_view.name,
            })
            target_page = self.env["website.page"].sudo().create({
                "name": source_page.name,
                "url": source_page.url,
                "website_id": target_website.id,
                "view_id": new_view.id,
            })

            excluded = {
                "id",
                "name",
                "url",
                "website_id",
                "view_id",
                "menu_ids",
                "is_homepage",
                "is_in_menu",
                "is_visible",
                "create_uid",
                "create_date",
                "write_uid",
                "write_date",
                "__last_update",
                "display_name",
            }
            values = self._prepare_write_values(source_page, target_page, excluded=excluded)
            if values:
                target_page.sudo().write(values)

            if copy_translations:
                self._copy_model_translations(source_page, target_page)
                self._copy_translated_field(source_view, new_view, "arch_db")

            page_map[source_page.id] = target_page

        return page_map

    def _clone_menus(self, source_website, target_website, page_map, copy_translations=True):
        menu_model = self.env["website.menu"].sudo()
        source_root = menu_model.search([
            ("website_id", "=", source_website.id),
            ("parent_id", "=", False),
        ], order="sequence,id", limit=1)
        target_root = target_website.menu_id.sudo()

        source_menus = menu_model.search([
            ("website_id", "=", source_website.id),
        ], order="parent_path,sequence,id")
        menu_map = {source_root.id: target_root} if source_root else {}

        for source_menu in source_menus:
            if source_root and source_menu.id == source_root.id:
                continue

            parent_menu = menu_map.get(source_menu.parent_id.id, target_root)
            values = {
                "name": source_menu.name,
                "website_id": target_website.id,
                "parent_id": parent_menu.id if parent_menu else False,
                "url": source_menu.url,
                "new_window": source_menu.new_window,
                "sequence": source_menu.sequence,
            }

            if source_menu.page_id and source_menu.page_id.id in page_map:
                target_page = page_map[source_menu.page_id.id]
                values["page_id"] = target_page.id
                values["url"] = target_page.url

            if "group_ids" in source_menu._fields:
                values["group_ids"] = [(6, 0, source_menu.group_ids.ids)]
            if "controller_page_id" in source_menu._fields and source_menu.controller_page_id:
                values["controller_page_id"] = source_menu.controller_page_id.id
            if "is_mega_menu" in source_menu._fields:
                values["is_mega_menu"] = source_menu.is_mega_menu
            if "mega_menu_content" in source_menu._fields:
                values["mega_menu_content"] = source_menu.mega_menu_content
            if "mega_menu_classes" in source_menu._fields:
                values["mega_menu_classes"] = source_menu.mega_menu_classes

            target_menu = menu_model.create(values)
            menu_map[source_menu.id] = target_menu

            if copy_translations:
                self._copy_model_translations(source_menu, target_menu)

    def _clone_rewrites(self, source_website, target_website):
        if "website.rewrite" not in self.env:
            return

        rewrite_model = self.env["website.rewrite"].sudo()
        source_rewrites = rewrite_model.search([("website_id", "=", source_website.id)], order="sequence,id")
        for source_rewrite in source_rewrites:
            rewrite_model.create({
                "name": source_rewrite.name,
                "website_id": target_website.id,
                "active": source_rewrite.active,
                "url_from": source_rewrite.url_from,
                "route_id": source_rewrite.route_id.id if source_rewrite.route_id else False,
                "url_to": source_rewrite.url_to,
                "redirect_type": source_rewrite.redirect_type,
                "sequence": source_rewrite.sequence,
            })

    def _clone_non_page_qweb_views(self, source_website, target_website, copy_translations=True):
        view_model = self.env["ir.ui.view"].sudo().with_context(active_test=False)
        domain = [("website_id", "=", source_website.id)]
        if "type" in view_model._fields:
            domain.append(("type", "=", "qweb"))

        source_views = view_model.search(domain, order="id")
        if "page_ids" in view_model._fields:
            source_views = source_views.filtered(lambda v: not v.page_ids)
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

        ordered_views = sorted(source_views, key=lambda v: (_depth(v), v.id))
        cloned_map = {}

        for source_view in ordered_views:
            target_view = source_view.copy(default={
                "website_id": target_website.id,
                "key": source_view.key,
            })
            cloned_map[source_view.id] = target_view
            if copy_translations:
                self._copy_translated_field(source_view, target_view, "arch_db")

        for source_view in ordered_views:
            target_view = cloned_map[source_view.id]
            inherit_id = source_view.inherit_id
            if inherit_id and inherit_id.id in cloned_map:
                target_view.write({"inherit_id": cloned_map[inherit_id.id].id})

    def _copy_ecommerce_extra_fields(self, source_website, target_website):
        if "shop_extra_field_ids" not in source_website._fields:
            return

        extra_field_model = self.env["website.sale.extra.field"].sudo()
        target_extra_fields = extra_field_model.search([("website_id", "=", target_website.id)])
        if target_extra_fields:
            target_extra_fields.unlink()

        for source_extra_field in source_website.sudo().shop_extra_field_ids:
            source_extra_field.copy(default={"website_id": target_website.id})

    def _clone_pricelists(self, source_website, target_website, copy_translations=True):
        pricelist_map = {}
        source_pricelists = source_website.sudo().pricelist_ids
        for source_pricelist in source_pricelists:
            if "website_id" not in source_pricelist._fields or source_pricelist.website_id != source_website:
                pricelist_map[source_pricelist.id] = source_pricelist
                continue

            cloned_pricelist = source_pricelist.sudo().copy(default={
                "website_id": target_website.id,
                "name": source_pricelist.name,
            })
            pricelist_map[source_pricelist.id] = cloned_pricelist
            if copy_translations:
                self._copy_model_translations(source_pricelist, cloned_pricelist)
        return pricelist_map

    def _apply_pricelist_mapping(self, source_website, target_website, pricelist_map):
        if not pricelist_map:
            return

        source_pl_ids = source_website.sudo().pricelist_ids.ids
        mapped_ids = [pricelist_map.get(pl_id, self.env["product.pricelist"].browse(pl_id)).id for pl_id in source_pl_ids]
        target_specific = self.env["product.pricelist"].sudo().browse(mapped_ids).filtered(
            lambda p: "website_id" in p._fields and p.website_id == target_website
        )
        if target_specific:
            target_specific.write({"website_id": target_website.id})

    @api.model
    def _translation_lang_codes(self):
        return self.env["res.lang"].sudo().search([("active", "=", True)]).mapped("code")

    def _copy_translated_field(self, source_record, target_record, field_name):
        source_field = source_record._fields.get(field_name)
        target_field = target_record._fields.get(field_name)
        if not source_field or not target_field:
            return
        if not getattr(source_field, "translate", False):
            return
        if getattr(target_field, "readonly", False):
            return

        for lang_code in self._translation_lang_codes():
            value = source_record.with_context(lang=lang_code)[field_name]
            target_record.with_context(lang=lang_code).sudo().write({field_name: value})

    def _copy_model_translations(self, source_record, target_record):
        for field_name, field in source_record._fields.items():
            if not getattr(field, "translate", False):
                continue
            self._copy_translated_field(source_record, target_record, field_name)

    def _prepare_write_values(self, source_record, target_record, excluded=None):
        excluded = excluded or set()
        values = {}
        for field_name, source_field in source_record._fields.items():
            if field_name in excluded:
                continue
            if field_name not in target_record._fields:
                continue

            target_field = target_record._fields[field_name]
            if getattr(target_field, "readonly", False):
                continue
            if getattr(target_field, "compute", False):
                continue
            if getattr(target_field, "related", False):
                continue
            if field_name in models.MAGIC_COLUMNS:
                continue
            if target_field.type == "one2many":
                continue
            if target_field.type == "many2one":
                values[field_name] = source_record[field_name].id or False
                continue
            if target_field.type == "many2many":
                values[field_name] = [(6, 0, source_record[field_name].ids)]
                continue
            values[field_name] = source_record[field_name]
        return values
