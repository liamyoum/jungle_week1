import time, random
from pymongo import MongoClient
from datetime import timedelta, datetime
from flask_apscheduler import APScheduler
from jinja2 import Environment, FileSystemLoader
import os
from flask import (
    Flask, render_template, request, jsonify, redirect,
    make_response, g
)
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import jwt
import secrets


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
db.user.create_index("std_id", unique=True)

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



def timecal():
    target_user = db.user.find_one({'std_id': g.user_id}, {'_id':0})
    print(target_user)
    if target_user is None:
        return {'result': 'fail','message':'no user_end'}
    if "start_time" in target_user: 
        if None ==target_user['start_time']:
            return {'result': 'fail','message':'no_start_time'}

        starttime=target_user['start_time']
    
    else:
        return {'result': 'fail','message':'no_start_time'}

    totaltime=target_user['total_time']
    todaytimes=target_user['todaytimes']

    fmt = '%Y:%m:%d:%H:%M:%S'

    nowtime= time.strftime(fmt)
    startTimestamp = datetime.strptime(starttime, fmt)
    endTimestamp = datetime.strptime(nowtime, fmt)

    thisSestime=endTimestamp-startTimestamp
    thisSestimesec=thisSestime.seconds + thisSestime.days*86400
    totaltime+=thisSestimesec

    startTimestamp=am4cal(startTimestamp)
    endTimestamp=am4cal(endTimestamp)

    thisSestime=sectoformat(thisSestimesec)
    totaltimeret=sectoformat(totaltime)
    if endTimestamp-startTimestamp<3:
        return {'result': 'fail','message':'최소 3초 이상이여야 합니다!'}

    todaytimes.append({'start_time': str(startTimestamp), 'end_time': str(endTimestamp)})
    

    db.user.update_one(
    {'std_id': g.user_id}, 
    {'$set': {
        'total_time': totaltime,
        'today_times':todaytimes,
        'start_time':None,
        'last_session':thisSestime
    }}      
    )
                                 
    return {'result':'success', 'totaltime':totaltimeret,'thisSestime':thisSestime,'todaytimes':todaytimes}

def utcnow():
    return datetime.utcnow()

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
        "exp": now + timedelta(minutes=ACCESS_EXP_MINUTE),
        "iat": now,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def create_refresh_token(user_id: str, sid: str) -> str:
    now = utcnow()
    payload = {
        "user_id": user_id,
        "sid": sid,
        "type": "refresh",
        "exp": now + timedelta(days=REFRESH_EXP_DAYS),
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

    if utcnow() - last_seen > timedelta(minutes=HEARTBEAT_GRACE_MINUTES):
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

    user = db.user.find_one({"std_id": user_id})
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
        "todaytimes": [],
        "friends": [],
        "ban_id": [],  # 2번째 코드 ban_id를 사용하므로 통일
    }

    try:
        db.user.insert_one(user)
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



## functions & class

#초를 받아서 일,시간,분,초로 출력하는 함수
#input=seconds 
#output={'days','hours','minutes','seconds'}

def sectoformat(totaltime):
    t1   = timedelta(seconds=totaltime)
    days = t1.days
    (hours, minutes, seconds) = str(timedelta(seconds=t1.seconds)).split(':')
    hours   = int(hours)
    minutes = int(minutes)
    seconds = int(seconds)
    ret={'days':days,'hours':hours,'minutes':minutes,'seconds':seconds}
    return ret

#리더보드와 친구 목록을 받아서 친구 목록에 해당하는지 bool로 출력
#input=leaderboard,list,mode="friend"
#output=bool type

def listfilter(leaderboard,list,mode="friend",str="std_"):
    if mode=="friend":
        for x in list :
            if x==leaderboard[str+'id'] :
                return True
        return False
    else:
        for x in list :
            if x==leaderboard[str+'id'] :
                return False
        return True


#새벽4시로부터 지난 초를 계산해주는 함수
#input=time
#output=seconds

def am4cal(timestamp):
    if(timestamp.hour>3):
        return timetosec((timestamp.hour-4),timestamp.minute,timestamp.second)
    else:
        return timetosec((timestamp.hour+20),timestamp.minute,timestamp.second)

