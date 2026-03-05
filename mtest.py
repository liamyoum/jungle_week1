import os
import time
import random
import jwt
import datetime
import secrets
from functools import wraps
from datetime import timedelta, datetime as dt

from flask import (
    Flask, render_template, request, jsonify, redirect,
    make_response, g
)
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash, check_password_hash

from flask_apscheduler import APScheduler

# =========================
# Config
# =========================
ACCESS_EXP_MINUTE = 20
REFRESH_EXP_DAYS = 1
HEARTBEAT_GRACE_MINUTES = 5

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-secret")
JWT_ALG = "HS256"

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "jungle")  # 하나로 통일

class Config:
    SCHEDULER_API_ENABLED = True

app = Flask(__name__)
app.config.from_object(Config())

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = client[DB_NAME]

# collections
# users: std_id unique
db.users.create_index("std_id", unique=True)

# sessions: user당 1개 세션만 유지
db.sessions.create_index("user_id", unique=True)
db.sessions.create_index("sid", unique=True)

# replies / quotes (필요하면 인덱스 추가)
db.replies.create_index("std_id", unique=True)

# =========================
# Scheduler
# =========================
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# =========================
# Time helpers (from 2nd)
# =========================
def sectoformat(totaltime: int):
    t1 = timedelta(seconds=totaltime)
    days = t1.days
    (hours, minutes, seconds) = str(timedelta(seconds=t1.seconds)).split(':')
    return {
        "days": days,
        "hours": int(hours),
        "minutes": int(minutes),
        "seconds": int(seconds),
    }

def timetosec(hour, minute, second):
    return second + minute * 60 + hour * 3600

def am4cal(timestamp: dt):
    # 새벽4시 기준 day rollover 계산
    if timestamp.hour > 3:
        return timetosec((timestamp.hour - 4), timestamp.minute, timestamp.second)
    else:
        return timetosec((timestamp.hour + 20), timestamp.minute, timestamp.second)

def utcnow():
    return datetime.datetime.utcnow()

# =========================
# API helpers
# =========================
def fail(msg, code):
    return jsonify({"result": "fail", "msg": msg}), code

def ok(msg="success", data=None):
    payload = {"result": "success", "msg": msg}
    if data is not None:
        payload["data"] = data
    return jsonify(payload)

