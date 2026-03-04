from flask import Flask, render_template, jsonify, request
app = Flask(__name__)
import time
import requests
from pymongo import MongoClient
from datetime import datetime, timedelta

from flask_apscheduler import APScheduler
from apscheduler.schedulers.background import BackgroundScheduler




class Config:
    SCHEDULER_API_ENABLED = True



app = Flask(__name__)
client = MongoClient('localhost', 27017)
app.config.from_object(Config())

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()





db = client.dbjungle
testid='1557'

def sectoformat(totaltime):
    t1   = timedelta(seconds=totaltime)
    days = t1.days
    (hours, minutes, seconds) = str(timedelta(seconds=t1.seconds)).split(':')
    hours   = int(hours)
    minutes = int(minutes)
    seconds = int(seconds)
    ret={'days':days,'hours':hours,'minutes':minutes,'seconds':seconds}
    return ret

def friendfilter(leaderboard,friendslist):
    for x in friendslist :
        if x==leaderboard['std_id'] :
            return True
    return False

@scheduler.task('cron', hour='4', id='reset')
def reset():
    print("리셋 작동중!!!!")

    db.user.update_many({'today_times':{'$ne':[]}}, {'$inc':{'total_time':1}})
    db.user.update_many({'today_times':{'$eq':[]}}, {'$set':{'total_time':0}})

    db.user.update_many({},{'$set':{'start_time':None,'today_times':[]}})
    






@app.route('/')
def home():
    return render_template('index.html')

@app.route('/timerstart', methods=['POST'])
def start_time():
    nowtime= time.strftime('%Y:%m:%d:%H:%M:%S')
    target_user = db.user.find_one({'std_id': 'test'})


    if target_user is None:
        return jsonify({'result': 'fail'})

    else:
        
        db.user.update_one(
            {'std_id': testid},
            {'$set': {'start_time': nowtime}}
        )

    return jsonify({'result': 'success','nowtime':nowtime})



@app.route('/timerend', methods=['POST'])
def end_time():

    target_user = db.user.find_one({'std_id': 'test'})
    if "start_time" in target_user: 
        if None ==target_user['start_time']:
            return jsonify({'result': 'fail','message':'no_start'})

        starttime=target_user['start_time']
    
    else:
        return jsonify({'result': 'fail','message':'no_start'})

    totaltime=target_user['total_time']
    todaytimes=target_user['today_times']
    fmt = '%Y:%m:%d:%H:%M:%S'
    nowtime= time.strftime(fmt)
    pastTimestamp = datetime.strptime(starttime, fmt)
    nowTimestamp = datetime.strptime(nowtime, fmt)
    test=nowTimestamp-pastTimestamp
    test=test.seconds+test.days*86400
    totaltime+=test
    if(pastTimestamp.hour>3):
        pastTimestamp=pastTimestamp.second+pastTimestamp.minute*60+(pastTimestamp.hour-4)*1440
    else:
        pastTimestamp=pastTimestamp.second+pastTimestamp.minute*60+(20+pastTimestamp.hour)*1440
    if(nowTimestamp.hour>3):
        nowTimestamp=nowTimestamp.second+nowTimestamp.minute*60+(nowTimestamp.hour-4)*1440
    else:
        nowTimestamp=nowTimestamp.second+nowTimestamp.minute*60+(20+nowTimestamp.hour)*1440
    test=sectoformat(test)
    totaltimeret=sectoformat(totaltime)
    
    start_end = {'start_time': str(pastTimestamp), 'end_time': str(nowTimestamp)}
    todaytimes.append(start_end)
    db.user.update_one(
    {'std_id': testid}, 
    {'$set': {
        'total_time': totaltime,
        'today_times':todaytimes,
        'start_time':None
    }}      
    )
                                 
    return jsonify({'result':'success', 'totaltime':totaltimeret,'todaytime':test,'todaytimes':todaytimes})

@app.route('/leaderboard', methods=['GET'])
def load_leaderboard():
    sortMode = request.args.get('sortMode', 'all')
    me = db.user.find_one({'std_id': 'test'})
    if sortMode == 'all':
        leaderboard = list(db.user.find({}, {'_id':0}).sort('total_time',-1))
    elif sortMode =='friends':
        leaderboard = list(db.user.find({}, {'_id':0}).sort('total_time',-1))
        leaderboard=list(filter(lambda x: friendfilter(x, me['friends']),leaderboard))
    else:
        return jsonify({'result': 'failure'})
    count=1
    for i in leaderboard:
        if i == me:
            break
        count+=1

    if len(leaderboard)>30 :
        return jsonify({'result':'success','leaderboard':leaderboard[:30],'myleader':count})
    else :
        return jsonify({'result':'success','leaderboard':leaderboard,'myleader':count})
    
@app.route('/profile', methods=['GET'])
def profileshow():
    profile = request.args.get('profile', testid)
    target_user = db.user.find_one({'std_id': testid})
    return jsonify({'result':'success','profile':target_user})



if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)

