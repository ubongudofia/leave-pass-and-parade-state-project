from flask import Flask, Blueprint, request, render_template, jsonify, redirect, flash, url_for, current_app, session
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename, send_file
from gridfs import GridFS
import os
from .leave_logic import validate_leave_request, LeaveBalances, working_days_between, get_legacy_fields
from .leave_helper import update_leave_balance, deduct_casual_with_annual, get_public_holidays, get_staff_object, get_current_balances, get_hospitalization_records, calendar_days_between
import holidays
import random
from pymongo import MongoClient
from app.extensions import socketio


application_routes = Blueprint('application_routes', __name__)


def generate_reference_id(directorate):
    """
    Generate unique reference ID: DSA-{DIRECTORATE}-{YEAR}-{6_RANDOM_DIGITS}
    Example: DSA-DCS-2026-123456
    """
    # Get current year
    year = datetime.now().year
    
    # Generate 6 random digits (not alphanumeric, just numbers)
    random_digits = ''.join(str(random.randint(0, 9)) for _ in range(6))
    
    # Format: DSA-{DIRECTORATE}-{YEAR}-{6_DIGITS}
    return f"DSA-{directorate}-{year}-{random_digits}"


def get_db_collections():
    """Get database collections directly instead of relying on current_app attributes."""
    client = MongoClient("mongodb://localhost:27017/")
    db = client["dsa_pass_leave"]
    
    return {
        'staff': db.staff,
        'leave_balances': db.leave_balances,
        'applications': db.applications,
        'fs': GridFS(db),
        'medical_records': db.medical_records if 'medical_records' in db.list_collection_names() else None
    }


def convert_doc_to_LeaveBalances(doc: dict, service_number: str, year: int):
    """Convert MongoDB document to LeaveBalances object."""
    from .leave_logic import LeaveBalances
    
    return LeaveBalances(
        annual_entitlement=doc.get('annualEntitlement', 0),
        annual_remaining=doc.get('annualRemaining', 0),
        compassionate_used=doc.get('compassionateUsed', 0),
        compassionate_remaining=doc.get('compassionateRemaining', 10),
        casual_calendar_days_used=doc.get('casualCalendarDaysUsed', 0),
        casual_calendar_days_remaining=doc.get('casualCalendarDaysRemaining', 7),
        sick_this_year=doc.get('sickThisYear', 0),
        sick_rolling_12m=doc.get('sickRolling12m', 0),
        sick_this_year_remaining=doc.get('sickThisYearRemaining', 21),
        sick_rolling_remaining=doc.get('sickRollingRemaining', 42),
        maternity_available=doc.get('maternityAvailable', True),
        paternity_available=doc.get('paternityAvailable', True),
        disembarkation_available=doc.get('disembarkationAvailable', True),
        terminal_granted=doc.get('terminalGranted', False),
        terminal_available=doc.get('terminalAvailable', True),
        has_international_permission=doc.get('hasInternationalPermission', False),
        year=year,
        service_number=service_number,
        full_name=doc.get('fullName', ''),
        directorate=doc.get('directorate', ''),
        grade=doc.get('grade', 0)
    )




def notify_pending_approval(app, first_pending, current_user):
    """
    Emits a Socket.IO notification to the next approver for real-time modal.
    """
    approver_id = first_pending.get("approverId")
    if not approver_id:
        return

    # Find staff member
    approver_user = current_app.staff_collection.find_one({"service_number": approver_id})
    if not approver_user:
        return

    # Notification message
    message = f"Application {app['referenceId']} is awaiting your approval."

    # Build payload
    payload = {
        "applicationId": str(app["_id"]),
        "referenceId": app["referenceId"],
        "message": message,
        "triggeredBy": current_user.get("fullName"),
        "role": first_pending.get("role"),
        "directorate": approver_user.get("directorate")
    }

    # Make service_number safe for room naming
    safe_approver_id = approver_id.replace("/", "_")
    room = f"USER_{safe_approver_id}"
    socketio.emit("new_notification", payload, room=room)





