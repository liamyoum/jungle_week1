from flask import Flask, render_template, jsonify, request
import time, random
from pymongo import MongoClient
from datetime import datetime, timedelta
from flask_apscheduler import APScheduler

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
#input=leaderboard,friendslist 
#output=bool type

def friendfilter(leaderboard,friendslist):
    for x in friendslist :
        if x==leaderboard['std_id'] :
            return True
    return False

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

app = Flask(__name__)
client = MongoClient('localhost', 27017)
app.config.from_object(Config())

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

db = client.dbjungle

testid='1557'

## server-reset

@scheduler.task('cron', hour='4', id='reset')
def reset():
    print("리셋 작동중!!!!")

    db.user.update_many({'today_times':{'$ne':[]}}, {'$inc':{'total_time':1}})
    db.user.update_many({'today_times':{'$eq':[]}}, {'$set':{'total_time':0}})

    db.user.update_many({},{'$set':{'start_time':None,'today_times':[]}})
    
## main codes

@app.route('/')
def home():
    db.quotes.delete_many({})
    quotess=["ㅁㄴㅇㄹ",'asdf','qwer']
    db.user.delete_many({})
    users = [
        {
            'std_id': '1557',
            'name': '나(테스트)',
            'total_time': 3600,
            'start_time': None,
            'today_times': [],
            'friends': ['user2', 'user3'],
            'replys': []
        },
        {
            'std_id': 'user2',
            'name': '친구1',
            'total_time': 7200,
            'start_time': None,
            'today_times': [],
            'friends': ['1557'],
            'replys': [{'id': 'user3', 'reply': '열공하세요!'}]
        },
        {
            'std_id': 'user3',
            'name': '친구2',
            'total_time': 5000,
            'start_time': None,
            'today_times': [],
            'friends': ['1557'],
            'replys': []
        },
        {
            'std_id': 'user4',
            'name': '모르는사람',
            'total_time': 10000,
            'start_time': None,
            'today_times': [],
            'friends': [],
            'replys': []
        }
    ]
    db.quotes.insert_many(quotess)
    db.user.insert_many(users)
    return render_template('index.html')

#현재 id(testid)의 현재 시간을 '년:월:일:시간:분:초'로 저장
#output='nowtime':현재 시간
@app.route('/timerstart', methods=['POST'])
def start_time():
    nowtime= time.strftime('%Y:%m:%d:%H:%M:%S')
    target_user = db.user.find_one({'std_id': testid}, {'_id':0})

    if target_user is None:
        return jsonify({'result': 'fail','message':'no user'})

    else:
        
        db.user.update_one(
            {'std_id': testid},
            {'$set': {'start_time': nowtime}}
        )

    return jsonify({'result': 'success','nowtime':nowtime})

#현재 id의 진행되고 있는 시간 측정을 끝내는 함수
#output='totaltime':총 시간 초,'thisSestime':이번 세션 초,'todaytimes':총 시간
#todaytimes 구조 {'start_time', 'end_time'}

@app.route('/timerend', methods=['POST'])
def giime():

    target_user = db.user.find_one({'std_id': testid}, {'_id':0})
    if "start_time" in target_user: 
        if None ==target_user['start_time']:
            return jsonify({'result': 'fail','message':'no_start_time'})

        starttime=target_user['start_time']
    
    else:
        return jsonify({'result': 'fail','message':'no_start_time'})

    totaltime=target_user['total_time']
    todaytimes=target_user['today_times']

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
    
    todaytimes.append({'start_time': str(startTimestamp), 'end_time': str(endTimestamp)})

    db.user.update_one(
    {'std_id': testid}, 
    {'$set': {
        'total_time': totaltime,
        'today_times':todaytimes,
        'start_time':None
    }}      
    )
                                 
    return jsonify({'result':'success', 'totaltime':totaltimeret,'thisSestime':thisSestime,'todaytimes':todaytimes})

#유저를 전부 읽어서 총 숫자를 내림차순으로 정렬 후 최대 30명까지 출력하는 함수
#input=sortMode->all,friends
#output='leaderboard':해당 인원들의 전체 정보,'myleader':내 순위 'myleaderboard':내 리더보드

@app.route('/leaderboard', methods=['GET'])
def load_leaderboard():
    filterMode = request.args.get('sortMode', 'all')
    me = db.user.find_one({'std_id': testid}, {'_id':0})
    if filterMode == 'all':
        leaderboard = list(db.user.find({}, {'_id':0}).sort('total_time',-1))
    elif filterMode =='friends':
        leaderboard = list(db.user.find({}, {'_id':0}).sort('total_time',-1))
        friends=[testid]
        friends+=me['friends']
        leaderboard=list(filter(lambda x: friendfilter(x, friends),leaderboard))
    else:
        return jsonify({'result': 'fail','message':'no current filter'})
    
    myleader = db.user.find({'std_id':testid}, {'_id':0})
    myrank=1
    for i in leaderboard:
        if i == me:
            break
        myrank+=1

    if len(leaderboard)>30 :
        return jsonify({'result':'success','leaderboard':leaderboard[:30],'myleader':myrank,'myleaderboard':myleader})
    else :
        return jsonify({'result':'success','leaderboard':leaderboard,'myleader':myrank,'myleaderboard':myleader})

#'profile'을 입력으로 받아서 해당 유저 정보를 출력하는 함수
#input='profile'->해당 유저 id 없을 시 현재 로그인한 유저
#output='profile_inf'->해당 유저의 정보 통째로 출력 'replys'->댓글 출력
#replys구조 'id':해당 댓글 작성자 'reply':해당 댓글 내용
@app.route('/profile', methods=['GET'])
def profileshow():
    profile = request.args.get('profile',testid)
    if profile == '':
        profile=testid
    
    target_user = db.user.find_one({'std_id': profile}, {'_id': 0})
    
    if 'replys' in target_user:
        replys = target_user['replys']

    else:
        return jsonify({'result':'success','profile_inf':target_user,'replys':''})
    
    
    

    return jsonify({'result':'success','profile_inf':target_user,'replys':replys})



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
    target_user = db.user.find_one({'std_id': person}, {'_id':0})


    if target_user is None:
        return jsonify({'result': 'fail','message':'no_avaiable_user'})

    if 'replys' in target_user:

        replys=target_user['replys']
        replys.append({'id':testid,'reply':text})
        db.user.update_one(
            {'std_id': person},
            {'$set': {'replys': replys}}
        )

    else:
        replys=[{'id':testid,'reply':text}]
        db.user.update_one(
            {'std_id': person},
            {'$set': {'replys': replys}}
        )
    return jsonify({'result':'success'})

#명언 랜덤 출력
#output='quote':명언 랜덤 하나
@app.route('/quotes', methods=['GET'])
def randquote():
    quotes=db.quotes.find({},{'_id':False})
    retquote=random.shuffle(quotes)
    return jsonify({'result':'success','quote':retquote})


if __name__ == '__main__':
    
    app.run('0.0.0.0', port=5000, debug=True)

