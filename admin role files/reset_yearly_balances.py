from pymongo import MongoClient
import sys
from datetime import datetime, timedelta
from flask import current_app



def reset_yearly_balances(year: int = None):
    """
    Reset annual balances for new year.
    Should be run on Jan 1st or when initializing staff.
    """
    if year is None:
        year = datetime.now().year
    
    # Get all active staff
    staff_collection = current_app.staff_collection
    all_staff = staff_collection.find({})
    
    for staff in all_staff:
        service_number = (
            staff.get('serviceNumber') or
            staff.get('service_number')
        )
        
        if not service_number:
            service_number = str(staff.get('_id'))
        
        if not service_number:
            continue
        
        # Get grade
        grade = 0
        rank_or_grade = staff.get('rankOrGrade', '')
        if 'Grade Level' in rank_or_grade:
            try:
                grade_str = rank_or_grade.split('Grade Level')[-1].strip()
                grade = int(grade_str)
            except:
                grade = 0
        
        # Determine annual entitlement
        annual_entitlement = 21 if 2 <= grade <= 6 else 30
        
        # Create new year balance
        new_balance = {
            "serviceNumber": service_number,
            "fullName": staff.get('fullName', ''),
            "directorate": staff.get('directorate', ''),
            "grade": grade,
            "year": year,
            "isActive": True,
            
            # Annual
            "annualEntitlement": annual_entitlement,
            "annualRemaining": annual_entitlement,
            
            # Compassionate (resets yearly)
            "compassionateUsed": 0,
            "compassionateRemaining": 10,
            
            # Casual (resets yearly)
            "casualCalendarDaysUsed": 0,
            "casualCalendarDaysRemaining": 7,
            
            # Sick (rolling 12m persists, yearly resets)
            "sickThisYear": 0,
            "sickThisYearRemaining": 21,
            # Keep sickRolling12m from previous year? This is rolling 12 months
            # We'll need to handle this carefully
            
            # Maternity/Paternity (these are per event, not yearly)
            "maternityAvailable": True,
            "paternityAvailable": True,
            "disembarkationAvailable": True,
            "terminalAvailable": True,
            
            # International permission status
            "hasInternationalPermission": staff.get('hasInternationalPermission', False),
            
            # Audit
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
            "notes": [f"Balance initialized for year {year}"]
        }
        
        # Check if balance already exists for this year
        existing = current_app.leave_balances.find_one({
            "serviceNumber": service_number,
            "year": year
        })
        
        if existing:
            # Update existing
            new_balance["updatedAt"] = datetime.utcnow()
            current_app.leave_balances.update_one(
                {"_id": existing["_id"]},
                {"$set": new_balance}
            )
        else:
            # Insert new
            current_app.leave_balances.insert_one(new_balance)
    
    print(f"✓ Yearly balances reset for {year}")
    return True