"""Exercises the real generation pipeline end to end against a LIVE server.

Prereqs (see DESIGN.md): Postgres up, Redis up, `MAX_CONCURRENT_GENERATIONS=2`
set in .env, then in two terminals:
    uvicorn app.main:app --reload
    python -m arq app.worker.WorkerSettings

Run: ./venv/Scripts/python.exe scripts/test_pipeline.py
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import create_session_token  # noqa: E402

# Registers every mapped class on Base before any mapper gets configured —
# same reason app/main.py imports all five model modules up front. Team.invites
# references "TeamInvite" by name, so without this import mapper configuration
# throws InvalidRequestError the moment any of the models below are touched.
from app.models import generation_job as generation_job_models  # noqa: E402,F401
from app.models import invite as invite_models  # noqa: E402,F401
from app.models.asset import Asset, AssetKind, MediaType  # noqa: E402
from app.models.team import Team, TeamMembership, TeamRole, new_id  # noqa: E402
from app.models.user import User  # noqa: E402

BASE_URL = "http://localhost:8000"


def api(method: str, path: str, cookie: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Cookie": f"session_token={cookie}"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def check(label: str, condition: bool) -> None:
    print(f"{'PASS' if condition else 'FAIL'}: {label}")
    if not condition:
        sys.exit(1)


def setup_team_with_assets(db, name: str, n_assets: int) -> tuple[str, str, list[str]]:
    """Creates a throwaway user + team + owner membership + n fake upload
    assets, directly in Postgres. Returns (session_cookie, team_id, asset_ids)."""
    user = User(id=new_id(), email=f"{name}-{new_id()}@example.test", name=name)
    db.add(user)
    team = Team(id=new_id(), name=f"{name}'s team")
    db.add(team)
    db.add(TeamMembership(team_id=team.id, user_id=user.id, role=TeamRole.owner.value))
    # Flush now: Asset has no ORM relationship() to Team/User (just plain FK
    # columns), and SQLAlchemy's flush-ordering is relationship-driven, not
    # raw-FK-driven — without this, the asset inserts below can be emitted
    # before their parent rows and fail the FK constraints.
    db.flush()

    asset_ids = []
    for i in range(n_assets):
        asset = Asset(
            id=new_id(),
            team_id=team.id,
            created_by=user.id,
            kind=AssetKind.upload.value,
            media_type=MediaType.image.value,
            storage_key=f"{team.id}/fake-{i}.png",
            url=f"{BASE_URL}/files/{team.id}/fake-{i}.png",
        )
        db.add(asset)
        asset_ids.append(asset.id)

    db.commit()
    return create_session_token(user.id), team.id, asset_ids


def main() -> None:
    db = SessionLocal()
    try:
        cookie_a, team_a, assets_a = setup_team_with_assets(db, "team-a", 5)
        cookie_b, team_b, assets_b = setup_team_with_assets(db, "team-b", 1)
    finally:
        db.close()

    # 1. Bulk batch of 5 for team A comes back immediately, all "processing"
    status_code, body = api(
        "POST",
        "/generate/bulk",
        cookie_a,
        {"team_id": team_a, "feature_type": "on_model_shots", "asset_ids": assets_a, "input_payload": {}},
    )
    check("POST /generate/bulk returns 201", status_code == 201)
    batch_id = body["batch_id"]
    job_ids = body["job_ids"]
    check("bulk response has 5 job ids", len(job_ids) == 5)

    status_code, jobs_body = api("GET", f"/jobs?ids={','.join(job_ids)}", cookie_a)
    check("GET /jobs 200", status_code == 200)
    check("all 5 jobs start as 'processing'", all(j["status"] == "processing" for j in jobs_body))

    # 2. While the batch is running, a second single /generate for the SAME
    # team must queue behind it, not start immediately.
    status_code, single_body = api(
        "POST",
        "/generate",
        cookie_a,
        {"team_id": team_a, "feature_type": "on_model_shots", "source_asset_id": assets_a[0], "input_payload": {}},
    )
    check("second single /generate (team A) returns 201", status_code == 201)
    single_job_id = single_body["id"]

    # 3. Simultaneously, a generation for a DIFFERENT team must run
    # independently, unblocked by team A's batch.
    status_code, other_team_body = api(
        "POST",
        "/generate",
        cookie_b,
        {"team_id": team_b, "feature_type": "on_model_shots", "source_asset_id": assets_b[0], "input_payload": {}},
    )
    check("team B /generate returns 201", status_code == 201)
    other_team_job_id = other_team_body["id"]

    # 4. Poll the batch — done-count must climb one at a time, not jump
    # straight to 5 (proves the per-team lock is real).
    seen_done_counts: list[int] = []
    deadline = time.time() + 60
    while time.time() < deadline:
        status_code, batch_body = api("GET", f"/batches/{batch_id}", cookie_a)
        check("GET /batches/{batch_id} 200", status_code == 200)
        done = batch_body["done"]
        if not seen_done_counts or seen_done_counts[-1] != done:
            seen_done_counts.append(done)
            print(f"  batch done-count: {done}/5")
        if done == 5:
            break
        time.sleep(0.5)
    check("batch reached done=5", seen_done_counts[-1] == 5 if seen_done_counts else False)
    check(
        "done-count climbed one at a time (not straight to 5)",
        seen_done_counts[:2] != [0, 5] and len(seen_done_counts) >= 5,
    )

    # 5. The team-A single job must only have completed AFTER the batch —
    # i.e. it was genuinely serialized behind the batch by the per-team lock.
    status_code, single_status = api("GET", f"/jobs?ids={single_job_id}", cookie_a)
    check("team A's extra single job is done", single_status[0]["status"] == "done")

    # 6. Team B's job ran independently — should already be done too, and
    # nothing about its timing depended on team A.
    status_code, other_status = api("GET", f"/jobs?ids={other_team_job_id}", cookie_b)
    check("team B's job is done, independently", other_status[0]["status"] == "done")

    # 7. /health responds immediately regardless of any of the above.
    start = time.time()
    status_code, _ = api("GET", "/health", cookie_a, body=None)
    elapsed = time.time() - start
    check("GET /health is 200", status_code == 200)
    check("GET /health responded in well under a second", elapsed < 1.0)

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
