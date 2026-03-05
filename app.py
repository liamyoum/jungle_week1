import os
import jwt
import datetime
from flask import Flask, render_template, request, jsonify, redirect, make_response, g
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

ACCESS_EXP_MINUTE = 20
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-secret")
JWT_ALG = "HS256"

app = Flask(__name__)

# 배포시 서버에 MONGO_URI 환경변수 등록 되어있는지 확인, localhost:27017 삭제
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = client.jungle

# std_id 필드에 고유 인덱스를 생성하여 중복된 std_id가 저장되지 않도록 합니다.
db.users.create_index("std_id", unique=True)

def create_access_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_EXP_MINUTE),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def verify_access_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# API 응답을 일관된 형식으로 반환하기 위한 헬퍼 함수입니다. 실패 시 fail 함수를, 성공 시 ok 함수를 사용하여 응답을 반환합니다.
def fail(msg, code):
    return jsonify({"result": "fail", "msg": msg}), code

def ok(msg="success", data=None):
    payload = {"result": "success", "msg": msg}
    if data is not None:
        payload["data"] = data
    return jsonify(payload)

def login_required_page(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.cookies.get("access_token")
        payload = verify_access_token(token) if token else None
        if not payload:
            return redirect('/login')
        return f(*args, **kwargs)
    return wrapper

def login_required_api(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.cookies.get("access_token")
        if not token:
            return fail("인증 필요", 401)

        payload = verify_access_token(token)
        if not payload:
            return fail("토큰 만료/위조", 401)

        # 이후 핸들러에서 g.user_id로 접근 가능
        g.user_id = payload["user_id"]
        return f(*args, **kwargs)
    return wrapper

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

@app.route('/api/login', methods=['POST'])
def api_login():
    user_id = request.form.get('id_give', '').strip()
    user_pw = request.form.get('pw_give', '').strip()

    if not user_id or not user_pw:
        return fail("필수값 누락", 400)

    user = db.users.find_one({'std_id': user_id})
    if (not user) or (not check_password_hash(user.get('password', ''), user_pw)):
        return fail("아이디/비밀번호가 올바르지 않습니다", 401)

    token = create_access_token(user['std_id'])

    resp = make_response(ok("로그인 성공"))
    resp.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=False,      # 배포(HTTPS)면 True
        samesite="Lax",
        max_age=ACCESS_EXP_MINUTE * 60,
        path="/"
    )
    return resp

# 회원가입 API에서는 새로운 사용자를 데이터베이스에 저장하며, 이미 존재하는 아이디로 회원가입을 시도할 경우 적절한 오류 메시지를 반환합니다.
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

    # 이미 존재하는 std_id로 회원가입을 시도할 경우 DuplicateKeyError가 발생합니다.
    try:
        db.users.insert_one(user)
    except DuplicateKeyError:
        return fail("이미 존재하는 아이디", 409)

    return ok("회원가입 성공")

@app.route('/logout')
def logout():
    resp = make_response(redirect('/login'))
    resp.delete_cookie("access_token", path="/")
    return resp

# 배포 시 debug 모드를 False로 설정!!
if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)