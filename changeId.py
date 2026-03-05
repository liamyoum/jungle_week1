import os
from pymongo import MongoClient

# DB 연결 설정
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "jungle")
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

def migrate_ids_to_digits():
    print("🚀 기존 아이디를 두 자리 숫자(01, 02...)로 변경하는 작업을 시작합니다.")

    # 1. 현재 모든 유저 가져오기
    users = list(db.user.find({}).sort("_id", 1))
    
    if not users:
        print("❌ 유저 데이터가 없습니다. 먼저 더미 데이터를 생성해 주세요.")
        return

    # 2. 기존 아이디 -> 새 아이디(두 자리 숫자) 매핑 딕셔너리 생성
    id_mapping = {}
    for idx, user in enumerate(users):
        old_id = user['std_id']
        # 이미 두 자리 숫자로 되어 있는 데이터가 아니라면 매핑 생성
        if not (old_id.isdigit() and len(old_id) == 2):
            new_id = f"{idx + 1:02d}"  # 1 -> "01", 2 -> "02"
            id_mapping[old_id] = new_id

    if not id_mapping:
        print("✅ 모든 아이디가 이미 두 자리 숫자로 되어 있습니다. 변경할 사항이 없습니다.")
        return

    print(f"총 {len(id_mapping)}명의 아이디를 변경합니다.")

    # 3. 데이터베이스 업데이트 진행
    for old_id, new_id in id_mapping.items():
        # A. user 컬렉션의 본인 std_id 변경
        db.user.update_one({"std_id": old_id}, {"$set": {"std_id": new_id}})
        
        # B. reply 컬렉션의 방명록 주인 std_id 변경
        db.reply.update_one({"std_id": old_id}, {"$set": {"std_id": new_id}})

    # 4. 관계 데이터(친구, 차단, 방명록 작성자) 갱신
    # 아이디가 전부 새 번호로 바뀐 뒤에 리스트 내부를 갱신해야 안전합니다.
    print("🔄 친구 목록 및 방명록 작성자 정보를 새 아이디로 업데이트 중...")
    
    all_updated_users = list(db.user.find({}))
    for user in all_updated_users:
        current_id = user['std_id']
        
        # 친구 목록 업데이트
        new_friends = [id_mapping.get(f, f) for f in user.get('friends', [])]
        # 밴 목록 업데이트
        new_bans = [id_mapping.get(b, b) for b in user.get('ban_id', [])]
        
        db.user.update_one(
            {"std_id": current_id}, 
            {"$set": {"friends": new_friends, "ban_id": new_bans}}
        )

    # 방명록 내부 댓글(replys 배열)의 작성자(id) 업데이트
    all_replies = db.reply.find({"admin": 0})
    for reply_doc in all_replies:
        updated_replys_list = []
        for reply_obj in reply_doc.get('replys', []):
            writer_id = reply_obj.get('id')
            # 작성자 아이디가 변경 대상이면 숫자로 교체
            if writer_id in id_mapping:
                reply_obj['id'] = id_mapping[writer_id]
            updated_replys_list.append(reply_obj)
            
        db.reply.update_one(
            {"_id": reply_doc["_id"]}, 
            {"$set": {"replys": updated_replys_list}}
        )

    # 5. 기존 세션 데이터 날리기 (아이디가 바뀌었으므로 기존 로그인 유저들은 로그아웃 처리)
    db.sessions.delete_many({})
    
    print("🎉 모든 아이디가 01, 02 등의 숫자로 완벽하게 업데이트되었습니다!")
    print("기존 접속자들의 세션이 초기화되었으니, 숫자로 된 아이디로 다시 로그인해 주세요.")

if __name__ == "__main__":
    migrate_ids_to_digits()