@application_routes.route('/application_form', methods=['GET', 'POST'])
def application_form():
    applicant = session.get('applicant')

    if not applicant:
        flash("Session expired. Please verify your service number again.", "error")
        return redirect(url_for('verify_service_number_routes.apply_id'))
    
    # Initialize chain early to prevent UnboundLocalError
    chain = []

    # ========== NEW: FETCH LEAVE DATA FOR DISPLAY ==========
    leave_data = {
        'balances': None,
        'previous_applications': [],
        'entitlements': {}
    }
    
    try:
        # Get current leave balances
        staff_member = current_app.staff_collection.find_one({"service_number": applicant['service_number']})
        if staff_member:
            # Get grade for entitlements
            grade = 0
            rank_or_grade = staff_member.get('rankOrGrade', '')
            if 'Grade Level' in rank_or_grade:
                try:
                    grade = int(rank_or_grade.split('Grade Level')[-1].strip())
                except:
                    grade = 0
            
            # Get current year's balance
            current_year = datetime.now().year
            balance = current_app.leave_balances.find_one({
                "serviceNumber": applicant['service_number'],
                "year": current_year
            })
            
            if balance:
                # Get current balances
                current_balance = convert_doc_to_LeaveBalances(balance, applicant['service_number'], current_year)
                
                # DEFAULT: Show actual database values
                display_annual = balance.get('annualRemaining', 0)
                display_casual = balance.get('casualCalendarDaysRemaining', 7)
                display_casual_used = balance.get('casualCalendarDaysUsed', 0)
                
                # Check if there's a pending deduction from a JUST SUBMITTED application
                # Only apply pending deduction if we're in a POST request (form submitted)
                if request.method == 'POST':
                    pending_deduction = session.get('pending_deduction')
                    if pending_deduction:
                        if pending_deduction.get('annual_deduction', 0) > 0:
                            display_annual = current_balance.annual_remaining - pending_deduction['annual_deduction']
                        
                        if pending_deduction.get('leave_type') == 'casual':
                            display_casual = max(0, 7 - (display_casual_used + pending_deduction.get('calendar_days', 0)))
                
                # Update balance dict for display
                balance['annualRemaining'] = display_annual
                balance['casualCalendarDaysRemaining'] = display_casual
                balance['casualCalendarDaysUsed'] = display_casual_used
                
                # Don't store pending_deduction in balance if it's stale
                if request.method == 'GET':
                    # Clear any stale pending deduction on page load
                    session.pop('pending_deduction', None)
                else:
                    # Only add pending info for POST requests
                    pending_deduction = session.get('pending_deduction')
                    if pending_deduction:
                        balance['pending_deduction'] = pending_deduction
                
                leave_data['balances'] = balance
                leave_data['balance_object'] = current_balance
            
            # Calculate entitlements based on grade
            if 2 <= grade <= 6:
                # Low grade
                leave_data['entitlements'] = {
                    'annual': 21,
                    'casual_calendar': 7,
                    'compassionate': 10,
                    'sick_normal': 21,
                    'sick_rolling': 42,
                    'maternity': 112 if staff_member.get('gender', '').lower() == 'female' else 0,
                    'paternity': 14 if staff_member.get('gender', '').lower() == 'male' else 0,
                    'disembarkation': True,
                    'terminal': 42
                }
            elif 7 <= grade <= 15:
                # High grade
                leave_data['entitlements'] = {
                    'annual': 30,
                    'casual_calendar': 7,
                    'compassionate': 10,
                    'sick_normal': 21,
                    'sick_rolling': 42,
                    'maternity': 112 if staff_member.get('gender', '').lower() == 'female' else 0,
                    'paternity': 14 if staff_member.get('gender', '').lower() == 'male' else 0,
                    'disembarkation': True,
                    'terminal': 90
                }
            else:
                # Default
                leave_data['entitlements'] = {
                    'annual': 21,
                    'casual_calendar': 7,
                    'compassionate': 10,
                    'sick_normal': 21,
                    'sick_rolling': 42,
                    'maternity': 112 if staff_member.get('gender', '').lower() == 'female' else 0,
                    'paternity': 14 if staff_member.get('gender', '').lower() == 'male' else 0,
                    'disembarkation': True,
                    'terminal': 42
                }
            
            # Get previous approved applications (last 6 months)
            six_months_ago = datetime.now() - timedelta(days=180)
            previous_apps = current_app.applications_collection.find({
                "applicantId": applicant['service_number'],
                "status": {"$in": ["approved", "issued"]},
                "createdAt": {"$gte": six_months_ago}
            }).sort("createdAt", -1).limit(5)
            
            leave_data['previous_applications'] = list(previous_apps)
            
    except Exception as e:
        print(f"Error fetching leave data: {e}")
        # Continue with form even if leave data fetch fails


    if request.method == 'POST':
        print(">>> USING APPLICATION_FORM FUNCTION - FILE:", __file__)
        # ─── Read form fields ───────────────────────────────────────────
        leave_type = request.form.get('leave_type', '').strip()
        start_date_str = request.form.get('start_date', '').strip()  # Application date
        end_date_str = request.form.get('end_date', '').strip()
        effective_date_str = request.form.get('effective_date', '').strip()
        number_of_days_str = request.form.get('calculated_days_actual', '').strip()
        reasons = request.form.get('reasons_for_application', '').strip()
        place_intended = request.form.get('place_intended', '').strip()
        contact_address = request.form.get('contact_address', '').strip()
        name_of_reliever = request.form.get('name_of_reliever', '').strip()
        appt_of_reliever = request.form.get('appt_of_reliever', '').strip()
        telephone = request.form.get('telephone', '').strip()
        # calculated_days_actual = request.form.get('calculated_days_actual', '').strip()

        # Conditional fields
        expected_delivery_date_str = request.form.get('expected_delivery_date', '').strip()
        attachment_months = request.form.get('attachment_months', type=int)

        # Initialize with default values
        has_medical_certificate = False
        hospitalized = False
        first_hospitalization = False

        # Only check these fields if sick leave is selected
        if leave_type == 'sick':
            has_medical_certificate = request.form.get('has_medical_certificate') == 'true'
            hospitalized = request.form.get('hospitalized') == 'true'
            first_hospitalization = request.form.get('first_hospitalization') == 'true'

        
        # # International travel checkbox (add to form if needed)
        outside_nigeria = False  # Default - add checkbox to form
        

        # Parse dates
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            effective_date = datetime.strptime(effective_date_str, '%Y-%m-%d')
        except ValueError:
            flash("Invalid date format.", "error")
            return redirect(url_for('application_routes.application_form'))

        # Parse expected delivery date
        expected_delivery_date = None
        if expected_delivery_date_str:
            try:
                expected_delivery_date = datetime.strptime(expected_delivery_date_str, '%Y-%m-%d')
            except ValueError:
                flash("Invalid expected delivery date format.", "error")
                return redirect(url_for('application_routes.application_form'))


        # ─── DATE VALIDATION ──────────────────────────────────────────
        # 1. Basic chronological order
        if not (start_date <= effective_date < end_date):
            flash("Dates must follow: Application Date ≤ Effective Date < End Date", "error")
            return redirect(url_for('application_routes.application_form'))

        # 2. For maternity: effective date should be before EDD
        if leave_type == 'maternity' and expected_delivery_date:
            if effective_date > expected_delivery_date:
                flash("Effective date cannot be after expected delivery date", "error")
                return redirect(url_for('application_routes.application_form'))

        # Get the calculated days from the hidden field
        # calculated_days_ = request.form.get('calculated_days_actual', '').strip()
        try:
            working_days_requested = int(number_of_days_str)
        except ValueError:
            # Fallback to backend calculation if hidden field is missing
            working_days_requested = working_days_between(effective_date, end_date, public_holidays)

        # ─── CALCULATE WORKING DAYS ───────────────────────────────────
        # IMPORTANT: Working days are from EFFECTIVE DATE to END DATE
        year = effective_date.year
        public_holidays = get_public_holidays(year)
        
        working_days_requested = working_days_between(effective_date, end_date, public_holidays)
        
        # Calculate calendar days for casual leave
        calendar_days_requested = calendar_days_between(effective_date, end_date)
        

        # The frontend shows approximate days - we ignore it and use our calculation
        # Just log it for debugging
        if number_of_days_str and number_of_days_str != '—':
            print(f"Frontend showed approx {number_of_days_str} days, backend calculated {working_days_requested} working days, {calendar_days_requested if leave_type=='casual' else 'N/A'} calendar days")

        # ─── BASIC VALIDATION ─────────────────────────────────────────
        required_fields = [
            ('Leave type', leave_type),
            ('Start date', start_date_str),
            ('End date', end_date_str),
            ('Effective date', effective_date_str),
            ('Reason', reasons),
            ('Place intended', place_intended),
            ('Contact address', contact_address)
        ]

        missing = [name for name, val in required_fields if not val]
        if missing:
            flash(f"Please fill in: {', '.join(missing)}", "error")
            return redirect(url_for('application_routes.application_form'))

        
        # Conditional required fields
        if leave_type == 'maternity' and not expected_delivery_date_str:
            flash("Expected delivery date is required for maternity leave", "error")
            return redirect(url_for('application_routes.application_form'))
        
        if leave_type == 'disembarkation' and not attachment_months:
            flash("Duration of course/attachment is required for disembarkation leave", "error")
            return redirect(url_for('application_routes.application_form'))
        
        if leave_type == 'sick' and not has_medical_certificate:
            flash("Medical certificate is required for sick leave", "error")
            return redirect(url_for('application_routes.application_form'))
        
        


        # ─── Handle multiple file uploads ──────────────────────────────
        attachments = []

        if 'attachments' in request.files:
            files = request.files.getlist('attachments')
            fs = current_app.fs   # your GridFS instance

            for file in files:
                if file and file.filename:
                    # Read once to check size
                    file_content = file.read()
                    if len(file_content) > 20 * 1024 * 1024:
                        flash(f"File '{file.filename}' is too large (max 20MB)", "error")
                        return redirect(url_for('application_routes.application_form'))

                    file.seek(0)  # reset for GridFS

                    try:
                        file_id = fs.put(
                            file,
                            filename=secure_filename(file.filename),
                            content_type=file.content_type or 'application/octet-stream',
                            metadata={
                                "uploaded_by": applicant['service_number'],
                                "application_type": leave_type,
                                "upload_date": datetime.utcnow()
                            }
                        )
                        attachments.append({
                            "gridfs_id": str(file_id),   # store as string or ObjectId
                            "filename": file.filename,
                            "contentType": file.content_type,
                            "size": len(file_content),
                            "uploadedAt": datetime.utcnow()
                        })
                    except Exception as e:
                        flash(f"Failed to upload {file.filename}: {str(e)}", "error")
                        return redirect(url_for('application_routes.application_form'))

        if has_medical_certificate and not attachments:
            flash("Please upload your medical certificate", "error")
            return redirect(url_for('application_routes.application_form'))

        # ─── TACOS VALIDATION ────────────────────────────────────────
        # Prepare request data for validation
        request_data = {
            'type': leave_type,
            'working_days_requested': working_days_requested,
            'start_date': start_date,           # Application date
            'end_date': end_date,               # Leave end date
            'effective_date': effective_date,   # Leave start date
            'has_medical_certificate': has_medical_certificate,
            'hospitalized': hospitalized,
            'first_hospitalization': first_hospitalization,
            'outside_nigeria': outside_nigeria,
            'expected_delivery_date': expected_delivery_date,
            'attachment_months': attachment_months if attachment_months else 0,
            'calendar_days': calendar_days_requested
        }

        # Get database collections
        collections = get_db_collections()

        # Get staff and balances - FIXED: Pass collections to helper functions
        try:
            # Temporarily set current_app attributes for helper functions
            current_app.staff_collection = collections['staff']
            current_app.leave_balances = collections['leave_balances']
            current_app.medical_records = collections['medical_records']
            
            staff = get_staff_object(applicant['service_number'])
            balances = get_current_balances(applicant['service_number'])
            hospitalization_records = get_hospitalization_records(applicant['service_number'])
        except Exception as e:
            flash(f"Error fetching staff data: {str(e)}", "error")
            return redirect(url_for('application_routes.application_form'))
        
        # ============= 🔥 CHECK BALANCE SUFFICIENCY AT SUBMISSION =============
        balance_sufficient = True
        insufficient_message = ""

        # Pre-calculate for casual leave
        excess_working_days = 0
        if leave_type == "casual" and calendar_days_requested > balances.casual_calendar_days_remaining:
            free_days = balances.casual_calendar_days_remaining
            if free_days > 0:
                free_end_date = effective_date + timedelta(days=free_days - 1)
                excess_start_date = free_end_date + timedelta(days=1)
                excess_working_days = working_days_between(excess_start_date, end_date, public_holidays)
            else:
                excess_working_days = working_days_requested

        # Check based on leave type
        if leave_type == "annual":
            if balances.annual_remaining < working_days_requested:
                balance_sufficient = False
                insufficient_message = f"Insufficient annual leave balance. You have {balances.annual_remaining} days remaining but requested {working_days_requested} days."

        elif leave_type == "casual":
            if calendar_days_requested > balances.casual_calendar_days_remaining:
                if balances.annual_remaining < excess_working_days:
                    balance_sufficient = False
                    insufficient_message = f"Insufficient annual leave for excess casual days. Need {excess_working_days} days from annual leave, but you only have {balances.annual_remaining} days remaining. Please reduce your leave days."

        elif leave_type == "compassionate":
            if balances.compassionate_remaining < working_days_requested:
                balance_sufficient = False
                insufficient_message = f"Insufficient compassionate leave balance. You have {balances.compassionate_remaining} days remaining but requested {working_days_requested} days."

        elif leave_type == "disembarkation":
            required_days = 14 if attachment_months and attachment_months > 6 else 7
            if balances.annual_remaining < required_days:
                balance_sufficient = False
                insufficient_message = f"Insufficient annual leave for disembarkation. Need {required_days} days from annual leave, but you only have {balances.annual_remaining} days remaining."

        # 🔥 BLOCK SUBMISSION IF INSUFFICIENT
        if not balance_sufficient:
            flash(f"❌ {insufficient_message} Please adjust your leave dates or select a different leave type.", "error")
            return redirect(url_for('application_routes.application_form'))

        # Validate with TACOS logic
        is_valid, message, metadata = validate_leave_request(
            request_data=request_data,
            staff=staff,
            current_year_balances=balances,
            public_holidays=public_holidays,
            hospitalization_records=hospitalization_records
        )
        
        if not is_valid:
            flash(f"Leave validation failed: {message}", "error")
            # Show metadata notes if any
            if metadata and metadata.get('notes'):
                for note in metadata['notes']:
                    if isinstance(note, str) and note.startswith("Warning:"):
                        flash(note, "warning")
            return redirect(url_for('application_routes.application_form'))
        
        # ============ NEW: PREVIEW BALANCE DEDUCTION ============
        # Calculate what will be deducted
        annual_deduction = metadata.get('deduct_from_annual', 0) if metadata else 0
        
        # For casual leave, calculate free days vs excess
        free_casual_days = 0
        excess_casual_days = 0
        excess_working_days = 0
        
        if leave_type == 'casual':
            casual_remaining = balances.casual_calendar_days_remaining
            
            if calendar_days_requested <= casual_remaining:
                free_casual_days = calendar_days_requested
                excess_casual_days = 0
                excess_working_days = 0
            else:
                free_casual_days = casual_remaining
                excess_casual_days = calendar_days_requested - casual_remaining
                
                # Calculate working days for excess period
                if free_casual_days > 0:
                    free_end_date = effective_date + timedelta(days=free_casual_days - 1)
                    excess_start_date = free_end_date + timedelta(days=1)
                    excess_working_days = working_days_between(excess_start_date, end_date, public_holidays)
                else:
                    excess_working_days = working_days_requested
            
            annual_deduction = excess_working_days
        
        # Store deduction info in session for display on success page
        session['pending_deduction'] = {
            'leave_type': leave_type,
            'calendar_days': calendar_days_requested if leave_type == 'casual' else 0,
            'working_days': working_days_requested if leave_type != 'casual' else 0,
            'free_casual_days': free_casual_days,
            'excess_casual_days': excess_casual_days,
            'excess_working_days': excess_working_days,
            'annual_deduction': annual_deduction,
            'annual_remaining_before': balances.annual_remaining,
            'annual_remaining_after': balances.annual_remaining - annual_deduction,
            'casual_remaining_before': balances.casual_calendar_days_remaining,
            'casual_remaining_after': max(0, 7 - (balances.casual_calendar_days_used + calendar_days_requested)) if leave_type == 'casual' else balances.casual_calendar_days_remaining
        }
        
        # Show user what will be deducted
        if annual_deduction > 0:
            flash(f"ℹ️ This leave will deduct {annual_deduction} working days from your Annual Leave balance", "info")
        if free_casual_days > 0:
            flash(f"✅ {free_casual_days} calendar days will be covered by your Casual Leave allowance", "success")




        # ─── Build approval chain (your existing code is good) ────────
        staff_coll = current_app.staff_collection
        chain = []

        # Helper to create a chain step with pre-filled approver info
        def create_step(role, approver):
            if not approver:
                return None
            return {
                "role": role,
                "approverId": approver.get('service_number'),
                "approverName": approver.get('fullName'),
                "approverRank": approver.get('rankOrGrade'),
                "approverDesignation": approver.get('designation'),
                "status": "pending",
                "comments": "",
                "timestamp": None
            }

        # 1. Civilian path: starts with Civilian Officer
        if applicant['type'] == 'civilian':
            civ_officer = staff_coll.find_one({
                "directorate": applicant['directorate'],
                "roles": "Civilian Officer"
            })
            step = create_step("Civilian Officer", civ_officer)
            if step:
                chain.append(step)
            else:
                flash("Warning: No Civilian Officer found in this directorate", "warning")

        # Both civilian and military go through these levels
        # 2. Common chain: SSO → Deputy Director → Director
        common_roles = ["SSO", "Deputy_Director", "Director"]

        for role in common_roles:
            approver = staff_coll.find_one({
                "directorate": applicant['directorate'],
                "roles": role
            })
            step = create_step(role, approver)
            if step:
                chain.append(step)
            else:
                flash(f"Warning: No {role} found in {applicant['directorate']}", "warning")
                
        
        # 3. Chief Clerk step — always after Director (not an approval step)
        chief_clerk = staff_coll.find_one({
            "directorate": applicant['directorate'],
            "roles": "Chief Clerk"
        })

        if chief_clerk:
            chief_clerk_step = create_step("Chief Clerk", chief_clerk)
            if chief_clerk_step:
                chief_clerk_step["status"] = "pending"              
                chief_clerk_step["forward_status"] = "not_forwarded" 
                chief_clerk_step["forwardedAt"] = None
                chain.append(chief_clerk_step)
            else:
                flash("Warning: Chief Clerk data incomplete", "warning")
        else:
            flash("Warning: No Chief Clerk found in this directorate", "warning")
                
        # 4. SO1-DOA for final approval
        so1_doa = staff_coll.find_one({"roles": "SO1-DOA"})
        if not so1_doa:
            flash("System error: SO1-DOA not found.", "error")
            return redirect(url_for('application_routes.application_form'))

        
        # Get SO1-DOA's service number
        so1_doa_id = so1_doa.get('service_number')

        
        # ─── Save application ──────────────────────────────────────────
        applications_coll = current_app.applications_collection
        directorate = applicant['directorate']
        
        # Generate reference ID
        reference_id = generate_reference_id(directorate)
        while applications_coll.find_one({"referenceId": reference_id}):
            reference_id = generate_reference_id(directorate)

        print("DEBUG: Generated reference_id =", reference_id)

        application = {
            # === Required root-level fields ===
            "referenceId": reference_id,
            "applicantName": applicant['fullName'],
            "applicantId": applicant['service_number'],
            "leave_type": leave_type,
            "directorate": directorate,
            "status": "pending",
            "approvalChain": chain,
            "finalApproval": {
                "approverId": so1_doa.get('service_number'),
                "status": "pending",
                "comments": "",
                "timestamp": None,
                "receipt": {
                    "receiptNumber": None,
                    "issuedDate": None,
                    "pdfUrl": None
                }
            },
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
            "dates": {
                "applicationDate": start_date,
                "effectiveDate": effective_date,
                "endDate": end_date
            },
            "startDate": start_date,
            "endDate": end_date,
            "effectiveDate": effective_date,
            "numberOfDays": calendar_days_requested if leave_type == 'casual' else working_days_requested,
            "reason": reasons,
            "placeIntended": place_intended,
            "contactAddress": contact_address,
            "telephone": telephone,
            "name_of_reliever": name_of_reliever,
            "appt_of_reliever": appt_of_reliever,
            "attachments": attachments,
            "tacosDetails": {
                "hasMedicalCertificate": has_medical_certificate,
                "hospitalized": hospitalized,
                "firstHospitalization": first_hospitalization,
                "outsideNigeria": outside_nigeria,
                "expectedDeliveryDate": expected_delivery_date,
                "attachmentMonths": attachment_months,
                "calendarDays": calendar_days_requested
            },
            # === Validation result ===
            "validation": {
                "isValid": is_valid,
                "validationMessage": message,
                "metadata": metadata or {},
                "validatedAt": datetime.utcnow()
            },
            # === Other expected root fields ===
            "leaveBalances": {
                "annualRemaining": balances.annual_remaining,
                "compassionateUsed": balances.compassionate_used,
                "casualCalendarDays": balances.casual_calendar_days_used,
                "sickThisYear": balances.sick_this_year,
                "sickRolling12m": balances.sick_rolling_12m,
                "terminalGranted": balances.terminal_granted
            },
            "tacosCompliance": None,
            "notifications": [],
            "auditTrail": []
            
        }


        try:
            result = applications_coll.insert_one(application)

            # 🔥 GET FIRST PENDING APPROVER
            first_pending = next(
                (s for s in chain if s['status'] == 'pending'),
                None
            )

            if first_pending:
                notify_pending_approval(application, first_pending, applicant)
           
            flash(f"Application submitted successfully! Reference ID: {reference_id}", "success")
            
            session['last_application_id'] = str(result.inserted_id)
            session['last_reference_id'] = reference_id
            
            return redirect(url_for('application_success_routes.application_success', 
                                  ref_id=reference_id))

        except Exception as e:
            # Cleanup uploaded files
            for att in attachments:
                try:
                    current_app.fs.delete(ObjectId(att["gridfs_id"]))
                except:
                    pass
            flash(f"Error saving application: {str(e)}", "error")
            return redirect(url_for('application_routes.application_form'))


    return render_template('application_form.html', applicant=applicant, leave_data=leave_data)





