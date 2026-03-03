from flask import Flask, render_template, jsonify, request
app = Flask(__name__)
import time
import requests
from pymongo import MongoClient
from datetime import datetime, timedelta

client = MongoClient('localhost', 27017)  # mongoDB는 27017 포트로 돌아갑니다.
db = client.dbjungle  # 'dbjungle'라는 이름의 db를 만들거나 사용합니다.
testid='test'

def sectoformat(totaltime):
    t1   = timedelta(seconds=totaltime)
    days = t1.days
    (hours, minutes, seconds) = str(timedelta(seconds=t1.seconds)).split(':')
    hours   = int(hours)
    minutes = int(minutes)
    seconds = int(seconds)
    ret={'days':days,'hours':hours,'minutes':minutes,'seconds':seconds}
    return ret


@app.route('/timerstart', methods=['POST'])
def test_timestart():
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
def test_timeend():

    target_user = db.user.find_one({'std_id': 'test'})
    starttime=target_user['star_time']
    totaltime=target_user['total_time']
    fmt = '%Y:%m:%d:%H:%M:%S'
    nowtime= time.strftime(fmt)
    pastTimestamp = datetime.strptime(starttime, fmt)
    nowTimestamp = datetime.strptime(nowtime, fmt)

    test=nowTimestamp-pastTimestamp
    test=test.seconds+test.days*86400
    totaltime+=test

    test=sectoformat(test)
    totaltimeret=sectoformat(totaltime)
    
    db.user.update_one(
    {'std_id': testid}, 
    {'$set': {
        'total_time': totaltime
    }}  
    )                                   
    return jsonify({'result':'success', 'totaltime':totaltimeret,'todaytime':test})