# =========================
# JWT helpers (from 1st)
# =========================
def create_access_token(user_id: str, sid: str) -> str:
    now = utcnow()
    payload = {
        "user_id": user_id,
        "sid": sid,
        "type": "access",
        "exp": now + datetime.timedelta(minutes=ACCESS_EXP_MINUTE),
        "iat": now,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def create_refresh_token(user_id: str, sid: str) -> str:
    now = utcnow()
    payload = {
        "user_id": user_id,
        "sid": sid,
        "type": "refresh",
        "exp": now + datetime.timedelta(days=REFRESH_EXP_DAYS),
        "iat": now,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def verify_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

def issue_new_session(user_id: str):
    sid = secrets.token_urlsafe(24)
    now = utcnow()

    db.sessions.update_one(
        {"user_id": user_id},
        {"$set": {"sid": sid, "last_seen": now}},
        upsert=True
    )

    access = create_access_token(user_id, sid)
    refresh = create_refresh_token(user_id, sid)
    return sid, access, refresh

def validate_session_or_fail(user_id: str, sid: str):
    sess = db.sessions.find_one({"user_id": user_id})
    if not sess:
        return None, fail("세션 없음", 401)

    if sess.get("sid") != sid:
        return None, fail("다른 곳에서 로그인됨", 401)

    last_seen = sess.get("last_seen")
    if not last_seen:
        return None, fail("세션 오류", 401)

    if utcnow() - last_seen > datetime.timedelta(minutes=HEARTBEAT_GRACE_MINUTES):
        db.sessions.delete_one({"user_id": user_id})
        return None, fail("세션 만료", 401)

    return sess, None

# =========================
# Decorators
# =========================
def login_required_page(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.cookies.get("access_token")
        payload = verify_token(token) if token else None
        if not payload or payload.get("type") != "access":
            return redirect("/login")

        user_id = payload.get("user_id")
        sid = payload.get("sid")
        if not user_id or not sid:
            return redirect("/login")

        _, err = validate_session_or_fail(user_id, sid)
        if err:
            resp = make_response(redirect("/login"))
            resp.delete_cookie("access_token", path="/")
            resp.delete_cookie("refresh_token", path="/api")
            return resp

        g.user_id = user_id
        g.sid = sid
        return f(*args, **kwargs)
    return wrapper

def login_required_api(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.cookies.get("access_token")
        if not token:
            return fail("인증 필요", 401)

        payload = verify_token(token)
        if not payload or payload.get("type") != "access":
            return fail("토큰 만료/위조", 401)

        user_id = payload.get("user_id")
        sid = payload.get("sid")
        if not user_id or not sid:
            return fail("토큰 형식 오류", 401)

        _, err = validate_session_or_fail(user_id, sid)
        if err:
            return err

        g.user_id = user_id
        g.sid = sid
        return f(*args, **kwargs)
    return wrapper

# =========================
# Night reset (4 AM) (from 2nd, adapted)
# =========================
@scheduler.task("cron", hour="4", id="reset_at_4am")
def reset_at_4am():
    """
    기존 2번째 코드의 reset 로직:
    - today_times 비어있지 않으면 total_time +1 (원본이 이상하긴 한데 그대로 유지하면 '기능 보존')
    - today_times 비어있으면 total_time=0
    - start_time=None, today_times=[] 초기화
    """
    try:
        db.users.update_many({"today_times": {"$ne": []}}, {"$inc": {"total_time": 1}})
        db.users.update_many({"today_times": {"$eq": []}}, {"$set": {"total_time": 0}})
        db.users.update_many({}, {"$set": {"start_time": None, "today_times": []}})
        print("[RESET] done")
    except Exception as e:
        print("[RESET] error:", e)

# =========================
# Pages (합치기: '/'는 리더보드 포함 버전으로)
# =========================
@app.route("/")
@login_required_page
def home():
    # quote
    quotes = list(db.quotes.find({}, {"_id": False}))
    random_quote = random.choice(quotes)["text"] if quotes else "몰입의 즐거움!"

    # leaderboard
    leaderboard = list(db.users.find({}, {"_id": 0}).sort("total_time", -1))

    me = db.users.find_one({"std_id": g.user_id}, {"_id": 0})
    if not me:
        return redirect("/login")

    my_rank = 1
    for user in leaderboard:
        if user.get("std_id") == g.user_id:
            break
        my_rank += 1

    return render_template(
        "index.html",
        quote=random_quote,
        ranking_list=leaderboard[:30],
        my_rank=my_rank,
        my_name=me.get("nickname", g.user_id),
        my_total_time=me.get("total_time", 0),
    )

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/signup")
def signup_page():
    return render_template("signup.html")

# =========================
# Auth APIs (from 1st)
# =========================
@app.route("/api/login", methods=["POST"])
def api_login():
    user_id = request.form.get("id_give", "").strip()
    user_pw = request.form.get("pw_give", "").strip()

    if not user_id or not user_pw:
        return fail("아이디/비밀번호를 입력해주세요", 400)

    user = db.users.find_one({"std_id": user_id})
    if (not user) or (not check_password_hash(user.get("password", ""), user_pw)):
        return fail("아이디/비밀번호가 올바르지 않습니다", 401)

    _, access_token, refresh_token = issue_new_session(user["std_id"])

    resp = make_response(ok("로그인 성공"))
    resp.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=False,      # 운영 HTTPS면 True
        samesite="Lax",
        max_age=ACCESS_EXP_MINUTE * 60,
        path="/",
    )
    resp.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=False,      # 운영 HTTPS면 True
        samesite="Lax",
        max_age=REFRESH_EXP_DAYS * 24 * 60 * 60,
        path="/api",
    )
    return resp

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return fail("리프레시 토큰 없음", 401)

    payload = verify_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        return fail("리프레시 토큰 만료/위조", 401)

    user_id = payload.get("user_id")
    sid = payload.get("sid")
    if not user_id or not sid:
        return fail("리프레시 토큰 형식 오류", 401)

    _, err = validate_session_or_fail(user_id, sid)
    if err:
        return err

    new_access = create_access_token(user_id, sid)
    resp = make_response(ok("토큰 갱신 성공"))
    resp.set_cookie(
        "access_token",
        new_access,
        httponly=True,
        secure=False,
        samesite="Lax",
        max_age=ACCESS_EXP_MINUTE * 60,
        path="/",
    )
    return resp

@app.route("/api/signup", methods=["POST"])
def api_signup():
    std_id = request.form.get("id_give", "").strip()
    password = request.form.get("pw_give", "").strip()
    nickname = request.form.get("nick_give", "").strip()

    if not std_id or not password or not nickname:
        return fail("필수값 누락", 400)

    if len(password) < 4 or len(password) > 20:
        return fail("비밀번호는 4~20자", 400)
    if len(nickname) > 20:
        return fail("닉네임은 20자 이하", 400)

    # 2번째 코드와 호환되게 today_times 필드명 유지
    user = {
        "std_id": std_id,
        "nickname": nickname,
        "password": generate_password_hash(password),
        "start_time": None,
        "total_time": 0,
        "today_times": [],
        "friends": [],
        "ban_id": [],  # 2번째 코드 ban_id를 사용하므로 통일
    }

    try:
        db.users.insert_one(user)
    except DuplicateKeyError:
        return fail("이미 존재하는 아이디", 409)

    return ok("회원가입 성공")

@app.route("/logout")
def logout():
    token = request.cookies.get("access_token")
    payload = verify_token(token) if token else None
    if payload and payload.get("type") == "access":
        user_id = payload.get("user_id")
        if user_id:
            db.sessions.delete_one({"user_id": user_id})

    resp = make_response(redirect("/login"))
    resp.delete_cookie("access_token", path="/")
    resp.delete_cookie("refresh_token", path="/api")
    return resp

@app.route("/api/heartbeat", methods=["POST"])
@login_required_api
def heartbeat():
    db.sessions.update_one(
        {"user_id": g.user_id, "sid": g.sid},
        {"$set": {"last_seen": utcnow()}}
    )
    return ok("alive")

# =========================
# Study timer APIs (from 2nd, adapted to g.user_id)
# =========================
@app.route("/timerstart", methods=["POST"])
@login_required_api
def start_time():
    fmt = "%Y:%m:%d:%H:%M:%S"
    nowtime = time.strftime(fmt)

    startTimestamp = dt.strptime(nowtime, fmt)
    startTimestamp = am4cal(startTimestamp)

    target_user = db.users.find_one({"std_id": g.user_id}, {"_id": 0})
    if target_user is None:
        return jsonify({"result": "fail", "message": "no user_start"})

    today_times = target_user.get("today_times", [])
    if len(today_times) > 0:
        if int(startTimestamp) - int(today_times[-1]["end_time"]) < 10:
            return jsonify({"result": "fail", "message": "10초 후에 다시 시도해주세요!"})

    db.users.update_one({"std_id": g.user_id}, {"$set": {"start_time": nowtime}})
    return jsonify({"result": "success", "nowtime": nowtime})

@app.route("/timerend", methods=["POST"])
@login_required_api
def end_time():
    target_user = db.users.find_one({"std_id": g.user_id}, {"_id": 0})
    if target_user is None:
        return jsonify({"result": "fail", "message": "no user_end"})

    starttime = target_user.get("start_time")
    if starttime is None:
        return jsonify({"result": "fail", "message": "no_start_time"})

    totaltime = int(target_user.get("total_time", 0))
    todaytimes = target_user.get("today_times", [])

    fmt = "%Y:%m:%d:%H:%M:%S"
    nowtime = time.strftime(fmt)

    startTimestamp_dt = dt.strptime(starttime, fmt)
    endTimestamp_dt = dt.strptime(nowtime, fmt)

    thisSestime = endTimestamp_dt - startTimestamp_dt
    thisSestimesec = thisSestime.seconds + thisSestime.days * 86400
    if thisSestimesec < 3:
        return jsonify({"result": "fail", "message": "최소 3초 이상이여야 합니다!"})

    totaltime += thisSestimesec

    startTimestamp = am4cal(startTimestamp_dt)
    endTimestamp = am4cal(endTimestamp_dt)

    thisSestime_fmt = sectoformat(thisSestimesec)
    totaltimeret = sectoformat(totaltime)

    todaytimes.append({"start_time": str(startTimestamp), "end_time": str(endTimestamp)})

    db.users.update_one(
        {"std_id": g.user_id},
        {"$set": {"total_time": totaltime, "today_times": todaytimes, "start_time": None}}
    )

    return jsonify({
        "result": "success",
        "totaltime": totaltimeret,
        "thisSestime": thisSestime_fmt,
        "todaytimes": todaytimes
    })

# =========================
# Leaderboard / Memberlist / Profile / Replies (from 2nd, adapted)
# =========================
def listfilter(leaderboard_row, ids, mode="friend", key="std_id"):
    if mode == "friend":
        return leaderboard_row.get(key) in ids
    else:  # ban filter
        return leaderboard_row.get(key) not in ids

@app.route("/leaderboard", methods=["GET"])
@login_required_api
def load_leaderboard():
    filterMode = request.args.get("sortMode", "all")

    me = db.users.find_one({"std_id": g.user_id}, {"_id": 0})
    if me is None:
        return jsonify({"result": "fail", "message": "나는 없는 유저 정보입니다!"})

    leaderboard = list(db.users.find({}, {"_id": 0}).sort("total_time", -1))

    ban_ids = me.get("ban_id", [])
    if filterMode == "friends":
        friends = [g.user_id] + me.get("friends", [])
        leaderboard = list(filter(lambda x: listfilter(x, friends, "friend"), leaderboard))

    # ban 적용
    if ban_ids:
        leaderboard = list(filter(lambda x: listfilter(x, ban_ids, "ban"), leaderboard))

    myrank = 1
    for row in leaderboard:
        if row.get("std_id") == g.user_id:
            break
        myrank += 1

    myleaderboard = me
    out = leaderboard[:30] if len(leaderboard) > 30 else leaderboard
    return jsonify({
        "result": "success",
        "leaderboard": out,
        "myleader": myrank,
        "myleaderboard": myleaderboard
    })

@app.route("/memberlist", methods=["GET"])
@login_required_api
def load_memberlist():
    filterMode = request.args.get("sortMode", "Now")

    me = db.users.find_one({"std_id": g.user_id}, {"_id": 0})
    if me is None:
        return jsonify({"result": "fail", "message": "멤버 나는 없는 유저 정보입니다!"})

    ban_ids = me.get("ban_id", [])

    if filterMode == "Now":
        rows = list(db.users.find({"start_time": {"$ne": None}}, {"_id": 0}).sort("total_time", -1))
    elif filterMode == "friends":
        rows = list(db.users.find({}, {"_id": 0}).sort("total_time", -1))
        friends = me.get("friends", [])
        rows = list(filter(lambda x: listfilter(x, friends, "friend"), rows))
    elif filterMode == "bans":
        rows = list(db.users.find({}, {"_id": 0}).sort("total_time", -1))
        rows = list(filter(lambda x: listfilter(x, ban_ids, "friend"), rows)) if ban_ids else []
    else:
        return jsonify({"result": "fail", "message": "no current filter"})

    if ban_ids and filterMode != "bans":
        rows = list(filter(lambda x: listfilter(x, ban_ids, "ban"), rows))

    return jsonify({"result": "success", "memberlist": rows[:30]})

@app.route("/profile", methods=["GET"])
@login_required_api
def profileshow():
    profile = request.args.get("profile", g.user_id) or g.user_id

    target_user_profile = db.users.find_one({"std_id": profile}, {"_id": 0})
    if target_user_profile is None:
        return jsonify({"result": "fail", "message": "없는 프로필 유저 정보입니다!"})

    reply_doc = db.replies.find_one({"std_id": profile}, {"_id": 0})
    replys = reply_doc.get("replys", []) if reply_doc else []

    me = db.users.find_one({"std_id": g.user_id}, {"_id": 0}) or {}
    ban_ids = me.get("ban_id", [])

    if ban_ids:
        replys = [r for r in replys if r.get("id") not in ban_ids]

    return jsonify({"result": "success", "profile_inf": target_user_profile, "replys": replys})

@app.route("/profile", methods=["POST"])
@login_required_api
def writereply():
    text = request.args.get("replytext", "")
    person = request.args.get("person", "")
    if not person:
        return jsonify({"result": "fail", "message": "no_person"})
    if not text:
        return jsonify({"result": "fail", "message": "no_text"})

    # counter doc
    counter_doc = db.replies.find_one({"admin": 1}, {"_id": 0})
    if counter_doc is None:
        db.replies.insert_one({"admin": 1, "counter": 1})
        counter = 1
    else:
        counter = int(counter_doc.get("counter", 1)) + 1

    # upsert target replies
    target = db.replies.find_one({"std_id": person}, {"_id": 0})
    if target is None:
        db.replies.insert_one({
            "admin": 0,
            "std_id": person,
            "replys": [{"id": g.user_id, "reply": text, "reply_id": counter}]
        })
    else:
        db.replies.update_one(
            {"std_id": person},
            {"$push": {"replys": {"id": g.user_id, "reply": text, "reply_id": counter}}}
        )

    db.replies.update_one({"admin": 1}, {"$set": {"counter": counter}}, upsert=True)
    return jsonify({"result": "success", "reply_id": counter})

@app.route("/profile", methods=["DELETE"])
@login_required_api
def delreply():
    del_id = request.args.get("del_id", "")
    del_user = request.args.get("del_user", "")
    if not del_id or not del_user:
        return jsonify({"result": "fail", "message": "댓글 정보가 없습니다!"})

    try:
        del_id_int = int(del_id)
    except ValueError:
        return jsonify({"result": "fail", "message": "del_id 형식 오류"})

    db.replies.update_one({"std_id": del_user}, {"$pull": {"replys": {"reply_id": del_id_int}}})
    return jsonify({"result": "success"})

@app.route("/ban", methods=["POST"])
@login_required_api
def banuser():
    ban_id = request.args.get("ban_id", "")
    if not ban_id:
        return jsonify({"result": "fail", "message": "밴 없는 유저 정보입니다!"})
    if db.users.find_one({"std_id": ban_id}, {"_id": 0}) is None:
        return jsonify({"result": "fail", "message": "밴 없는 유저 정보입니다!"})

    db.users.update_one({"std_id": g.user_id}, {"$addToSet": {"ban_id": ban_id}})
    return jsonify({"result": "success"})

@app.route("/ban", methods=["DELETE"])
@login_required_api
def unbanuser():
    ban_id = request.args.get("ban_id", "")
    if not ban_id:
        return jsonify({"result": "fail", "message": "없는 유저 정보입니다!"})
    if db.users.find_one({"std_id": ban_id}, {"_id": 0}) is None:
        return jsonify({"result": "fail", "message": "없는 유저 정보입니다!"})

    db.users.update_one({"std_id": g.user_id}, {"$pull": {"ban_id": ban_id}})
    return jsonify({"result": "success"})

# Quotes
@app.route("/quotes", methods=["GET"])
@login_required_api
def randquote():
    quotes = list(db.quotes.find({}, {"_id": False}))
    if not quotes:
        return jsonify({"result": "fail", "message": "no quotes"})
    retquote = random.choice(quotes)
    return jsonify({"result": "success", "quote": retquote})

# =========================
# Run
# =========================
if __name__ == "__main__":
    app.run("0.0.0.0", port=5000, debug=True)