"""Entity registry for the CMS's generic CRUD layer (app/controllers/
cms_controller.py, app/routes/cms_routes.py) — one FieldConfig/EntityConfig
per model, describing what the CMS is allowed to do with it. Same "a
registry every module registers itself into" pattern as
app/tools/registry.py, just data instead of behavior: nothing outside this
file needs to know which SQLAlchemy columns exist on which table, it just
reads ENTITIES.
"""

from dataclasses import dataclass, field
from typing import Literal

from app.models.ai_model import AIModel
from app.models.asset import Asset
from app.models.credit import CreditPack, CreditTransaction, TeamCreditBalance
from app.models.generation_job import GenerationJob
from app.models.invite import TeamInvite
from app.models.nav_item import NavItem
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.product_import import ProductImport
from app.models.subscription import TeamSubscription
from app.models.team import Team, TeamMembership
from app.models.template import Template
from app.models.tool import Tool
from app.models.user import User

FieldKind = Literal["string", "int", "float", "bool", "datetime", "json", "enum", "fk"]


@dataclass(frozen=True)
class FieldConfig:
    name: str
    kind: FieldKind
    editable: bool = True
    enum_values: list[str] | None = None  # required when kind == "enum"
    fk_entity: str | None = None  # required when kind == "fk" — the
    # registered entity name (an ENTITIES key) it points to
    help_text: str | None = None  # shown under the field's label in the CMS
    # form — for a field name that isn't self-explanatory (e.g. "is_active"
    # doesn't say WHAT goes inactive, or where)


@dataclass(frozen=True)
class EntityConfig:
    name: str  # URL slug, e.g. "team-memberships"
    label: str  # sidebar/heading display name
    model: type  # the SQLAlchemy model class
    fields: list[FieldConfig]
    pk_field: str = "id"
    pk_provided_on_create: bool = False  # True when the PK column has no
    # Python-side default (plain Column(..., primary_key=True)) and must be
    # supplied in the create payload instead of being auto-generated
    search_fields: list[str] = field(default_factory=list)  # columns
    # matched (ILIKE) by the list page's search box
    cache_namespace: str | None = None  # app.core.cache namespace to clear
    # (keyed by this row's own pk value) after any write — mirrors whatever
    # read-through cache already exists for this table elsewhere in the app
    allow_create: bool = True
    allow_update: bool = True
    allow_delete: bool = True


ENTITIES: dict[str, EntityConfig] = {}


def register(entity: EntityConfig) -> None:
    if entity.name in ENTITIES:
        raise ValueError(f"entity {entity.name!r} already registered")
    ENTITIES[entity.name] = entity


_ID = FieldConfig("id", "string", editable=False)
_CREATED_AT = FieldConfig("created_at", "datetime", editable=False)
_UPDATED_AT = FieldConfig("updated_at", "datetime", editable=False)

register(EntityConfig(
    name="users",
    label="Users",
    model=User,
    pk_provided_on_create=True,  # User.id is a Firebase uid, no DB default
    cache_namespace="login",
    search_fields=["email", "name"],
    fields=[_ID, FieldConfig("email", "string"), FieldConfig("name", "string"),
            FieldConfig("avatar_url", "string"), _CREATED_AT],
))

register(EntityConfig(
    name="teams",
    label="Teams",
    model=Team,
    search_fields=["name"],
    fields=[_ID, FieldConfig("name", "string"), _CREATED_AT],
))

register(EntityConfig(
    name="team-memberships",
    label="Team Memberships",
    model=TeamMembership,
    fields=[
        _ID,
        FieldConfig("team_id", "fk", fk_entity="teams"),
        FieldConfig("user_id", "fk", fk_entity="users"),
        FieldConfig("role", "enum", enum_values=["owner", "editor"]),
        FieldConfig("joined_at", "datetime", editable=False),
    ],
))

register(EntityConfig(
    name="team-invites",
    label="Team Invites",
    model=TeamInvite,
    search_fields=["email"],
    fields=[
        _ID,
        FieldConfig("team_id", "fk", fk_entity="teams"),
        FieldConfig("email", "string"),
        FieldConfig("role", "enum", enum_values=["owner", "editor"]),
        FieldConfig("invited_by", "fk", fk_entity="users"),
        _CREATED_AT,
        FieldConfig("accepted_at", "datetime"),
    ],
))

