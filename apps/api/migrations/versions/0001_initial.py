"""Frozen initial schema; run as a release step, never on web startup."""

import json
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    root = Path(__file__).parent
    connection = op.get_bind()
    for statement in json.loads((root / "0001_schema.json").read_text()):
        connection.exec_driver_sql(statement)
    for statement in json.loads((root / "0001_triggers.json").read_text()):
        connection.exec_driver_sql(statement)
    seed = json.loads((root / "0001_rules.json").read_text())
    connection.execute(
        text(
            "INSERT INTO rule_sets (version, checksum, engine_min_version, created_at) VALUES (:version, :checksum, '1.0.0', now())"
        ),
        {"version": "1.0.0", "checksum": seed["checksum"]},
    )
    for rule, definition in seed["rules"].items():
        connection.execute(
            text(
                "INSERT INTO rule_definitions (rule_set_version, rule_id, definition) VALUES ('1.0.0', :rule, CAST(:definition AS jsonb))"
            ),
            {"rule": rule, "definition": json.dumps(definition)},
        )


def downgrade():
    raise RuntimeError(
        "Initial migration is irreversible. Restore a verified backup; never drop user data implicitly."
    )
