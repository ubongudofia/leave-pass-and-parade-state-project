# update_military_grades.py
from pymongo import MongoClient
# from military_rank_mapping import get_grade_from_rank


MILITARY_RANK_TO_GRADE = {
    # Army/Air Force/Navy ranks to CONDSASS grades
    "Maj Gen": 15, "Major General": 15,
    "Brig Gen": 14, "Brigadier General": 14,
    "Col": 13, "Colonel": 13,
    "Lt Col": 12, "Lieutenant Colonel": 12,
    "Maj": 11, "Major": 11,
    "Capt": 10, "Captain": 10,
    "Lt": 9, "Lieutenant": 9,
    "2Lt": 8, "Second Lieutenant": 8,
    
    # Navy equivalents
    "Rear Admiral": 15,
    "Commodore": 14,
    "Captain": 13,  # Navy Captain (equivalent to Colonel)
    "Commander": 12,
    "Lt Commander": 11,
    "Lieutenant": 10,  # Navy Lieutenant
    "Sub Lieutenant": 9,
    "Acting Sub Lieutenant": 8,
    
    # Air Force equivalents
    "Air Vice Marshal": 15,
    "Air Commodore": 14,
    "Group Captain": 13,
    "Wing Commander": 12,
    "Squadron Leader": 11,
    "Flight Lieutenant": 10,
    "Flying Officer": 9,
    "Pilot Officer": 8,
    
    # Warrant Officers & NCOs (typically lower grades)
    "WO": 7, "Warrant Officer": 7,
    "SSgt": 6, "Staff Sergeant": 6,
    "Sgt": 5, "Sergeant": 5,
    "Cpl": 4, "Corporal": 4,
    "LCpl": 3, "Lance Corporal": 3,
    "Pte": 2, "Private": 2
}

def get_grade_from_rank(rank: str) -> int:
    """Convert military rank to CONDSASS grade."""
    if not rank:
        return 0
    
    rank = rank.strip().title()
    
    # Check exact matches first
    if rank in MILITARY_RANK_TO_GRADE:
        return MILITARY_RANK_TO_GRADE[rank]
    
    # Check partial matches
    for key, grade in MILITARY_RANK_TO_GRADE.items():
        if key.lower() in rank.lower():
            return grade
    
    return 0  # Unknown rank

def update_military_grades():
    client = MongoClient("mongodb://localhost:27017/")
    db = client["dsa_pass_leave"]
    
    # Get all staff with military prefixes
    military_staff = db.staff.find({
        "_id": {"$regex": "^(NA/|NN/|NAF/)"}
    })
    
    for staff in military_staff:
        service_number = staff['_id']
        rank = staff.get('rankOrGrade', '')
        
        # Get grade from rank
        grade = get_grade_from_rank(rank)
        
        if grade > 0:
            # Update leave_balance
            db.leave_balances.update_one(
                {
                    "serviceNumber": service_number,
                    "year": 2026
                },
                {
                    "$set": {
                        "grade": grade,
                        "annualEntitlement": 30 if grade >= 7 else 21,
                        "annualRemaining": 30 if grade >= 7 else 21
                    }
                }
            )
            print(f"Updated {service_number}: {rank} -> Grade {grade}")
    
    client.close()

if __name__ == "__main__":
    update_military_grades()