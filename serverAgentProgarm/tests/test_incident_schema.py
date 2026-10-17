from app.storage.models import Incident


def test_incident_status_column_fits_longest_state() -> None:
    assert Incident.__table__.c.status.type.length >= len("awaiting_approval")
