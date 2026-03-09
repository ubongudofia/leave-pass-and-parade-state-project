# migrate_balances.py
from pymongo import MongoClient
from datetime import datetime

def migrate_existing_balances():
    """Migrate existing leave_balances to new schema with all TACOS fields."""
    
    client = MongoClient("mongodb://localhost:27017/")
    db = client["dsa_pass_leave"]
    
    print("Migrating existing leave balances to new TACOS schema...")
    
    # Get all existing balances
    balances = db.leave_balances.find({})
    migrated_count = 0
    
    for balance in balances:
        update_data = {}
        
        # 1. Add missing fields with TACOS defaults
        fields_to_add = {
            # Compassionate
            "compassionateRemaining": max(0, 10 - balance.get('compassionateUsed', 0)),
            
            # Casual - rename field if needed
            "casualCalendarDaysUsed": balance.get('casualCalendarDays', 0),
            "casualCalendarDaysRemaining": max(0, 7 - balance.get('casualCalendarDays', 0)),
            
            # Sick
            "sickThisYearRemaining": max(0, 21 - balance.get('sickThisYear', 0)),
            "sickRollingRemaining": max(0, 42 - balance.get('sickRolling12m', 0)),
            
            # Maternity
            "maternityUsed": False,
            "maternityAvailable": True,
            "maternityStartDate": None,
            
            # Paternity
            "paternityUsed": False,
            "paternityAvailable": True,
            "paternityDaysUsed": 0,
            
            # Disembarkation
            "disembarkationAvailable": True,
            "disembarkationDaysUsed": 0,
            
            # Terminal
            "terminalAvailable": not balance.get('terminalGranted', False),
            
            # Hospitalization
            "hospitalizationDaysUsed": 0,
            "firstHospitalizationUsed": False,
            
            # International
            "hasInternationalPermission": False,
            
            # Annual entitlement if missing
            "annualEntitlement": balance.get('annualEntitlement', 
                30 if (7 <= balance.get('grade', 0) <= 15) else 21)
        }
        
        # Only add fields that don't exist
        for field, value in fields_to_add.items():
            if field not in balance:
                update_data[field] = value
        
        # Also ensure annualRemaining doesn't exceed entitlement
        annual_remaining = balance.get('annualRemaining', 0)
        annual_entitlement = update_data.get('annualEntitlement') or balance.get('annualEntitlement', 30)
        if annual_remaining > annual_entitlement:
            update_data['annualRemaining'] = annual_entitlement
        
        if update_data:
            update_data['updatedAt'] = datetime.utcnow()
            
            db.leave_balances.update_one(
                {"_id": balance['_id']},
                {"$set": update_data}
            )
            migrated_count += 1
            print(f"  Migrated balance for {balance.get('serviceNumber', 'Unknown')}")
    
    print(f"\n✓ Migrated {migrated_count} balance records")
    
    # Verify
    total = db.leave_balances.count_documents({})
    print(f"Total balances: {total}")
    
    client.close()

if __name__ == "__main__":
    migrate_existing_balances()