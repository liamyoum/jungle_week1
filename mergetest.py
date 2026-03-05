from flask import Flask, render_template, jsonify, request
import time, random
from pymongo import MongoClient
from datetime import datetime, timedelta
from flask_apscheduler import APScheduler
from jinja2 import Environment, FileSystemLoader
import os
from flask import Flask, render_template, request, jsonify, session, redirect
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps


app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    SESSION_PERMANENT=False
)


MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)

db = client.junglemergetest

db.user.create_index("std_id", unique=True)

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
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return wrapper

def login_required_api(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return fail("인증 필요", 401)
        return f(*args, **kwargs)
    return wrapper

def timecal():
    target_user = db.user.find_one({'std_id': session['user_id']}, {'_id':0})
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
    {'std_id': session['user_id']}, 
    {'$set': {
        'total_time': totaltime,
        'today_times':todaytimes,
        'start_time':None
    }}      
    )
                                 
    return {'result':'success', 'totaltime':totaltimeret,'thisSestime':thisSestime,'todaytimes':todaytimes}

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
def result():
    endinfo=timecal()
    returnleader=load_leaderboard()
    print("리턴 호출",endinfo['thisSestime'],returnleader['result'])
    if returnleader['result'] == 'fail':
        return render_template('result.html',message="error")
    
    leaderboard = returnleader['leaderboard']
    me = returnleader['myleaderboard']


    
    return render_template('result.html',result='success',thisSestime=endinfo['thisSestime'],profile_inf=me,my_rank=returnleader['myleader'],ranking_list=leaderboard)


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

    user = db.user.find_one({'std_id': user_id})

    if (not user) or (not check_password_hash(user.get('password', ''), user_pw)):
        return fail("아이디/비밀번호가 올바르지 않습니다", 401)

    session.clear()
    session['user_id'] = user['std_id']
    return ok("로그인 성공")

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
        db.user.insert_one(user)
    except DuplicateKeyError:
        return fail("이미 존재하는 아이디", 409)

    return ok("회원가입 성공")

# 로그아웃 API에서는 세션을 초기화하여 사용자를 로그아웃 처리합니다.
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')



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

class Config:
    SCHEDULER_API_ENABLED = True

## pre-settings
file_loader = FileSystemLoader('C:/path/templates')
env = Environment(loader=file_loader)



app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    SESSION_PERMANENT=False
)
app.config.from_object(Config())

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()





# std_id 필드에 고유 인덱스를 생성하여 중복된 std_id가 저장되지 않도록 합니다.
db.user.create_index("std_id", unique=True)
## server-reset

@scheduler.task('cron', hour='7',minute='42', id='reset')
def reset():
    print("리셋 작동중!!!!")

    db.user.update_many({'today_times':{'$ne':[]}}, {'$inc':{'total_time':1}})
    db.user.update_many({'today_times':{'$eq':[]}}, {'$set':{'total_time':0}})

    db.user.update_many({},{'$set':{'start_time':None,'today_times':[]}})
    
## main codes

#현재 id(session['user_id'])의 현재 시간을 '년:월:일:시간:분:초'로 저장
#output='nowtime':현재 시간
@app.route('/timerstart', methods=['POST'])
def start_time():
    fmt='%Y:%m:%d:%H:%M:%S'
    nowtime= time.strftime(fmt)
    startTimestamp = datetime.strptime(nowtime, fmt)
    startTimestamp=am4cal(startTimestamp)
    target_user = db.user.find_one({'std_id': session['user_id']}, {'_id':0})
    if target_user is None:
        return jsonify({'result': 'fail','message':'no user_start'})
    if 'today_times' not in target_user:
        target_user['today_times']=[]
        
    if len(target_user['today_times']) > 0:
    
        if int(startTimestamp)-int(target_user['today_times'][-1]['end_time'])<10:
            return jsonify({'result': 'fail','message':'10초 후에 다시 시도해주세요!'})
        
    db.user.update_one(
            {'std_id': session['user_id']},
            {'$set': {'start_time': nowtime}}
        )

    return jsonify({'result': 'success','nowtime':nowtime})

