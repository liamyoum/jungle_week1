from flask import Flask, render_template, request, jsonify, session, redirect
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "SECRET_KEY"

client = MongoClient('localhost', 27017)
db = client.jungle

@app.route('/')
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
        return jsonify({'result': 'fail', 'msg': '누락'}), 400

    user = db.users.find_one({'std_id': user_id})
    if not user:
        return jsonify({'result': 'fail', 'msg': '존재하지 않는 계정'}), 401

    if not check_password_hash(user.get('password',''), user_pw):
        return jsonify({'result': 'fail', 'msg': '아이디/비번 불일치'}), 401

    session['user_id'] = user['std_id']
    session['nickname'] = user.get('nickname', '')

    return jsonify({'result': 'success'})

@app.route('/api/signup', methods=['POST'])
def api_signup():
    std_id = request.form.get('std_id', '').strip()
    password = request.form.get('password', '').strip()
    nickname = request.form.get('nickname', '').strip()

    if not std_id or not password or not nickname:
        return jsonify({'result': 'fail', 'msg': '누락'}), 400

    if db.users.find_one({'std_id': std_id}):
        return jsonify({'result': 'fail', 'msg': '이미 존재하는 아이디'}), 409

    user = {
        'std_id': std_id,
        'nickname': nickname,
        'password': generate_password_hash(password),
        'start_time': 0,
        'total_time': 0,
        'combo': 0,
        'todaytimes': [],
        'friends': [],
        'blockedUsers': []
    }

    db.users.insert_one(user)
    return jsonify({'result': 'success'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)