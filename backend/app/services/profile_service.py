"""User profile serialization and updates."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

_MAX_SKILLS = 40
_MAX_SKILL_LEN = 64


def user_dict(user: User) -> dict:
    skills = user.skills if isinstance(user.skills, list) else []
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name or "",
        "picture_url": user.picture_url,
        "professional_title": user.professional_title or "",
        "introduction": user.introduction or "",
        "skills": [str(s) for s in skills],
        "education": user.education or "",
        "onboarding_completed": user.onboarding_completed_at is not None,
        "onboarding_completed_at": (
            user.onboarding_completed_at.isoformat() if user.onboarding_completed_at else None
        ),
    }


async def update_profile(db: AsyncSession, user: User, data: dict) -> dict:
    if "name" in data and data["name"] is not None:
        user.name = str(data["name"]).strip()[:255]
    if "professional_title" in data and data["professional_title"] is not None:
        title = str(data["professional_title"]).strip()[:255]
        user.professional_title = title or None
    if "introduction" in data and data["introduction"] is not None:
        intro = str(data["introduction"]).strip()[:4000]
        user.introduction = intro or None
    if "education" in data and data["education"] is not None:
        edu = str(data["education"]).strip()[:4000]
        user.education = edu or None
    if "picture_url" in data:
        pic = data["picture_url"]
        if pic is None or str(pic).strip() == "":
            user.picture_url = None
        else:
            user.picture_url = str(pic).strip()[:1024]
    if "skills" in data and data["skills"] is not None:
        raw = data["skills"]
        if not isinstance(raw, list):
            raise ValueError("skills_must_be_list")
        cleaned: list[str] = []
        for item in raw[:_MAX_SKILLS]:
            s = str(item).strip()[:_MAX_SKILL_LEN]
            if s and s not in cleaned:
                cleaned.append(s)
        user.skills = cleaned
    await db.commit()
    await db.refresh(user)
    return user_dict(user)
