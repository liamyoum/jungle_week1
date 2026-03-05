import random
import os
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash

# DB 연결 설정
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://test:test@localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "jungle")
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

def generate_dummy_data():
    print("🚀 실감 나는 사람 이름으로 더미 데이터 생성을 시작합니다...")

    # 1. 명언(Quotes) 데이터가 없으면 기본 데이터 추가
    if db.quotes.count_documents({}) == 0:
        sample_quotes = [
            {"text": "몰입의 즐거움을 느껴보세요!"},
            {"text": "오늘 흘린 땀은 내일의 실력이 됩니다."},
            {"text": "정글에서 살아남는 자가 강한 자입니다."},
            {"text": "꾸준함은 모든 것을 이깁니다."},
            {"text": "지금 자면 꿈을 꾸지만, 지금 깨어있으면 꿈을 이룹니다."}
        ]
        db.quotes.insert_many(sample_quotes)
        print("✅ 기본 명언 데이터 세팅 완료")

    # 2. 30명의 현실적인 이름과 아이디 리스트
    korean_names = [
        "김민수", "이지은", "박지훈", "최수진", "정민호", 
        "강지영", "조현우", "윤서연", "장도윤", "임하은", 
        "한건우", "오지유", "서준서", "신지아", "권우진", 
        "황서윤", "안시우", "송채원", "전은우", "홍수아", 
        "유도현", "고다은", "문지호", "양하윤", "손서진", 
        "배지우", "조유준", "백수아", "허건", "남지윤"
    ]
    
    english_ids = [
        "minsoo", "jieun", "jihoon", "sujin", "minho", 
        "jiyoung", "hyunwoo", "seoyeon", "doyun", "haeun", 
        "gunwoo", "jiyoo", "junseo", "jia", "woojin", 
        "seoyoon", "siwoo", "chaewon", "eunwoo", "sooa", 
        "dohyun", "daeun", "jiho", "hayoon", "seojin", 
        "jiwoo", "yujun", "suah", "geon", "jiyoon"
    ]
    
    dummy_users = []
    user_ids = []
    
    # 비밀번호는 테스트 편의를 위해 '1234'로 통일
    hashed_pw = generate_password_hash("1234")

    # 리스트를 순회하며 데이터 만들기
    for std_id, nickname in zip(english_ids, korean_names):
        user_ids.append(std_id)
        
        # 누적 시간 랜덤 생성 (0초 ~ 약 100시간 사이)
        random_total_time = random.randint(0, 360000)
        
        user = {
            "std_id": std_id,
            "nickname": nickname,
            "password": hashed_pw,
            "start_time": None,
            "total_time": random_total_time,
            "todaytimes": [],
            "friends": [],
            "ban_id": [],
            "combo": random.randint(0, 15) # 랜덤 연속 출석 일수
        }
        dummy_users.append(user)

    # DB에 유저 인서트 (이미 존재하면 건너뜀)
    inserted_count = 0
    for user in dummy_users:
        try:
            db.user.insert_one(user)
            inserted_count += 1
        except DuplicateKeyError:
            pass # 이미 있는 아이디는 무시

    print(f"✅ {inserted_count}명의 새로운 유저 생성 완료 (비밀번호는 모두 '1234'입니다)")

    # 3. 랜덤하게 친구 추가 및 방명록(댓글) 작성
    print("🔄 친구 관계 및 방명록 생성 중...")
    
    if db.reply.find_one({'admin': 1}) is None:
        db.reply.insert_one({'admin': 1, 'counter': 0})

    for std_id in user_ids:
        # 본인을 제외한 랜덤한 2~5명을 친구로 추가
        potential_friends = [uid for uid in user_ids if uid != std_id]
        friends_list = random.sample(potential_friends, random.randint(2, 5))
        
        db.user.update_one(
            {"std_id": std_id},
            {"$set": {"friends": friends_list}}
        )

        # 각 유저의 프로필(방명록)에 1~3개의 랜덤 댓글 작성
        reply_count = random.randint(1, 3)
        replys_data = []
        
        for _ in range(reply_count):
            writer = random.choice(user_ids) # 방명록 작성자 (아이디 형태)
            
            count_doc = db.reply.find_one_and_update(
                {'admin': 1},
                {'$inc': {'counter': 1}},
                return_document=True
            )
            current_reply_id = count_doc['counter']
            
            # 방명록 내용도 조금 더 사람처럼
            greetings = [
                "오늘도 화이팅입니다!! 🔥", 
                "리더보드 순위 엄청 높으시네요 👍", 
                "같이 빡공해요~", 
                "어제 늦게까지 하시던데 체력 관리 잘하세요!",
                "친구 추가 꾹 누르고 갑니다 ㅎㅎ"
            ]
            
            replys_data.append({
                'id': writer,
                'reply': random.choice(greetings),
                'reply_id': current_reply_id
            })
            
        if db.reply.find_one({'std_id': std_id, 'admin': 0}) is None:
            db.reply.insert_one({
                'admin': 0,
                'std_id': std_id,
                'replys': replys_data
            })
        else:
            db.reply.update_one(
                {'std_id': std_id, 'admin': 0},
                {'$push': {'replys': {'$each': replys_data}}}
            )

    print("✅ 친구 맺기 및 생동감 있는 댓글 데이터 세팅 완료")
    print("🎉 완벽합니다! 이제 서버를 켜고 확인해 보세요.")

if __name__ == "__main__":
    generate_dummy_data()