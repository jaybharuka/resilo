async def log_remediation(db, data: dict):
    await db.execute(
        """
        INSERT INTO remediation_logs (alert_id, playbook_type, status, created_at)
        VALUES (:alert_id, :playbook_type, :status, NOW())
        """,
        data
    )
