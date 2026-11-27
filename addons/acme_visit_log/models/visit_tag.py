from odoo import fields, models


class AcmeVisitTag(models.Model):
    _name = "acme.visit.tag"
    _description = "Visit Tag"

    name = fields.Char(required=True)