#시,분,초를 받고 초로 합쳐서 출력

def timetosec(hour,minute,second):
            return second+minute*60+hour*3600

@app.route('/')
@login_required_page
def home():
    quotes = list(db.quotes.find({}, {'_id': False}))
    random_quote = random.choice(quotes)['text'] if quotes else "몰입의 즐거움!"

    returnleader=load_leaderboard("all")
    
    if returnleader['result'] == 'fail':
        return render_template('index.html')
    leaderboard = returnleader['leaderboard']

    me = returnleader['myleaderboard']
    return render_template('index.html', quote=random_quote, ranking_list=leaderboard, my_rank=returnleader['myleader'], my_name=me['std_id'], my_total_time=me['total_time'])

@app.route('/result')
@login_required_page
def result():
    endinfo = timecal()
    if endinfo['result'] == 'fail':
        # DB에서 유저 정보를 가져옵니다.
        user_info = db.user.find_one({'std_id': g.user_id}, {'_id':0})
        
        # KeyError 방지: ['last_session'] 대신 .get()을 사용하여 키가 없으면 0을 반환하게 합니다.
        if user_info:
            thisSestime = user_info.get('last_session', 0)
        else:
            thisSestime = 0
            
        if thisSestime == None:
            thisSestime = 0
    else:
        thisSestime = endinfo['thisSestime']
        
    returnleader = load_leaderboard()
    print("리턴 호출", endinfo, returnleader['result'])
    
    if returnleader['result'] == 'fail':
        return render_template('result.html')
    
    leaderboard = returnleader['leaderboard']
    me = returnleader['myleaderboard']
    
    return render_template('result.html', result='success', thisSestime=thisSestime, profile_inf=me, my_rank=returnleader['myleader'], ranking_list=leaderboard)


@scheduler.task('cron', hour='4',minute='0', id='reset')
@login_required_api
def reset():
    print("리셋 작동중!!!!")

    db.user.update_many({'today_times':{'$ne':[]}}, {'$inc':{'total_time':1}})
    db.user.update_many({'today_times':{'$eq':[]}}, {'$set':{'total_time':0}})

    db.user.update_many({},{'$set':{'start_time':None,'today_times':[]}})
    
## main codes

#현재 id(g.user_id)의 현재 시간을 '년:월:일:시간:분:초'로 저장
#output='nowtime':현재 시간
@app.route('/timerstart', methods=['POST'])
@login_required_api
def start_time():
    fmt='%Y:%m:%d:%H:%M:%S'
    nowtime= time.strftime(fmt)
    startTimestamp = datetime.strptime(nowtime, fmt)
    startTimestamp=am4cal(startTimestamp)
    print(g.user_id,"여기에 g")
    target_user = db.user.find_one({'std_id': g.user_id}, {'_id':0})
    if target_user is None:
        return jsonify({'result': 'fail','message':'no user_start'})
    if 'today_times' not in target_user:
        target_user['today_times']=[]
        
    if len(target_user['today_times']) > 0:
    
        if int(startTimestamp)-int(target_user['today_times'][-1]['end_time'])<10:
            return jsonify({'result': 'fail','message':'10초 후에 다시 시도해주세요!'})
        
    db.user.update_one(
            {'std_id': g.user_id},
            {'$set': {'start_time': nowtime}}
        )

    return jsonify({'result': 'success','nowtime':nowtime})

#현재 id의 진행되고 있는 시간 측정을 끝내는 함수
#output='totaltime':총 시간 초,'thisSestime':이번 세션 초,'todaytimes':총 시간
#todaytimes 구조 {'start_time', 'end_time'}

@app.route('/timerend', methods=['POST'])
@login_required_api # 추가된 데코레이터
def end_time():
    return jsonify(timecal())

#유저를 전부 읽어서 총 숫자를 내림차순으로 정렬 후 최대 30명까지 출력하는 함수
#input=sortMode->all,friends
#output='leaderboard':해당 인원들의 전체 정보,'myleader':내 순위 'myleaderboard':내 리더보드