register(EntityConfig(
    name="plans",
    label="Plans",
    model=Plan,
    search_fields=["name"],
    fields=[
        _ID,
        FieldConfig("name", "string"),
        FieldConfig("billing_cycle", "enum", enum_values=["monthly", "yearly", "free"]),
        FieldConfig("price", "int"),
        FieldConfig("currency", "string"),
        FieldConfig("credit_allowance", "int"),
        FieldConfig("max_team_members", "int"),
        FieldConfig("provider", "string"),
        FieldConfig("provider_plan_id", "string"),
        FieldConfig("is_active", "bool"),
        _CREATED_AT,
    ],
))

register(EntityConfig(
    name="team-subscriptions",
    label="Team Subscriptions",
    model=TeamSubscription,
    fields=[
        _ID,
        FieldConfig("team_id", "fk", fk_entity="teams"),
        FieldConfig("plan_id", "fk", fk_entity="plans"),
        FieldConfig("provider", "string"),
        FieldConfig("provider_subscription_id", "string"),
        FieldConfig("status", "enum", enum_values=["active", "past_due", "cancelled", "free"]),
        FieldConfig("current_period_end", "datetime"),
        FieldConfig("next_credit_refill_at", "datetime"),
        _CREATED_AT,
        _UPDATED_AT,
    ],
))

register(EntityConfig(
    name="team-credit-balances",
    label="Team Credit Balances",
    model=TeamCreditBalance,
    pk_field="team_id",
    pk_provided_on_create=True,  # team_id is the PK, no DB default
    fields=[
        FieldConfig("team_id", "fk", editable=False, fk_entity="teams"),
        FieldConfig("balance", "int"),  # bypasses credit_transactions —
        # see cms/README.md's "Known limitations"
        FieldConfig("updated_at", "datetime", editable=False),
    ],
))

register(EntityConfig(
    name="credit-transactions",
    label="Credit Transactions",
    model=CreditTransaction,
    allow_update=False,
    allow_delete=False,  # append-only audit ledger — create-only
    fields=[
        _ID,
        FieldConfig("team_id", "fk", fk_entity="teams"),
        FieldConfig("amount", "int"),
        FieldConfig("reason", "enum", enum_values=[
            "plan_grant", "topup_purchase", "generation_spend", "refund",
            "manual_adjustment", "subscription_cancelled",
        ]),
        FieldConfig("reference_id", "string"),
        FieldConfig("balance_after", "int"),
        _CREATED_AT,
    ],
))

register(EntityConfig(
    name="credit-packs",
    label="Credit Packs",
    model=CreditPack,
    search_fields=["name"],
    fields=[
        _ID,
        FieldConfig("name", "string"),
        FieldConfig("credit_amount", "int"),
        FieldConfig("price", "int"),
        FieldConfig("currency", "string"),
        FieldConfig("is_active", "bool"),
    ],
))

register(EntityConfig(
    name="tools",
    label="Tools",
    model=Tool,
    pk_field="feature_type",
    allow_create=False,  # a genuinely new tool needs a new app/tools/*.py
    # module — its row only ever appears via sync_tools_to_db
    fields=[
        FieldConfig("feature_type", "string", editable=False),
        FieldConfig("display_name", "string", editable=False),  # code-owned,
        # re-synced from app/tools/*.py on every boot — an edit here would
        # silently vanish on restart (app/tools/sync.py)
        FieldConfig("output_media_type", "enum", editable=False, enum_values=["image", "video"]),
        FieldConfig("default_model_id", "fk", fk_entity="ai-models"),  # DB-owned —
        # sync_tools_to_db never touches it on an existing row
        FieldConfig("credit_cost", "int"),
        FieldConfig("pricing_config", "json"),
        FieldConfig("is_active", "bool", help_text=(
            "Unchecked = this tool disappears from GET /tools and the Studio "
            "app immediately — no restart, no cache to clear. Checked = it "
            "shows up wherever the frontend lists tools."
        )),
        _CREATED_AT,
        _UPDATED_AT,
    ],
))

register(EntityConfig(
    name="ai-models",
    label="AI Models",
    model=AIModel,
    pk_field="model_id",
    pk_provided_on_create=True,  # no DB default on model_id
    search_fields=["display_name"],
    fields=[
        FieldConfig("model_id", "string", editable=False),
        FieldConfig("display_name", "string"),
        FieldConfig("base_credit_cost", "int"),
        FieldConfig("provider_name", "string"),
        FieldConfig("is_active", "bool"),
    ],
))

