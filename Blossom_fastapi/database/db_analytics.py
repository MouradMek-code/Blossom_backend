"""Who visits the app and the website - the admin dashboard.

Rules (what the owner asked for):
  * admins are never counted - neither logged in, nor later logged out on a
    phone or browser they used as admin;
  * a member (someone with a profile) counts once per period, however often
    they come;
  * someone without a profile (a visitor, or someone still signing up) counts
    at every visit.

A visit is one sitting: activity within 30 minutes of the last one continues
it (a reload or moving between pages isn't a new visit). When someone logs in
during a visit, that visit becomes theirs instead of counting twice.
"""
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import DbAdminDevice, DbProfile, DbUser, DbVisit

SESSION = timedelta(minutes=30)
PLATFORMS = ("app", "web")
DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
# Crawlers and link previews that run pages: not people.
BOTS = re.compile(r"bot|crawl|spider|slurp|preview|lighthouse|headless|facebookexternalhit|embedly", re.I)


def _clean(value, length):
    value = " ".join(str(value or "").split())
    return value[:length] or None


def record_visit(db: Session, user, device_id: str, platform: str, entry=None, language=None,
                 timezone=None, user_agent: str = "", now: datetime = None):
    """Returns {"counted": bool, "reason": ...}. Never raises for bad input
    from a client - a broken tracker must not break the app."""
    now = now or datetime.utcnow()
    if not device_id or not DEVICE_ID.match(device_id):
        return {"counted": False, "reason": "bad device"}
    if BOTS.search(user_agent or ""):
        return {"counted": False, "reason": "bot"}
    platform = platform if platform in PLATFORMS else "web"

    if user is not None and getattr(user, "is_admin", False):
        # Remember this phone/browser, and forget what it did before the admin
        # logged in on it.
        if not db.get(DbAdminDevice, device_id):
            db.add(DbAdminDevice(device_id=device_id))
        db.query(DbVisit).filter(DbVisit.device_id == device_id, DbVisit.profile_id.is_(None)).delete(
            synchronize_session=False)
        db.commit()
        return {"counted": False, "reason": "admin"}
    if db.get(DbAdminDevice, device_id):
        return {"counted": False, "reason": "admin device"}

    profile_id = None
    if user is not None:
        profile_id = db.query(DbProfile.id).filter(DbProfile.user_id == user.id).scalar()
    visitor = f"p:{profile_id}" if profile_id else f"d:{device_id}"
    since = now - SESSION

    # Still the same visit: just note they're still here.
    current = (
        db.query(DbVisit)
        .filter(DbVisit.visitor == visitor, DbVisit.last_seen_at >= since)
        .order_by(DbVisit.last_seen_at.desc())
        .first()
    )
    if current:
        current.last_seen_at = now
        db.commit()
        return {"counted": False, "reason": "same visit"}

    # Logged in during a visit: that visit was theirs all along.
    if profile_id:
        before_login = (
            db.query(DbVisit)
            .filter(DbVisit.device_id == device_id, DbVisit.profile_id.is_(None), DbVisit.last_seen_at >= since)
            .order_by(DbVisit.last_seen_at.desc())
            .first()
        )
        if before_login:
            before_login.visitor = visitor
            before_login.profile_id = profile_id
            before_login.last_seen_at = now
            db.commit()
            return {"counted": True, "reason": "logged in during the visit"}

    db.add(DbVisit(
        created_at=now,
        last_seen_at=now,
        visitor=visitor,
        profile_id=profile_id,
        device_id=device_id,
        platform=platform,
        entry=_clean(entry, 120),
        language=(_clean(language, 8) or "").lower()[:2] or None,
        timezone=_clean(timezone, 64),
    ))
    db.commit()
    return {"counted": True, "reason": "new visit"}


# ---- dashboard ------------------------------------------------------------------

def _top(counter: Counter, limit=6):
    """The biggest entries, the rest folded into "other"."""
    items = counter.most_common()
    top = [{"key": key, "value": value} for key, value in items[:limit]]
    rest = sum(value for _, value in items[limit:])
    if rest:
        top.append({"key": "other", "value": rest})
    return top


