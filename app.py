import os
from flask import Flask, render_template, request, jsonify, session, redirect
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
# Flask 세션 사용을 위한 secret key 설정
# 개발 환경에서는 "dev-only-secret"을 기본값으로 사용하지만, 실제 배포 시에는 환경변수로 설정된 값을 사용하도록 합니다.
# 배포시 서버에 SECRET_KEY 환경변수 등록 되어있는지 확인, dev-only-secret 삭제
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret")

# 세션 쿠키 옵션 설정
# 보안을 강화하기 위해 세션 쿠키에 대한 옵션을 설정합니다.
# 배포 시에는 SESSION_COOKIE_SECURE를 True로 설정!!
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    SESSION_PERMANENT=False
)

# 배포시 서버에 MONGO_URI 환경변수 등록 되어있는지 확인, localhost:27017 삭제
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)

db = client.jungle

# std_id 필드에 고유 인덱스를 생성하여 중복된 std_id가 저장되지 않도록 합니다.
db.users.create_index("std_id", unique=True)

# API 응답을 일관된 형식으로 반환하기 위한 헬퍼 함수입니다. 실패 시 fail 함수를, 성공 시 ok 함수를 사용하여 응답을 반환합니다.
def fail(msg, code):
    return jsonify({"result": "fail", "msg": msg}), code

def ok(msg="success", data=None):
    payload = {"result": "success", "msg": msg}
    if data is not None:
        payload["data"] = data
    return jsonify(payload)

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return wrapper

@app.route('/')
@login_required
def home():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/signup')
def signup_page():
    return render_template('signup.html')

# 로그인 API에서는 사용자가 입력한 아이디와 비밀번호를 검증하여 세션에 사용자 정보를 저장합니다.
@app.route('/api/login', methods=['POST'])
def api_login():
    user_id = request.form.get('id_give', '').strip()
    user_pw = request.form.get('pw_give', '').strip()

    if not user_id or not user_pw:
        return fail("필수값 누락", 400)

    user = db.users.find_one({'std_id': user_id})

    if (not user) or (not check_password_hash(user.get('password', ''), user_pw)):
        return fail("아이디/비밀번호가 올바르지 않습니다", 401)

    session.clear()
    session['user_id'] = user['std_id']
    return ok("로그인 성공")

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

# 로그아웃 API에서는 세션을 초기화하여 사용자를 로그아웃 처리합니다.
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# 배포 시 debug 모드를 False로 설정!!
if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)