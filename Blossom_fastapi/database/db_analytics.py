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
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from database.models import (
    DbAdminDevice, DbDateSpot, DbMatch, DbMessage, DbProfile, DbProfileLike, DbReport, DbSpotVoucher,
    DbUser, DbVisit, DbVisitPage,
)

SESSION = timedelta(minutes=30)
PLATFORMS = ("app", "web")
DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
# Crawlers and link previews that run pages: not people.
BOTS = re.compile(r"bot|crawl|spider|slurp|preview|lighthouse|headless|facebookexternalhit|embedly", re.I)


def _clean(value, length):
    value = " ".join(str(value or "").split())
    return value[:length] or None


MAX_PAGES_PER_VISIT = 300
# Page-by-page details are kept one week, then deleted (delete_old_pages):
# the table would otherwise grow forever. Visits themselves stay - the
# 7/30/90-day charts need them, and an older day still shows each visit with
# the page it started on.
PAGES_KEPT = timedelta(days=7)
# A long random segment in a path is a secret (a friend's activation link, a
# venue's manager link): never stored as such.
SECRET_SEGMENT = re.compile(r"/[A-Za-z0-9_-]{16,}(?=/|$)")
NUMBER_SEGMENT = re.compile(r"/\d+(?=/|$)")


def clean_path(value):
    """"/claim/Xk3...9" -> "/claim/:token", "/profile/42" -> "/profile/:id"."""
    path = _clean(value, 200)
    if not path:
        return None
    path = path.split("?")[0].split("#")[0]
    path = SECRET_SEGMENT.sub("/:token", path)
    path = NUMBER_SEGMENT.sub("/:id", path)
    return path[:120] or None


def delete_old_pages(db: Session, now: datetime = None) -> int:
    """Delete the pages seen more than a week ago. Returns how many."""
    now = now or datetime.utcnow()
    deleted = db.query(DbVisitPage).filter(DbVisitPage.at < now - PAGES_KEPT).delete(synchronize_session=False)
    db.commit()
    return deleted


def _add_page(db: Session, visit: DbVisit, path, now: datetime):
    """Note the page seen - not again when it's the one already noted (a
    reload, the app coming back, a keep-alive)."""
    path = clean_path(path)
    if not path or visit.id is None:
        return
    last = (
        db.query(DbVisitPage.path)
        .filter(DbVisitPage.visit_id == visit.id)
        .order_by(DbVisitPage.at.desc(), DbVisitPage.id.desc())
        .first()
    )
    if last and last[0] == path:
        return
    count = db.query(func.count(DbVisitPage.id)).filter(DbVisitPage.visit_id == visit.id).scalar() or 0
    if count >= MAX_PAGES_PER_VISIT:
        return
    db.add(DbVisitPage(visit_id=visit.id, at=now, path=path))


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
        _add_page(db, current, entry, now)
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
            _add_page(db, before_login, entry, now)
            db.commit()
            return {"counted": True, "reason": "logged in during the visit"}

    visit = DbVisit(
        created_at=now,
        last_seen_at=now,
        visitor=visitor,
        profile_id=profile_id,
        device_id=device_id,
        platform=platform,
        entry=clean_path(entry),
        language=(_clean(language, 8) or "").lower()[:2] or None,
        timezone=_clean(timezone, 64),
    )
    db.add(visit)
    db.flush()
    _add_page(db, visit, entry, now)
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


# ---- one day in detail ------------------------------------------------------------

MAX_PEOPLE = 300


def _iso(value):
    return value.isoformat(timespec="seconds") + "Z" if value else None


def _counts(rows):
    """[(profile_id, n), ...] -> {profile_id: n}"""
    return {pid: n for pid, n in rows if pid is not None}


def _pair_counts(db: Session, column_time, first, second, start, end):
    """Both people of a match / a couple's gift code count it."""
    result = Counter()
    for a, b in db.query(first, second).filter(column_time >= start, column_time < end).all():
        result[a] += 1
        result[b] += 1
    return result


