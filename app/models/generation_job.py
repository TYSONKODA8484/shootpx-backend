import enum
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String

from app.core.db import Base
from app.models.team import new_id


class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class GenerationJob(Base):
    """One attempt at running a tool. feature_type is a plain string on
    purpose — it's the dispatch key that will pick which of the 23 tools'
    logic runs, once that logic exists; today every feature_type just hits
    the same MockAIProvider. Scoped directly to a team, same as Asset —
    team_id for access, created_by for who actually ran it."""

    __tablename__ = "generation_jobs"

    id = Column(String, primary_key=True, default=new_id)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    feature_type = Column(String, nullable=False)
    status = Column(String, default=JobStatus.queued.value, nullable=False)  # queued|processing|done|failed
    source_asset_id = Column(String, ForeignKey("assets.id"), nullable=True)
    output_asset_id = Column(String, ForeignKey("assets.id"), nullable=True)
    batch_id = Column(String, nullable=True)  # shared by every job from one
    # /generate/bulk call; null for a single /generate. Not a FK — there's
    # no separate batches table, same lightweight-string pattern as
    # feature_type. Add an index if batch lookups ever get slow; skipped
    # for now (YAGNI at this scale).
    external_job_id = Column(String, nullable=True)  # the aggregator's own
    # job id (e.g. a fal.ai request id), set once app/worker.py has submitted
    # this job — null beforehand. Presence of this column, not `status`, is
    # what the worker uses to tell "not submitted yet" from "submitted,
    # waiting on a poll" across separate arq retries of the same job.
    provider = Column(String, nullable=True)  # which AIProvider handled this
    # ("mock", "fal", "segmind", ...) — set alongside external_job_id. Needed
    # because a later poll retry can land on a different worker process than
    # the one that submitted; nothing about routing back to the right
    # provider can live in that process's memory.
    input_payload = Column(JSON, default=dict, nullable=False)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
