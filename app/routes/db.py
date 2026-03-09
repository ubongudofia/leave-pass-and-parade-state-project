# # 1. leave_balances collection
# {
#     "_id": ObjectId,
#     "serviceNumber": "string",
#     "year": 2025,
#     "annualRemaining": 15,
#     "compassionateUsed": 3,
#     "casualCalendarDays": 5,
#     "sickThisYear": 10,
#     "sickRolling12m": 25,
#     "terminalGranted": false,
#     "updatedAt": ISODate
# }

# # 2. medical_records collection (for hospitalization tracking)
# {
#     "_id": ObjectId,
#     "serviceNumber": "string",
#     "recordType": "hospitalization" | "sick_certificate",
#     "admissionDate": ISODate,
#     "dischargeDate": ISODate,
#     "medicalOfficer": "string",
#     "hospitalName": "string",
#     "certificateFileId": ObjectId,  # GridFS reference
#     "createdAt": ISODate
# }

# # 3. public_holidays collection
# {
#     "_id": ObjectId,
#     "date": ISODate,
#     "name": "string",
#     "year": 2025,
#     "isRecurring": boolean
# }

# # 4. Update applications collection schema to include TACOS fields
# # (as shown in the code above)
