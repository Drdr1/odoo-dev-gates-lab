from odoo import api, fields, models


class AcmeVisitLog(models.Model):
    _name = "acme.visit.log"
    _description = "Customer Visit Log"
    _order = "visit_date desc, id desc"

    name = fields.Char(string="Subject", required=True)
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    visit_date = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Done")],
        string="Status",
        default="draft",
        required=True,
    )
    notes = fields.Text()

    @api.depends("name", "partner_id.name")
    def _compute_display_name(self):
        for visit in self:
            visit.display_name = f"{visit.partner_id.name} - {visit.name}"

    def action_done(self):
        self.write({"state": "done"})

    def action_reopen(self):
        self.write({"state": "draft"})