def load_leaderboard(sortMode="all"):
    filterMode = sortMode
    me = db.user.find_one({'std_id': g.user_id}, {'_id':0})
    if me is None:
        return {'result':'fail','message':'나는 없는 유저 정보입니다!'}
    if filterMode == 'all':
        leaderboard = list(db.user.find({}, {'_id':0}).sort('total_time',-1))
        if 'ban_id' in me:
            leaderboard=list(filter(lambda x: listfilter(x, me['ban_id'],"ban"),leaderboard))

    elif filterMode =='friends':
        leaderboard = list(db.user.find({}, {'_id':0}).sort('total_time',-1))
        friends=[g.user_id]
        friends+=me['friends']
        leaderboard=list(filter(lambda x: listfilter(x, friends),leaderboard))
        if 'ban_id' in me :
            leaderboard=list(filter(lambda x: listfilter(x, me['ban_id'],"ban"),leaderboard))


    else:
        return {'result': 'fail','message':'no current filter'}
    
    myleader = db.user.find_one({'std_id':g.user_id}, {'_id':0})
    myrank=1
    for i in leaderboard:
        if i == me:
            break
        myrank+=1

    if len(leaderboard)>30 :
        return {'result':'success','leaderboard':leaderboard[:30],'myleader':myrank,'myleaderboard':myleader}
    else :
        return {'result':'success','leaderboard':leaderboard,'myleader':myrank,'myleaderboard':myleader}

#'profile'을 입력으로 받아서 해당 유저 정보를 출력하는 함수
#input='profile'->해당 유저 id 없을 시 현재 로그인한 유저
#output='profile_inf'->해당 유저의 정보 통째로 출력 'replys'->댓글 출력
#replys구조 'id':해당 댓글 작성자 'reply':해당 댓글 내용
@app.route('/profile', methods=['GET'])
def profileshow():
    profile = request.args.get('profile',g.user_id)
    if profile == '':
        profile=g.user_id
    
    target_user = db.reply.find_one({'std_id': profile}, {'admin':0,'_id':0})
    target_user_profile = db.user.find_one({'std_id': profile}, {'_id':0})
    
    if target_user_profile is None :
        return jsonify({'result':'fail','message':'없는 프로필 유저 정보입니다!'})
    
    if None != target_user:
        replys = target_user['replys']

    else:
        return jsonify({'result':'success','profile_inf':target_user_profile,'replys':[]})
    
    me = db.user.find_one({'std_id': g.user_id}, {'_id':0})
    if 'ban_id' in me :
        replys=list(filter(lambda x: listfilter(x, me['ban_id'],"ban",str=""),replys))

    return jsonify({'result':'success','profile_inf':target_user_profile,'replys':replys})

#memberlist 멤버리스트

@app.route('/memberlist', methods=['GET'])
def load_memberlist():
    filterMode = request.args.get('sortMode')
    me = db.user.find_one({'std_id': g.user_id}, {'_id':0})
    if me is None:
        return jsonify({'result':'fail','message':'멤버 나는 없는 유저 정보입니다!'})
    
    if filterMode == 'Now':
        leaderboard = list(db.user.find({'start_time':{'$ne':None}}, {'_id':0}).sort('total_time',-1))
        if 'ban_id' in me :
            leaderboard=list(filter(lambda x: listfilter(x, me['ban_id'],"ban"),leaderboard))
        return jsonify({'result':'success','memberlist':leaderboard[:30]})
        

    elif filterMode =='friends':
        leaderboard = list(db.user.find({}, {'_id':0}).sort('total_time',-1))
        friends=me['friends']
        leaderboard=list(filter(lambda x: listfilter(x, friends),leaderboard))
        if 'ban_id' in me :
            leaderboard=list(filter(lambda x: listfilter(x, me['ban_id'],"ban"),leaderboard))
        return jsonify({'result':'success','memberlist':leaderboard[:30]})

    elif filterMode =='bans':
        leaderboard = list(db.user.find({}, {'_id':0}).sort('total_time',-1))
        if 'ban_id' in me :
            leaderboard=list(filter(lambda x: listfilter(x, me['ban_id']),leaderboard))
            return jsonify({'result':'success','memberlist':leaderboard[:30]})
        else:
            return jsonify({'result':'success','memberlist':[]})


    else:
        return jsonify({'result': 'fail','message':'no current filter'})



