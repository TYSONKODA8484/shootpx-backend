"""seed templates catalog

Revision ID: 8c59f976c159
Revises: 7e11343179fd
Create Date: 2026-08-26 14:20:00.000000

Data-only. Seeds 24 real templates across the 5 categories the Studio's
Templates page and Home's template strip need (BACKEND-NEEDS.md's B3:
"even 20-30 real seeded rows makes the page honest instead of empty").
preview_asset_url is left NULL for all of them — no real preview images
exist yet; seeding a fake URL would be dishonest catalog data.

Uses a SQLAlchemy Core `insert()` against a lightweight `sa.table()`
description (not raw `text()` SQL) specifically so preset_payload's Python
dict gets serialized through the JSON column type's own bind processor —
a raw `text()` bind handed a dict goes straight to psycopg2, which doesn't
know how to adapt one.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c59f976c159'
down_revision: Union[str, Sequence[str], None] = '7e11343179fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEMPLATES = [
    # (name, category, feature_type, preset_payload)
    ("Wet Stone Ledge", "Photoshoot", "product_photoshoot", {"prompt": "wet stone ledge, cold morning light", "aspect": "1:1", "mode": "creative"}),
    ("Marble Vanity", "Photoshoot", "product_photoshoot", {"prompt": "white marble vanity counter, soft daylight", "aspect": "4:5", "mode": "precise"}),
    ("Sandy Dune Backdrop", "Photoshoot", "product_photoshoot", {"prompt": "sand dune backdrop, golden hour", "aspect": "1:1", "mode": "creative"}),
    ("Studio Seamless White", "Photoshoot", "product_photoshoot", {"prompt": "seamless white studio backdrop, softbox lighting", "aspect": "1:1", "mode": "precise"}),
    ("Concrete Loft", "Photoshoot", "product_photoshoot", {"prompt": "raw concrete loft interior, natural window light", "aspect": "16:9", "mode": "creative"}),
    ("Apparel Tee Front", "Mockup", "mockup_studio", {"mockup_type": "apparel", "prompt": "unisex crewneck t-shirt, front view, studio lighting"}),
    ("Kraft Box Packaging", "Mockup", "mockup_studio", {"mockup_type": "packaging", "prompt": "kraft cardboard box mockup on wooden table"}),
    ("Phone Case Device", "Mockup", "mockup_studio", {"mockup_type": "device", "prompt": "smartphone case mockup, hand holding phone"}),
    ("Tote Bag Apparel", "Mockup", "mockup_studio", {"mockup_type": "apparel", "prompt": "canvas tote bag mockup, flat lay"}),
    ("Glass Jar Packaging", "Mockup", "mockup_studio", {"mockup_type": "packaging", "prompt": "glass jar label mockup, clean white background"}),
    ("Studio Fashion Model", "On-model", "on_model_shots", {"prompt": "studio fashion editorial, plain grey background"}),
    ("Street Style Model", "On-model", "on_model_shots", {"prompt": "street style, urban background, natural light"}),
    ("Outdoor Lifestyle Model", "On-model", "on_model_shots", {"prompt": "outdoor lifestyle, golden hour, casual pose"}),
    ("Minimal Studio Model", "On-model", "on_model_shots", {"prompt": "minimal studio backdrop, soft shadows"}),
    ("Editorial Runway Model", "On-model", "on_model_shots", {"prompt": "editorial runway pose, dramatic lighting"}),
    ("360 Orbit", "Motion", "product_motion", {"motion": "orbit", "aspect": "9:16", "duration_s": 5}),
    ("Push-In Reveal", "Motion", "product_motion", {"motion": "push-in", "aspect": "16:9", "duration_s": 5}),
    ("Slow Pan", "Motion", "product_motion", {"motion": "pan", "aspect": "16:9", "duration_s": 5}),
    ("Zoom Out Reveal", "Motion", "product_motion", {"motion": "zoom-out", "aspect": "9:16", "duration_s": 5}),
    ("Pour Splash", "Motion", "product_motion", {"motion": "pour", "aspect": "9:16", "duration_s": 5}),
    ("Unbox Reveal", "Motion", "product_motion", {"motion": "unbox", "aspect": "9:16", "duration_s": 5}),
    ("Testimonial Selfie", "UGC", "ugc", {"prompt": "handheld selfie style testimonial, natural lighting"}),
    ("Unboxing Reaction", "UGC", "ugc", {"prompt": "unboxing reaction, excited expression, home setting"}),
    ("Before/After Demo", "UGC", "ugc", {"prompt": "before and after demo, split screen style"}),
]

templates_table = sa.table(
    "templates",
    sa.column("id", sa.String),
    sa.column("name", sa.String),
    sa.column("category", sa.String),
    sa.column("feature_type", sa.String),
    sa.column("preset_payload", sa.JSON),
    sa.column("is_active", sa.Boolean),
)


def upgrade() -> None:
    conn = op.get_bind()
    for name, category, feature_type, preset in TEMPLATES:
        existing = conn.execute(
            sa.text("SELECT 1 FROM templates WHERE name = :name"), {"name": name}
        ).first()
        if existing:
            continue
        conn.execute(
            templates_table.insert().values(
                id=str(uuid.uuid4()), name=name, category=category,
                feature_type=feature_type, preset_payload=preset, is_active=True,
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    for name, _category, _ft, _preset in TEMPLATES:
        conn.execute(sa.text("DELETE FROM templates WHERE name = :name"), {"name": name})