@application_routes.route('/calculate_working_days', methods=['POST'])
def calculate_working_days():
    """API endpoint to calculate working days between two dates."""
    data = request.get_json()
    
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    leave_type = data.get('leave_type', 'annual')
    
    if not start_date_str or not end_date_str:
        return jsonify({'error': 'Start and end dates required'}), 400
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    
    if start_date > end_date:
        return jsonify({'error': 'Start date must be before end date'}), 400
    
    # Get public holidays for the year
    year = start_date.year
    public_holidays = get_public_holidays(year)
    
    # Calculate based on leave type
    if leave_type == 'casual':
        # Casual leave uses calendar days
        days = calendar_days_between(start_date, end_date)
        return jsonify({
            'days': days,
            'type': 'calendar',
            'message': f'{days} calendar days (includes weekends)'
        })
    else:
        # Other leaves use working days
        days = working_days_between(start_date, end_date, public_holidays)
        
        # Get holiday names for display
        holiday_names = []
        for holiday_date in public_holidays:
            if start_date <= holiday_date <= end_date:
                # Get holiday name from holidays library
                nigeria_holidays = holidays.country_holidays('NG', years=year)
                name = nigeria_holidays.get(holiday_date.date(), 'Public Holiday')
                holiday_names.append({
                    'date': holiday_date.strftime('%Y-%m-%d'),
                    'name': name
                })
        
        return jsonify({
            'days': days,
            'type': 'working',
            'holidays_excluded': holiday_names,
            'message': f'{days} working days (excludes weekends and {len(holiday_names)} public holidays)'
        })
