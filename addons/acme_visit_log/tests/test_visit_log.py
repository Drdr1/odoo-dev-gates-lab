from odoo.tests.common import TransactionCase


class TestVisitLog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Test Customer"})
        cls.visit = cls.env["acme.visit.log"].create(
            {"name": "Quarterly review", "partner_id": cls.partner.id}
        )

    def test_defaults(self):
        self.assertEqual(self.visit.state, "draft")
        self.assertEqual(self.visit.company_id, self.env.company)

    def test_display_name(self):
        self.assertEqual(self.visit.display_name, "Test Customer - Quarterly review")

    def test_action_done(self):
        self.visit.action_done()
        self.assertEqual(self.visit.state, "done")

    def test_action_close_all(self):
        self.visit.action_close_all()
        self.assertEqual(self.visit.state, "done")