register(EntityConfig(
    name="assets",
    label="Assets",
    model=Asset,
    cache_namespace="media",
    search_fields=["url"],
    fields=[
        _ID,
        FieldConfig("team_id", "fk", fk_entity="teams"),
        FieldConfig("created_by", "fk", fk_entity="users"),
        FieldConfig("kind", "enum", enum_values=["upload", "generated", "imported"]),
        FieldConfig("media_type", "enum", enum_values=["image", "video"]),
        FieldConfig("storage_key", "string"),
        FieldConfig("url", "string"),
        FieldConfig("product_import_id", "fk", fk_entity="product-imports"),
        _CREATED_AT,
    ],
))

register(EntityConfig(
    name="generation-jobs",
    label="Generation Jobs",
    model=GenerationJob,
    search_fields=["feature_type", "batch_id"],
    fields=[
        _ID,
        FieldConfig("team_id", "fk", fk_entity="teams"),
        FieldConfig("created_by", "fk", fk_entity="users"),
        FieldConfig("feature_type", "string"),
        FieldConfig("status", "enum", enum_values=["queued", "processing", "done", "failed"]),
        FieldConfig("source_asset_id", "fk", fk_entity="assets"),
        FieldConfig("output_asset_id", "fk", fk_entity="assets"),
        FieldConfig("batch_id", "string"),
        FieldConfig("external_job_id", "string"),
        FieldConfig("provider", "string"),
        FieldConfig("input_payload", "json"),
        FieldConfig("credit_cost", "int"),
        FieldConfig("error", "string"),
        _CREATED_AT,
        FieldConfig("completed_at", "datetime"),
    ],
))

register(EntityConfig(
    name="product-imports",
    label="Product Imports",
    model=ProductImport,
    search_fields=["source_url", "product_name"],
    fields=[
        _ID,
        FieldConfig("team_id", "fk", fk_entity="teams"),
        FieldConfig("created_by", "fk", fk_entity="users"),
        FieldConfig("source_url", "string"),
        FieldConfig("status", "enum", enum_values=["processing", "done", "failed"]),
        FieldConfig("external_job_id", "string"),
        FieldConfig("product_name", "string"),
        FieldConfig("product_description", "string"),
        FieldConfig("brand_name", "string"),
        FieldConfig("price", "string"),
        FieldConfig("theme_colors", "json"),
        FieldConfig("raw_result", "json"),
        FieldConfig("credit_cost", "int"),
        FieldConfig("error", "string"),
        _CREATED_AT,
        FieldConfig("completed_at", "datetime"),
    ],
))

register(EntityConfig(
    name="payments",
    label="Payments",
    model=Payment,
    search_fields=["provider_payment_id"],
    fields=[
        _ID,
        FieldConfig("team_id", "fk", fk_entity="teams"),
        FieldConfig("provider", "string"),
        FieldConfig("provider_payment_id", "string"),
        FieldConfig("provider_order_id", "string"),
        FieldConfig("provider_subscription_id", "string"),
        FieldConfig("amount", "int"),
        FieldConfig("currency", "string"),
        FieldConfig("status", "enum", enum_values=["captured", "failed", "refunded"]),
        FieldConfig("kind", "enum", enum_values=["subscription_charge", "topup"]),
        _CREATED_AT,
    ],
))

register(EntityConfig(
    name="templates",
    label="Templates",
    model=Template,
    search_fields=["name", "category"],
    fields=[
        _ID,
        FieldConfig("name", "string"),
        FieldConfig("category", "string"),
        FieldConfig("preview_asset_url", "string"),
        FieldConfig("feature_type", "fk", fk_entity="tools"),
        FieldConfig("model_id", "fk", fk_entity="ai-models"),
        FieldConfig("preset_payload", "json"),
        FieldConfig("credit_cost_override", "int"),
        FieldConfig("is_active", "bool", help_text=(
            "Unchecked = this template disappears from GET /templates and "
            "the Templates page immediately — no restart, no cache to clear."
        )),
    ],
))

register(EntityConfig(
    name="nav-items",
    label="Nav Items",
    model=NavItem,
    pk_field="key",
    allow_create=False,  # the 12 pages are fixed by the Studio's own
    # routing — nothing here creates a new page, only toggles existing ones
    allow_delete=False,
    search_fields=["label"],
    fields=[
        FieldConfig("key", "string", editable=False),
        FieldConfig("label", "string", editable=False),
        FieldConfig("is_active", "bool", help_text=(
            "Unchecked = this page disappears from the Studio's sidebar "
            "immediately — no restart, no cache to clear."
        )),
        _CREATED_AT,
        _UPDATED_AT,
    ],
))
