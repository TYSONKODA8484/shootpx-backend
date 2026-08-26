from pydantic import BaseModel


class ActivityEvent(BaseModel):
    id: str  # "job:<id>" | "import:<id>" | "credit:<id>" — synthetic, keeps
    # ids unique across the merged union without a real shared table.
    kind: str  # "job" | "import" | "credit"
    title: str
    detail: str
    status: str | None
    created_at: str  # isoformat
    asset_url: str | None


class ActivityFeedOut(BaseModel):
    events: list[ActivityEvent]
    next_cursor: str | None
