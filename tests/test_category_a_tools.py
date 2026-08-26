"""tests/test_category_a_tools.py — verifies the 10 Category-A tools from
BACKEND-NEEDS.md are registered in the code registry (app/tools/) and get
mirrored into the tools DB table with the right output_media_type by
sync_tools_to_db(). credit_cost correctness (product_motion=4) is seeded by
an Alembic migration against real Postgres, not covered here — see
alembic/versions/ (this test's sqlite fixture runs Base.metadata.create_all,
not alembic migrations, so a migration-seeded value can't be asserted here).
"""

from app.models.tool import Tool
from app.tools import known_feature_types
from app.tools.sync import sync_tools_to_db

CATEGORY_A_FEATURE_TYPES = [
    "product_photoshoot",
    "background_swap",
    "mockup_studio",
    "flat_lay_angles",
    "magic_erase",
    "inpaint",
    "relight_shadows",
    "upscale_4k",
    "resize_outpaint",
    "product_motion",
]


def test_all_category_a_tools_registered():
    known = known_feature_types()
    missing = [ft for ft in CATEGORY_A_FEATURE_TYPES if ft not in known]
    assert not missing, f"not registered: {missing}"


def test_sync_creates_rows_with_correct_media_type(db_session):
    sync_tools_to_db(db_session)
    rows = {t.feature_type: t for t in db_session.query(Tool).all()}

    missing = [ft for ft in CATEGORY_A_FEATURE_TYPES if ft not in rows]
    assert not missing, f"missing from tools table after sync: {missing}"

    assert rows["product_motion"].output_media_type == "video"
    for feature_type in CATEGORY_A_FEATURE_TYPES:
        if feature_type != "product_motion":
            assert rows[feature_type].output_media_type == "image", feature_type