def _member_actions(db: Session, start: datetime, end: datetime) -> dict:
    """What each member did that day - counts only: never message contents,
    nor whom they liked or wrote to."""
    actions = defaultdict(dict)

    def put(name, counts):
        for pid, n in counts.items():
            if pid and n:
                actions[pid][name] = n

    put("likes", _counts(
        db.query(DbProfileLike.liker_profile_id, func.count(DbProfileLike.id))
        .filter(DbProfileLike.created_at >= start, DbProfileLike.created_at < end)
        .group_by(DbProfileLike.liker_profile_id).all()))
    put("matches", _pair_counts(db, DbMatch.matched_at, DbMatch.profile1_id, DbMatch.profile2_id, start, end))
    put("messages", _counts(
        db.query(DbMessage.sender_profile_id, func.count(DbMessage.id))
        .filter(DbMessage.created_at >= start, DbMessage.created_at < end, DbMessage.date_spot_id.is_(None))
        .group_by(DbMessage.sender_profile_id).all()))
    put("invites", _counts(
        db.query(DbMessage.sender_profile_id, func.count(DbMessage.id))
        .filter(DbMessage.created_at >= start, DbMessage.created_at < end, DbMessage.date_spot_id.isnot(None))
        .group_by(DbMessage.sender_profile_id).all()))
    put("spots_shared", _counts(
        db.query(DbDateSpot.profile_id, func.count(DbDateSpot.id))
        .filter(DbDateSpot.created_at >= start, DbDateSpot.created_at < end)
        .group_by(DbDateSpot.profile_id).all()))
    put("gift_codes", _pair_counts(
        db, DbSpotVoucher.created_at, DbSpotVoucher.profile1_id, DbSpotVoucher.profile2_id, start, end))
    put("gifts_used", _pair_counts(
        db, DbSpotVoucher.used_at, DbSpotVoucher.profile1_id, DbSpotVoucher.profile2_id, start, end))
    put("reports", _counts(
        db.query(DbReport.reporter_profile_id, func.count(DbReport.id))
        .filter(DbReport.created_at >= start, DbReport.created_at < end)
        .group_by(DbReport.reporter_profile_id).all()))

    for pid, created, completed, signed_up in (
        db.query(DbProfile.id, DbProfile.created_at, DbProfile.completed_at, DbUser.created_at)
        .join(DbUser, DbUser.id == DbProfile.user_id)
        .filter(
            ((DbProfile.created_at >= start) & (DbProfile.created_at < end))
            | ((DbProfile.completed_at >= start) & (DbProfile.completed_at < end))
            | ((DbUser.created_at >= start) & (DbUser.created_at < end))
        ).all()
    ):
        if signed_up and start <= signed_up < end:
            actions[pid]["signed_up"] = 1
        if created and start <= created < end:
            actions[pid]["profile_created"] = 1
        if completed and start <= completed < end:
            actions[pid]["profile_finished"] = 1
    return actions


