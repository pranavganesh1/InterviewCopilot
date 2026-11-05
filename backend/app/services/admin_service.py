"""Admin analytics (M11): global + per-user rollups.

Reads Mongo llm_call_logs (tokens/cost) and Postgres (users, tracks,
sessions, reports). MVP-scale aggregations run on demand; no caching.
"""

import uuid
from datetime import UTC, datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession
from app.models.track import Track
from app.models.user import User

WINDOW_DAYS = 30


async def overview(db: AsyncSession, mongo_db: AsyncIOMotorDatabase) -> dict:
    users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    tracks = (await db.execute(select(func.count()).select_from(Track))).scalar_one()
    sessions = (await db.execute(select(func.count()).select_from(InterviewSession))).scalar_one()
    completed = (
        await db.execute(
            select(func.count())
            .select_from(InterviewSession)
            .where(InterviewSession.status == "completed")
        )
    ).scalar_one()
    minutes = (
        await db.execute(
            select(func.coalesce(func.sum(InterviewSession.duration_minutes), 0)).where(
                InterviewSession.status == "completed"
            )
        )
    ).scalar_one()

    since = datetime.now(UTC) - timedelta(days=WINDOW_DAYS)

    # Totals (all-time) + windowed by-day / by-model from Mongo.
    match_all = {"estimated_cost_usd": {"$exists": True}}
    pipeline_totals = [
        {"$match": match_all},
        {
            "$group": {
                "_id": None,
                "calls": {"$sum": 1},
                "tokens_in": {"$sum": "$prompt_tokens"},
                "tokens_out": {"$sum": "$completion_tokens"},
                "estimated_cost_usd": {"$sum": "$estimated_cost_usd"},
            }
        },
    ]
    totals_rows = await mongo_db.llm_call_logs.aggregate(pipeline_totals).to_list(1)
    totals = (
        totals_rows[0]
        if totals_rows
        else {
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "estimated_cost_usd": 0,
        }
    )

    by_day_rows = await mongo_db.llm_call_logs.aggregate(
        [
            {"$match": {"created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                    "calls": {"$sum": 1},
                    "tokens": {"$sum": {"$add": ["$prompt_tokens", "$completion_tokens"]}},
                    "estimated_cost_usd": {"$sum": "$estimated_cost_usd"},
                }
            },
            {"$sort": {"_id": 1}},
        ]
    ).to_list(500)

    by_model_rows = await mongo_db.llm_call_logs.aggregate(
        [
            {"$match": {"created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": "$model",
                    "calls": {"$sum": 1},
                    "tokens": {"$sum": {"$add": ["$prompt_tokens", "$completion_tokens"]}},
                    "estimated_cost_usd": {"$sum": "$estimated_cost_usd"},
                }
            },
            {"$sort": {"estimated_cost_usd": -1}},
        ]
    ).to_list(50)

    return {
        "users": users,
        "tracks": tracks,
        "interviews_total": sessions,
        "interviews_completed": completed,
        "interview_minutes": minutes,
        "llm_calls": totals.get("calls", 0),
        "tokens_in": totals.get("tokens_in") or 0,
        "tokens_out": totals.get("tokens_out") or 0,
        "estimated_cost_usd": round(float(totals.get("estimated_cost_usd") or 0), 4),
        "by_day": [
            {
                "day": r["_id"],
                "calls": r["calls"],
                "tokens": r.get("tokens") or 0,
                "estimated_cost_usd": round(float(r.get("estimated_cost_usd") or 0), 4),
            }
            for r in by_day_rows
        ],
        "by_model": [
            {
                "model": r["_id"],
                "calls": r["calls"],
                "tokens": r.get("tokens") or 0,
                "estimated_cost_usd": round(float(r.get("estimated_cost_usd") or 0), 4),
            }
            for r in by_model_rows
        ],
    }


