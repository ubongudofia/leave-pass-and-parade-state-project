from pymongo import MongoClient
from werkzeug.security import generate_password_hash
import sys
from datetime import datetime

# ────────────────────────────────────────────────
# CONFIG - change these
# ────────────────────────────────────────────────
MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "dsa_pass_leave"        

# List of users to update (you can add many at once)
users_to_update = [
    # {
    #     "service_number": "NN/0987",      # Chief clerk DCS
    #     "plain_password": "@sso_pw"     
    # },
    # {
    #     "service_number": "NA/2368",      # Chief clerk Dnpt
    #     "plain_password": "chief_dnpt"     
    # }NAF/6573
    {
        "service_number": "NAF/6573",      # DOA-RSM
        "plain_password": "rsm_pw"     
    },
    # {
    #     "service_number": "DSA/CIV/0213",      # Director DCS
    #     "plain_password": "admin_pw"     
    # },
    # {
    #     "service_number": "DSA/CIV/0022",      # Director DCS
    #     "plain_password": "civilian"     
    # }
    # {
    #     "service_number": "NAF/67890",           # Deputy Director DCS
    #     "plain_password": "@deputy"
    # },
    # {
    #     "service_number": "NN/67890",          # SSO DCS
    #     "plain_password": "@sso_pw"
    # },
    # {
    #     "service_number": "DSA/CIV/0120",          # Civilian Officer
    #     "plain_password": "@civilian"
    # }
    # ,{
    #     "service_number": "NA/9167",          # SO1-DOA
    #     "plain_password": "doa_pw"
    # }
    # Add more here...
]

# ────────────────────────────────────────────────
def update_staff_passwords():
    try:
        client = MongoClient(MONGO_URI)
        db = client[DATABASE_NAME]
        staff_coll = db['staff']

        updated_count = 0

        for user in users_to_update:
            service_num = user["service_number"]
            plain_pw = user["plain_password"]

            if not plain_pw or len(plain_pw) < 5:
                print(f"Skipping {service_num}: password too short or empty")
                continue

            hashed_pw = generate_password_hash(plain_pw, method='pbkdf2:sha256:600000')

            result = staff_coll.update_one(
                {"service_number": service_num},
                {"$set": {
                    "password": hashed_pw,
                    "passwordSetAt": datetime.utcnow()   # optional: track when it was set
                }}
            )

            if result.modified_count == 1:
                print(f"✔ Updated password for {service_num}")
                updated_count += 1
            elif result.matched_count == 1:
                print(f"✗ No change for {service_num} (same password?)")
            else:
                print(f"⚠ User not found: {service_num}")

        print(f"\nFinished. {updated_count} users updated successfully.")

    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    print("=== DSA Staff Password Update Script ===\n")
    update_staff_passwords()