def dashboard(db: Session, days: int = 30, tz_offset_minutes: int = 0, now: datetime = None):
    """Everything the admin dashboard shows, for the last `days` days in the
    admin's time zone (tz_offset_minutes: minutes ahead of UTC, e.g. 120 for
    Paris in summer), compared with the `days` before."""
    now = now or datetime.utcnow()
    offset = timedelta(minutes=max(-840, min(840, int(tz_offset_minutes or 0))))
    local_now = now + offset
    today = local_now.date()
    first_day = today - timedelta(days=days - 1)
    start = datetime.combine(first_day, datetime.min.time()) - offset  # UTC
    prev_start = start - timedelta(days=days)
    today_start = datetime.combine(today, datetime.min.time()) - offset

    rows = (
        db.query(DbVisit.created_at, DbVisit.profile_id, DbVisit.platform, DbVisit.entry,
                 DbVisit.language, DbVisit.timezone)
        .filter(DbVisit.created_at >= prev_start)
        .all()
    )
    admin_profile_ids = {
        pid for (pid,) in db.query(DbProfile.id).join(DbUser, DbUser.id == DbProfile.user_id)
        .filter(DbUser.is_admin == True).all()  # noqa: E712
    }

    def visitors(visits):
        members = {v.profile_id for v in visits if v.profile_id}
        anonymous = sum(1 for v in visits if not v.profile_id)
        return members, anonymous

    current = [v for v in rows if v.created_at >= start and v.profile_id not in admin_profile_ids]
    previous = [v for v in rows if v.created_at < start and v.profile_id not in admin_profile_ids]
    cur_members, cur_anon = visitors(current)
    prev_members, prev_anon = visitors(previous)
    today_members, today_anon = visitors([v for v in current if v.created_at >= today_start])

    # New people: accounts, profiles, finished profiles (2 photos), admins aside.
    def created_between(column, lo, hi):
        return [
            (when,) for (when,) in db.query(column)
            .join(DbUser, DbUser.id == DbProfile.user_id)
            .filter(column >= lo, column < hi, DbUser.is_admin == False)  # noqa: E712
            .all()
        ]

    finished_cur = created_between(DbProfile.completed_at, start, now + timedelta(seconds=1))
    finished_prev = created_between(DbProfile.completed_at, prev_start, start)
    profiles_cur = created_between(DbProfile.created_at, start, now + timedelta(seconds=1))
    accounts_cur = db.query(func.count(DbUser.id)).filter(
        DbUser.created_at >= start, DbUser.is_admin == False).scalar() or 0  # noqa: E712

    # Day by day, in the admin's time zone.
    per_day_members = defaultdict(set)
    per_day_anon = Counter()
    for v in current:
        day = (v.created_at + offset).date()
        if v.profile_id:
            per_day_members[day].add(v.profile_id)
        else:
            per_day_anon[day] += 1
    per_day_new = Counter((when + offset).date() for (when,) in finished_cur)
    daily = []
    for i in range(days):
        day = first_day + timedelta(days=i)
        daily.append({
            "date": day.isoformat(),
            "members": len(per_day_members[day]),
            "anonymous": per_day_anon[day],
            "new_profiles": per_day_new[day],
        })

    # Breakdowns count visitors the same way as the totals: someone without a
    # profile per visit, a member once - under the value they use most (their
    # latest on a tie), so each breakdown adds up to the visitors total.
    ordered = sorted(current, key=lambda v: v.created_at)

    def breakdown(key):
        total = Counter()
        member_values = defaultdict(Counter)
        latest = {}
        for v in ordered:
            value = key(v)
            if not v.profile_id:
                total[value or "unknown"] += 1
            elif value:
                member_values[v.profile_id][value] += 1
                latest[v.profile_id] = value
        for pid in cur_members:
            values = member_values.get(pid)
            if not values:
                total["unknown"] += 1
                continue
            best = max(values.values())
            favourite = latest[pid] if values[latest[pid]] == best else values.most_common(1)[0][0]
            total[favourite] += 1
        return total

    hours = [0] * 24
    for v in current:
        hours[(v.created_at + offset).hour] += 1

    # Members who came back on at least two different days.
    member_days = defaultdict(set)
    member_visits = Counter()
    for v in current:
        if v.profile_id:
            member_days[v.profile_id].add((v.created_at + offset).date())
            member_visits[v.profile_id] += 1
    week_start = datetime.combine(today - timedelta(days=6), datetime.min.time()) - offset

    members_total = db.query(func.count(DbProfile.id)).join(DbUser, DbUser.id == DbProfile.user_id).filter(
        DbUser.is_admin == False).scalar() or 0  # noqa: E712
    finished_total = db.query(func.count(DbProfile.id)).join(DbUser, DbUser.id == DbProfile.user_id).filter(
        DbUser.is_admin == False, DbProfile.completed_at.isnot(None)).scalar() or 0  # noqa: E712

    def rate(new, visits):
        return round(100 * new / visits, 1) if visits else None

    return {
        "period": {"days": days, "from": first_day.isoformat(), "to": today.isoformat(),
                   "tz_offset_minutes": int(offset.total_seconds() // 60)},
        "kpis": {
            "visitors": {"value": len(cur_members) + cur_anon, "previous": len(prev_members) + prev_anon},
            "members": {"value": len(cur_members), "previous": len(prev_members)},
            "anonymous": {"value": cur_anon, "previous": prev_anon},
            "new_profiles": {"value": len(finished_cur), "previous": len(finished_prev)},
            "signup_rate": {"value": rate(len(finished_cur), cur_anon), "previous": rate(len(finished_prev), prev_anon)},
        },
        "today": {
            "visitors": len(today_members) + today_anon,
            "members": len(today_members),
            "anonymous": today_anon,
            "new_profiles": per_day_new[today],
        },
        "daily": daily,
        "hours": hours,
        "platforms": _top(breakdown(lambda v: v.platform), 2),
        "languages": _top(breakdown(lambda v: v.language)),
        "timezones": _top(breakdown(lambda v: v.timezone)),
        "entries": _top(breakdown(lambda v: v.entry)),
        "funnel": [
            {"key": "visits", "value": cur_anon},
            {"key": "accounts", "value": accounts_cur},
            {"key": "profiles", "value": len(profiles_cur)},
            {"key": "finished", "value": len(finished_cur)},
        ],
        "community": {
            "members_total": members_total,
            "finished_total": finished_total,
            "active_week": len({v.profile_id for v in current if v.profile_id and v.created_at >= week_start}),
            "returning": sum(1 for days_seen in member_days.values() if len(days_seen) >= 2),
            "visits_per_member": round(sum(member_visits.values()) / len(member_visits), 1) if member_visits else 0,
        },
    }