#현재 id의 진행되고 있는 시간 측정을 끝내는 함수
#output='totaltime':총 시간 초,'thisSestime':이번 세션 초,'todaytimes':총 시간
#todaytimes 구조 {'start_time', 'end_time'}

@app.route('/timerend', methods=['POST'])
def end_time():
              
    return jsonify(timecal())

#유저를 전부 읽어서 총 숫자를 내림차순으로 정렬 후 최대 30명까지 출력하는 함수
#input=sortMode->all,friends
#output='leaderboard':해당 인원들의 전체 정보,'myleader':내 순위 'myleaderboard':내 리더보드



def load_leaderboard(sortMode="all"):
    filterMode = sortMode
    me = db.user.find_one({'std_id': session['user_id']}, {'_id':0})
    if me is None:
        return {'result':'fail','message':'나는 없는 유저 정보입니다!'}
    if filterMode == 'all':
        leaderboard = list(db.user.find({}, {'_id':0}).sort('total_time',-1))
        if 'ban_id' in me:
            leaderboard=list(filter(lambda x: listfilter(x, me['ban_id'],"ban"),leaderboard))

    elif filterMode =='friends':
        leaderboard = list(db.user.find({}, {'_id':0}).sort('total_time',-1))
        friends=[session['user_id']]
        friends+=me['friends']
        leaderboard=list(filter(lambda x: listfilter(x, friends),leaderboard))
        if 'ban_id' in me :
            leaderboard=list(filter(lambda x: listfilter(x, me['ban_id'],"ban"),leaderboard))


    else:
        return {'result': 'fail','message':'no current filter'}
    
    myleader = db.user.find_one({'std_id':session['user_id']}, {'_id':0})
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
    profile = request.args.get('profile',session['user_id'])
    if profile == '':
        profile=session['user_id']
    
    target_user = db.reply.find_one({'std_id': profile}, {'admin':0,'_id':0})
    target_user_profile = db.user.find_one({'std_id': profile}, {'_id':0})
    
    if target_user_profile is None :
        return jsonify({'result':'fail','message':'없는 프로필 유저 정보입니다!'})
    
    if None != target_user:
        replys = target_user['replys']

    else:
        return jsonify({'result':'success','profile_inf':target_user_profile,'replys':[]})
    
    me = db.user.find_one({'std_id': session['user_id']}, {'_id':0})
    if 'ban_id' in me :
        replys=list(filter(lambda x: listfilter(x, me['ban_id'],"ban",str=""),replys))

    return jsonify({'result':'success','profile_inf':target_user_profile,'replys':replys})

#memberlist 멤버리스트

@app.route('/memberlist', methods=['GET'])
def load_memberlist():
    filterMode = request.args.get('sortMode')
    me = db.user.find_one({'std_id': session['user_id']}, {'_id':0})
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
        
    db.user.update_one({'std_id': session['user_id']},{'$push': {'ban_id': ban_id}})
    return jsonify({'result':'success'})
    
@app.route('/ban',methods=['DELETE'])
def unbanuser():
    ban_id=request.args.get('ban_id','')
    if ban_id is None:
        return jsonify({'result':'fail','message':'없는 유저 정보입니다!'})
    if db.user.find_one({'std_id': ban_id}, {'_id':0}) is None:
        return jsonify({'result':'fail','message':'없는 유저 정보입니다!'})
        
    db.user.update_one({'std_id': session['user_id']},{'$pull': {'ban_id': ban_id}})
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
        db.reply.insert_one({'admin':0,'std_id': person,'replys':[{'id':session['user_id'],'reply':text,'reply_id':countnum}]})

    else:
        replys=target_user['replys']
        replys.append({'id':session['user_id'],'reply':text,'reply_id':countnum})
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
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return wrapper

