def migrate(cr, version):
    """Existing visits predate the field: record them as zero minutes."""
    cr.execute(
        "UPDATE acme_visit_log SET duration_minutes = %s WHERE duration_minutes IS NULL",
        (0,),
    )
