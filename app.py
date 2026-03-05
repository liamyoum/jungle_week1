import os
import jwt
import datetime
import secrets
from flask import Flask, render_template, request, jsonify, redirect, make_response, g
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# Config
ACCESS_EXP_MINUTE = 20
REFRESH_EXP_DAYS = 1
HEARTBEAT_GRACE_MINUTES = 5

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-secret")
JWT_ALG = "HS256"

app = Flask(__name__)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = client.jungle

db.users.create_index("std_id", unique=True)

# sessions
# user_id: 사용자당 1개 세션만 유지
# sid: access token에 포함되는 session id
db.sessions.create_index("user_id", unique=True)
db.sessions.create_index("sid", unique=True)

def utcnow():
    return datetime.datetime.utcnow()

# JWT
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

def fail(msg, code):
    return jsonify({"result": "fail", "msg": msg}), code

def ok(msg="success", data=None):
    payload = {"result": "success", "msg": msg}
    if data is not None:
        payload["data"] = data
    return jsonify(payload)

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

    # 다른 기기 로그인/재로그인으로 sid가 바뀌었으면 기존 access는 즉시 무효
    if sess.get("sid") != sid:
        return None, fail("다른 곳에서 로그인됨", 401)

    last_seen = sess.get("last_seen")
    if not last_seen:
        return None, fail("세션 오류", 401)

    if utcnow() - last_seen > datetime.timedelta(minutes=HEARTBEAT_GRACE_MINUTES):
        db.sessions.delete_one({"user_id": user_id})
        return None, fail("세션 만료", 401)

    return sess, None

# Decorators
def login_required_page(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.cookies.get("access_token")
        payload = verify_token(token) if token else None
        if not payload or payload.get("type") != "access":
            return redirect('/login')

        user_id = payload.get("user_id")
        sid = payload.get("sid")

        if not user_id or not sid:
            return redirect('/login')

        _, err = validate_session_or_fail(user_id, sid)
        if err:
            # 세션이 만료면 쿠키도 지우고 로그인으로
            resp = make_response(redirect('/login'))
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

# Pages
@app.route('/')
@login_required_page
def home():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/signup')
def signup_page():
    return render_template('signup.html')

# API
@app.route('/api/login', methods=['POST'])
def api_login():
    user_id = request.form.get('id_give', '').strip()
    user_pw = request.form.get('pw_give', '').strip()

    if not user_id or not user_pw:
        return fail("아이디/비밀번호를 입력해주세요", 400)

    user = db.users.find_one({'std_id': user_id})
    if (not user) or (not check_password_hash(user.get('password', ''), user_pw)):
        return fail("아이디/비밀번호가 올바르지 않습니다", 401)

    _, access_token, refresh_token = issue_new_session(user['std_id'])

    resp = make_response(ok("로그인 성공"))

    resp.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=False,
        samesite="Lax",
        max_age=ACCESS_EXP_MINUTE * 60,
        path="/"
    )

    resp.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=False,
        samesite="Lax",
        max_age=REFRESH_EXP_DAYS * 24 * 60 * 60,
        path="/api"
    )

    return resp

@app.route('/api/refresh', methods=['POST'])
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

    # refresh 시에도 세션/하트비트 강제
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
        path="/"
    )
    return resp

# 회원가입
@app.route('/api/signup', methods=['POST'])
def api_signup():
    std_id = request.form.get('id_give', '').strip()
    password = request.form.get('pw_give', '').strip()
    nickname = request.form.get('nick_give', '').strip()

    if not std_id or not password or not nickname:
        return fail("필수값 누락", 400)

    if len(password) < 4 or len(password) > 20:
        return fail("비밀번호는 4~20자", 400)
    if len(nickname) > 20:
        return fail("닉네임은 20자 이하", 400)

    user = {
        'std_id': std_id,
        'nickname': nickname,
        'password': generate_password_hash(password),
        'start_time': None,
        'total_time': 0,
        'combo': None,
        'todaytimes': [],
        'friends': [],
        'blockedUsers': []
    }

    try:
        db.users.insert_one(user)
    except DuplicateKeyError:
        return fail("이미 존재하는 아이디", 409)

    return ok("회원가입 성공")

@app.route('/logout')
def logout():
    # 서버 세션 삭제(강제 종료)
    token = request.cookies.get("access_token")
    payload = verify_token(token) if token else None
    if payload and payload.get("type") == "access":
        user_id = payload.get("user_id")
        if user_id:
            db.sessions.delete_one({"user_id": user_id})

    resp = make_response(redirect('/login'))
    resp.delete_cookie("access_token", path="/")
    resp.delete_cookie("refresh_token", path="/api")
    return resp

# Heartbeat
@app.route('/api/heartbeat', methods=['POST'])
@login_required_api
def heartbeat():
    db.sessions.update_one(
        {"user_id": g.user_id, "sid": g.sid},
        {"$set": {"last_seen": utcnow()}}
    )
    return ok("alive")

# Run
if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)