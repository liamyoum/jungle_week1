from flask import Flask, render_template, request, jsonify
app = Flask(__name__)

from pymongo import MongoClient
client = MongoClient('localhost', 27017)
db = client.jungle

# all_users = list(db.users.find({}))

# for user in all_users:
#     print(user)

@app.route('/main')
def home():
   return render_template('index.html')

@app.route('/login')
def login():
   return render_template('login.html')

@app.route('/register')
def register():
   return render_template('register.html')

if __name__ == '__main__':  
   app.run('0.0.0.0', port=5000, debug=True)