def day_detail(db: Session, day: date = None, tz_offset_minutes: int = 0, now: datetime = None):
    """Everyone who came on one day (the admin's day), with the pages they saw
    and, for members, what they did. Admins are left out, as everywhere."""
    now = now or datetime.utcnow()
    offset = timedelta(minutes=max(-840, min(840, int(tz_offset_minutes or 0))))
    day = day or (now + offset).date()
    start = datetime.combine(day, datetime.min.time()) - offset  # UTC
    end = start + timedelta(days=1)

    admin_profile_ids = {
        pid for (pid,) in db.query(DbProfile.id).join(DbUser, DbUser.id == DbProfile.user_id)
        .filter(DbUser.is_admin == True).all()  # noqa: E712
    }
    visits = [
        v for v in db.query(DbVisit).filter(DbVisit.created_at >= start, DbVisit.created_at < end)
        .order_by(DbVisit.created_at).all()
        if v.profile_id not in admin_profile_ids
    ]
    pages = defaultdict(list)
    if visits:
        for page in (
            db.query(DbVisitPage).filter(DbVisitPage.visit_id.in_([v.id for v in visits]))
            .order_by(DbVisitPage.at, DbVisitPage.id).all()
        ):
            pages[page.visit_id].append({"path": page.path, "at": _iso(page.at)})

    # Visitors' phones/browsers already seen before this day.
    devices = {v.device_id for v in visits if not v.profile_id and v.device_id}
    seen_before = {
        d for (d,) in db.query(DbVisit.device_id)
        .filter(DbVisit.device_id.in_(devices), DbVisit.created_at < start).distinct().all()
    } if devices else set()

    actions = _member_actions(db, start, end)
    for pid in admin_profile_ids:
        actions.pop(pid, None)

    people = {}
    for v in visits:
        person = people.setdefault(v.visitor, {
            "key": v.visitor,
            "profile_id": v.profile_id,
            "device": (v.device_id or "")[-4:].upper() or None,
            "visits": [],
        })
        person["visits"].append({
            "start": _iso(v.created_at),
            "end": _iso(v.last_seen_at),
            "seconds": int((v.last_seen_at - v.created_at).total_seconds()),
            "platform": v.platform,
            "language": v.language,
            "timezone": v.timezone,
            # Visits recorded before pages were: just the page they came in on.
            "pages": pages.get(v.id) or ([{"path": v.entry, "at": _iso(v.created_at)}] if v.entry else []),
        })
    # Members who did something without a recorded visit (older app versions).
    for pid in actions:
        people.setdefault(f"p:{pid}", {"key": f"p:{pid}", "profile_id": pid, "device": None, "visits": []})

    profiles = {
        p.id: p for p in db.query(DbProfile).options(selectinload(DbProfile.photos))
        .filter(DbProfile.id.in_([p["profile_id"] for p in people.values() if p["profile_id"]])).all()
    } if people else {}

    result = []
    for person in people.values():
        visits_of = person["visits"]
        pid = person["profile_id"]
        profile = profiles.get(pid) if pid else None
        first = min((x["start"] for x in visits_of), default=None)
        last = max((x["end"] for x in visits_of), default=None)
        latest = visits_of[-1] if visits_of else {}
        result.append({
            "key": person["key"],
            "member": {
                "id": profile.id,
                "first_name": profile.first_name,
                "age": profile.age,
                "gender": profile.gender,
                "city": profile.city,
                "country": profile.country,
                "photo": sorted(profile.photos, key=lambda ph: ph.id)[0].image_url if profile.photos else None,
            } if profile else None,
            "device": person["device"],
            "returning": (person["device"] is not None and not pid and any(
                v.device_id in seen_before for v in visits if v.visitor == person["key"])),
            "first_at": first,
            "last_at": last,
            "seconds": sum(x["seconds"] for x in visits_of),
            "platforms": sorted({x["platform"] for x in visits_of if x["platform"]}),
            "language": latest.get("language"),
            "timezone": latest.get("timezone"),
            "visits": visits_of,
            "actions": actions.get(pid, {}) if pid else {},
        })
    result.sort(key=lambda p: p["last_at"] or "", reverse=True)

    hours = [0] * 24
    for v in visits:
        hours[(v.created_at + offset).hour] += 1
    members = [p for p in result if p["member"]]
    return {
        "date": day.isoformat(),
        "tz_offset_minutes": int(offset.total_seconds() // 60),
        "totals": {
            "people": len(result),
            "members": len(members),
            "visitors": len(result) - len(members),
            "visits": len(visits),
            "app": sum(1 for v in visits if v.platform == "app"),
            "web": sum(1 for v in visits if v.platform == "web"),
            "pages": sum(len(v["pages"]) for p in result for v in p["visits"]),
            "new_accounts": sum(1 for p in members if p["actions"].get("signed_up")),
            "new_profiles": sum(1 for p in members if p["actions"].get("profile_finished")),
            "seconds": sum(p["seconds"] for p in result),
        },
        "hours": hours,
        "people": result[:MAX_PEOPLE],
        "truncated": len(result) > MAX_PEOPLE,
    }