@app.route('/ban',methods=['POST'])
def banuser():
    ban_id=request.args.get('ban_id','')
    if ban_id is None:
        return jsonify({'result':'fail','message':'밴 없는 유저 정보입니다!'})
    if db.user.find_one({'std_id': ban_id}, {'_id':0}) is None:
        return jsonify({'result':'fail','message':'밴 없는 유저 정보입니다!'})    
        
    db.user.update_one({'std_id': g.user_id},{'$push': {'ban_id': ban_id}})
    return jsonify({'result':'success'})
    
@app.route('/ban',methods=['DELETE'])
def unbanuser():
    ban_id=request.args.get('ban_id','')
    if ban_id is None:
        return jsonify({'result':'fail','message':'없는 유저 정보입니다!'})
    if db.user.find_one({'std_id': ban_id}, {'_id':0}) is None:
        return jsonify({'result':'fail','message':'없는 유저 정보입니다!'})
        
    db.user.update_one({'std_id': g.user_id},{'$pull': {'ban_id': ban_id}})
    return jsonify({'result':'success'})
    

#'person'과 'text'를 받아서 person의 댓글에 현재 계정으로 작성하는 함수
#input='text'->댓글 내용,'person'->누구에게 댓글을 쓰는지
@app.route('/profile', methods=['POST'])
def wirtereply():
    text=request.args.get('replytext','')
    person=request.args.get('person','')
    if person =='':
        return jsonify({'result': 'fail','message':'no_person'})
    if text =='':
        return jsonify({'result': 'fail','message':'no_text'})
    target_user = db.reply.find_one({'std_id': person}, {'_id':0})
    count=db.reply.find_one({'admin':1}, {'_id':0})
    if  count is None:
        db.reply.insert_one({'admin':1,'counter':1})
        count['counter']=0    
    
    countnum=count['counter']+1

    if target_user is None:
        db.reply.update_one(
            {'admin': 1},
            {'$set': {'counter': (countnum)}}
        )
        db.reply.insert_one({'admin':0,'std_id': person,'replys':[{'id':g.user_id,'reply':text,'reply_id':countnum}]})

    else:
        replys=target_user['replys']
        replys.append({'id':g.user_id,'reply':text,'reply_id':countnum})
        db.reply.update_one(
            {'std_id': person},
            {'$set': {'replys': replys}}
        )
        db.reply.update_one(
            {'admin': 1},
            {'$set': {'counter': (countnum)}}
        )
    return jsonify({'result':'success','reply_id':countnum})

#댓글의 id받아서 해당 댓글을 지움
#input='del_id' 지울 댓글 id
@app.route('/profile', methods=['DELETE'])
def delreply():    
    del_id=request.args.get('del_id','')
    del_user=request.args.get('del_user','')
    if del_id is None:
        return jsonify({'result':'fail','message':'댓글 정보가 없습니다!'})
    
    if db.reply.find_one({'std_id': del_user},{'replys': {'reply_id': del_id}}) is None:
        return jsonify({'result':'fail','message':'없는 댓글 정보입니다!'})    
    db.reply.update_one({'std_id': del_user},{'$pull': {'replys': {'reply_id': int(del_id)}}})
    return jsonify({'result':'success'})



#명언 랜덤 출력
#output='quote':명언 랜덤 하나
@app.route('/quotes', methods=['GET'])
def randquote():
    quotes = list(db.quotes.find({}, {'_id': False})) 
    if not quotes:
        return jsonify({'result': 'fail', 'message': 'no quotes'})
    retquote = random.choice(quotes) 
    return jsonify({'result': 'success', 'quote': retquote})









if __name__ == '__main__':


    
    app.run('0.0.0.0', port=5001, debug=True)