async def users_rollup(db: AsyncSession, mongo_db: AsyncIOMotorDatabase) -> list[dict]:
    users = (await db.execute(select(User).order_by(User.created_at))).scalars().all()

    track_counts = dict(
        (await db.execute(select(Track.user_id, func.count()).group_by(Track.user_id))).all()
    )
    sess_rows = (
        await db.execute(
            select(
                InterviewSession.user_id,
                func.count(),
                func.coalesce(func.sum(InterviewSession.duration_minutes), 0),
            )
            .where(InterviewSession.status == "completed")
            .group_by(InterviewSession.user_id)
        )
    ).all()
    session_stats = {r[0]: (r[1], r[2]) for r in sess_rows}

    # Mongo: cost per user (attributed via meta.user_id on each call).
    cost_rows = await mongo_db.llm_call_logs.aggregate(
        [
            {
                "$group": {
                    "_id": "$meta.user_id",
                    "tokens": {"$sum": {"$add": ["$prompt_tokens", "$completion_tokens"]}},
                    "estimated_cost_usd": {"$sum": "$estimated_cost_usd"},
                }
            }
        ]
    ).to_list(1000)
    cost_by_user = {r["_id"]: r for r in cost_rows if r.get("_id")}

    reports = (
        await db.execute(
            select(FeedbackReport.user_id, FeedbackReport.content).order_by(
                FeedbackReport.created_at
            )
        )
    ).all()
    coverage_by_user: dict[str, list[int]] = {}
    coverage_score = {"excellent": 100, "good": 80, "partial": 50, "none": 10}
    for uid, content in reports:
        qa = content.get("question_assessments") or []
        scores = [coverage_score.get(q.get("coverage"), 0) for q in qa]
        if scores:
            coverage_by_user.setdefault(str(uid), []).append(round(sum(scores) / len(scores)))

    out = []
    for u in users:
        uid = str(u.id)
        c = cost_by_user.get(uid, {})
        scores = coverage_by_user.get(uid, [])
        out.append(
            {
                "id": uid,
                "email": u.email,
                "name": u.name,
                "tracks": track_counts.get(u.id, 0),
                "interviews_completed": session_stats.get(u.id, (0, 0))[0],
                "interview_minutes": session_stats.get(u.id, (0, 0))[1],
                "tokens": c.get("tokens") or 0,
                "estimated_cost_usd": round(float(c.get("estimated_cost_usd") or 0), 4),
                "avg_performance": round(sum(scores) / len(scores)) if scores else None,
            }
        )
    return out


async def user_detail(
    db: AsyncSession, mongo_db: AsyncIOMotorDatabase, user_id: uuid.UUID
) -> dict | None:
    user = await db.get(User, user_id)
    if user is None:
        return None

    tracks = (await db.execute(select(Track).where(Track.user_id == user_id))).scalars().all()
    sessions = (
        (
            await db.execute(
                select(InterviewSession)
                .where(InterviewSession.user_id == user_id)
                .order_by(InterviewSession.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    reports = (
        (await db.execute(select(FeedbackReport).where(FeedbackReport.user_id == user_id)))
        .scalars()
        .all()
    )

    cost_rows = await mongo_db.llm_call_logs.aggregate(
        [
            {"$match": {"meta.user_id": str(user_id)}},
            {
                "$group": {
                    "_id": None,
                    "calls": {"$sum": 1},
                    "tokens": {"$sum": {"$add": ["$prompt_tokens", "$completion_tokens"]}},
                    "estimated_cost_usd": {"$sum": "$estimated_cost_usd"},
                }
            },
        ]
    ).to_list(1)
    c = cost_rows[0] if cost_rows else {"calls": 0, "tokens": 0, "estimated_cost_usd": 0}

    report_by_session = {str(r.session_id): r.content for r in reports}

    return {
        "user": {"id": str(user.id), "email": user.email, "name": user.name},
        "llm": {
            "calls": c.get("calls") or 0,
            "tokens": c.get("tokens") or 0,
            "estimated_cost_usd": round(float(c.get("estimated_cost_usd") or 0), 4),
        },
        "tracks": [
            {"id": str(t.id), "subject": t.subject, "track_type": t.track_type} for t in tracks
        ],
        "sessions": [
            {
                "id": str(s.id),
                "mode": s.mode,
                "status": s.status,
                "minutes": s.duration_minutes if s.status == "completed" else 0,
                "started": s.created_at.isoformat(),
                "coverage_status": report_by_session.get(str(s.id), {}).get("coverage_status"),
            }
            for s in sessions
        ],
        "reports": [
            {
                "session_id": str(r.session_id),
                "coverage_status": r.content.get("coverage_status"),
                "summary_overview": r.content.get("summary_overview", "")[:200],
            }
            for r in reports
        ],
    }