def login_required_api(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return fail("인증 필요", 401)
        return f(*args, **kwargs)
    return wrapper






if __name__ == '__main__':
    db.quotes.delete_many({})
    quotess=[ {"text":"빨리 가려면 혼자 가고, 멀리 가려면 함께 가라. — 아프리카 속담"},
              {"text":"혼자서 할 수 있는 일은 작지만, 함께 할 수 있는 일은 위대하다. — 헬렌 켈러"},
             {"text": "모이는 것은 시작이고, 함께 머무는 것은 진보이며, 같이 일하는 것은 성공이다. — 헨리 포드"},
             {"text": "교향곡을 혼자서 휘파람으로 불 수는 없다. 그것을 연주하려면 오케스트라가 필요하다. — H.E. 루콕"},
            {"text":  "우리는 모두 한 날개로만 나는 천사들이다. 서로를 껴안아야만 날 수 있다. — 루치아노 데 크레센초"},
            {"text":  "우정이란 누군가에게 ‘뭐라고? 너도 그래? 나만 그런 줄 알았는데!’라고 말하는 순간 태어난다. — C.S. 루이스"},
           {"text":   "고난은 진정한 친구를 가려내는 시험대다. — 아리스토텔레스"},
            {"text":  "진정한 친구는 세상 모두가 나갈 때 우리 안으로 들어오는 사람이다. — 월터 윈첼"},
           {"text":   "누군가와 고통을 나누는 것은 그 고통을 반으로 줄이는 것이 아니라, 견딜 수 있는 힘을 두 배로 만드는 것이다. — 작자 미상 (유명 격언)"},
           {"text":   "우리는 서로의 용기가 되어야 한다. — 마야 안젤루"},
           {"text":   "천재성은 혼자서 빛날 수 있지만, 승리는 팀워크와 지성이 모여야 가능하다. — 마이클 조던"},
           {"text":   "재능은 게임에서 이기게 하지만, 팀워크와 이해력은 챔피언을 만든다. — 마이클 조던"},
          {"text":    "개미는 작지만 모이면 사자를 이긴다. — 에티오피아 속담"},
           {"text":   "스스로 빛을 내는 별보다, 서로를 비추는 별들이 더 밝은 법이다."},
           {"text":   "당신이 다른 사람의 배를 강 건너로 저어다 주면, 당신도 어느덧 강 건너에 도착해 있을 것이다. — 인도 속담"}]

    db.quotes.insert_many(quotess)

    # 기존 데이터 삭제 (테스트 환경 초기화)
    db.user.delete_many({})
    db.reply.delete_many({})

    # 30명의 테스트 유저 생성
    mock_users = []
    for i in range(1, 31):
        std_id2 = str(1000 + i) # 1001 ~ 1030
        user = {
            "std_id": std_id2,
            "start_time": None,
            "total_time": random.randint(500, 1000), # 500초~10000초 랜덤
            "today_times": [],
            "friends": [], 
            "ban_id": []
            
            
        }
        
        # 친구 관계 랜덤 설정 (일부 유저에게 친구 추가)
        if i % 3 == 0:
            user["friends"] = ["44"]
        
        mock_users.append(user)

        # 1557번 유저 추가 (메인 테스트 계정)
    mock_users.append({
            "std_id": "44",
            "start_time": None,
            "total_time": 3600,
            "today_times": [],
            "friends": ["1003", "1006", "1009"],
            "ban_id": [],
            "nickname":"테스트닉네임"
        })
    reply_data = [
        {
            "admin": 0,
            "std_id": "44", # 1557번 유저 프로필에 달린 댓글들
            "replys": [
                {"id": "1005", "reply": "1557님, 오늘 공부 정말 열심히 하시네요!", "reply_id": 1},
                {"id": "1010", "reply": "대단해요! 저도 자극받고 갑니다.", "reply_id": 2}
            ]
        },
        {
            "admin": 0,
            "std_id": "1005", # 1005번 유저 프로필에 달린 댓글들
            "replys": [
                {"id": "44", "reply": "맞팔해요! 1005님 화이팅!", "reply_id": 3}
            ]
        },
        {
            "admin": 1,
            "counter": 4 # 다음 댓글 ID는 4부터 시작하도록 설정
        }
    ]
    db.reply.insert_many(reply_data)

    # 데이터 삽입
    db.user.insert_many(mock_users)

    
    app.run('0.0.0.0', port=5001, debug=True)
