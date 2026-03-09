from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from datetime import datetime
from bson.objectid import ObjectId
from flask_login import current_user
from functools import wraps
from app.extensions import socketio
from flask_socketio import emit, join_room



parade_state = Blueprint('parade_state', __name__)



def create_parade_notification(parade_doc, current_user, target_role, target_directorate=None):
    """
    Create a notification record in the database for parade state approvals
    """
    notifications_coll = current_app.notifications_collection
    
    # Determine target based on role
    target = {
        "type": "role",
        "role": target_role
    }
    
    if target_directorate:
        target["directorate"] = target_directorate
    
    # Make sure we have all the meta data
    meta = {
        "triggeredBy": current_user["service_number"],
        "triggeredByName": current_user.get("fullName", "Unknown"),
        "date": parade_doc.get('date'),
        "batch": parade_doc.get('batch'),
        "directorate": parade_doc.get('directorate'),
        "parade_id": str(parade_doc["_id"])  # Store the parade ID in meta
    }
    
    # Create notification document
    notification = {
        "type": "parade_approval_required",
        "applicationId": parade_doc["_id"],  # Store the parade ID
        "referenceId": f"PARADE-{parade_doc['date']}-{parade_doc['batch']}",
        "target": target,
        "message": f"Parade State for {parade_doc['date']} (Batch {parade_doc['batch']}) is awaiting your approval.",
        "status": "unread",
        "readBy": [],
        "meta": meta,  # Store all important data in meta
        "createdAt": datetime.utcnow(),
        "isActive": True,
        "updatedAt": datetime.utcnow()
    }
    
    try:
        result = notifications_coll.insert_one(notification)
        print(f"Notification created with ID: {result.inserted_id}")
        return result.inserted_id
    except Exception as e:
        print(f"Error creating notification: {e}")
        return None


def notify_parade_submitted(parade_doc, current_user):
    """
    Send notification to Civilian Officer when parade state is submitted by Admin Officer
    """
    try:
        directorate = parade_doc.get('directorate')
        target_role = "Civilian Officer"
        
        # Create database notification
        notification_id = create_parade_notification(parade_doc, current_user, target_role, directorate)
        
        if not notification_id:
            print("Failed to create notification")
            return
        
        # Prepare payload for socket emission with ALL data at root level
        payload = {
            "_id": str(parade_doc["_id"]),
            "notification_id": str(notification_id),
            "message": f"New Parade State for {parade_doc['date']} (Batch {parade_doc['batch']}) has been submitted and awaits your approval.",
            "triggeredBy": current_user.get("fullName"),
            "role": target_role,
            "directorate": directorate,
            "date": parade_doc['date'],
            "batch": parade_doc['batch'],
            "type": "parade",
            "action": "submitted"
        }
        
        # Emit to Civilian Officer room
        room = f"DIR_{directorate}_Civilian Officer"
        socketio.emit("new_notification", payload, room=room)
        
        # Also emit to a more generic room name without spaces
        safe_room = f"DIR_{directorate}_Civilian_Officer"
        if safe_room != room:
            socketio.emit("new_notification", payload, room=safe_room)
        
        print(f"Submission notification sent to {room} for parade {parade_doc['date']}")
        
    except Exception as e:
        print(f"Error sending submission notification: {e}")


def notify_parade_next_approver(app, next_stage, current_user):
    """
    Emits a Socket.IO notification to the next approver for real-time modal.
    Also creates a database notification record.
    """
    try:
        directorate = app.get('directorate')
        
        # Determine target based on next stage
        if next_stage == "civilian_officer":
            return
        elif next_stage == "deputy_director":
            target_role = "Deputy_Director"
            room = f"DIR_{directorate}_Deputy_Director"
            alt_room = f"DIR_{directorate}_Deputy_Director"
            message = f"Parade State for {app['date']} (Batch {app['batch']}) has been approved by Civilian Officer and awaits your approval."
            
        elif next_stage == "documentation":
            # For documentation stage, notify both Chief Clerk and DOA-RSM
            # Chief Clerk
            chief_clerk_msg = f"Parade State for {app['date']} (Batch {app['batch']}) has been approved by Deputy Director and requires documentation."
            
            # Create notification for Chief Clerk
            create_parade_notification(app, current_user, "Chief Clerk", directorate)



            # Emit to Chief Clerk
            socketio.emit("new_notification", {
                "_id": str(app["_id"]),
                "message": chief_clerk_msg,
                "triggeredBy": current_user.get("fullName"),
                "role": "Chief Clerk",
                "directorate": directorate,
                "date": app['date'],
                "batch": app['batch'],
                "type": "parade",
                "action": "documentation"
            }, room=f"DIR_{directorate}_Chief Clerk")
            
            socketio.emit("new_notification", {
                "_id": str(app["_id"]),
                "message": chief_clerk_msg,
                "triggeredBy": current_user.get("fullName"),
                "role": "Chief Clerk",
                "directorate": directorate,
                "date": app['date'],
                "batch": app['batch'],
                "type": "parade",
                "action": "documentation"
            }, room=f"DIR_{directorate}_Chief_Clerk")


            # DOA-RSM
            create_parade_notification(app, current_user, "DOA-RSM", directorate)
            
            socketio.emit("new_notification", {
                "_id": str(app["_id"]),
                "message": chief_clerk_msg,
                "triggeredBy": current_user.get("fullName"),
                "role": "DOA-RSM",
                "directorate": directorate,
                "date": app['date'],
                "batch": app['batch'],
                "type": "parade",
                "action": "documentation"
            }, room=f"DIR_{directorate}_DOA-RSM")
            
            socketio.emit("new_notification", {
                "_id": str(app["_id"]),
                "message": chief_clerk_msg,
                "triggeredBy": current_user.get("fullName"),
                "role": "DOA-RSM",
                "directorate": directorate,
                "date": app['date'],
                "batch": app['batch'],
                "type": "parade",
                "action": "documentation"
            }, room=f"DIR_{directorate}_DOA_RSM")
            
            return  # Early return since we handled both
            
        else:
            return
        
        # Create database notification
        notification_id = create_parade_notification(app, current_user, target_role, directorate)
        
        # Prepare payload for socket emission
        payload = {
            "_id": str(app["_id"]),
            "notification_id": str(notification_id),
            "message": message,
            "triggeredBy": current_user.get("fullName"),
            "role": target_role,
            "directorate": directorate,
            "date": app['date'],
            "batch": app['batch'],
            "type": "parade",
            "action": "approval"
        }
        
        # Emit to the appropriate room
        socketio.emit("new_notification", payload, room=room)
        print(f"Notification sent to {room}: {message}")


        # Also emit to alternative room name
        safe_role = target_role.replace("-", "_").replace(" ", "_")
        alt_room = f"DIR_{directorate}_{safe_role}"
        if alt_room != room:
            socketio.emit("new_notification", payload, room=alt_room)
        
        print(f"Notification sent to {room}: {message}")
        
    except Exception as e:
        print(f"Error sending notification: {e}")


@socketio.on('connect')
def handle_connect():
    print("Socket connected attempt")

    user = session.get("user")

    if not user:
        print("No user in session")
        return

    service_number = user["service_number"]
    directorate = user.get("directorate")
    roles = user.get("roles", [])

    print(f"User: {service_number}, Roles: {roles}, Directorate: {directorate}")
    
    safe_service_number = service_number.replace("/", "_")

    # Join personal room
    join_room(f"USER_{safe_service_number}")
    print(f"Joined: USER_{safe_service_number}")

    # Join role-specific rooms
    for role in roles:
        # For roles like DOA-RSM, Chief Clerk, etc.
        join_room(f"ROLE_{role}")
        print(f"Joined: ROLE_{role}")
        
        # Join directorate-specific role room
        if directorate:
            room_name = f"DIR_{directorate}_{role}"
            join_room(room_name)
            print(f"Joined: {room_name}")
            
            # Also join a more generic version without spaces/special chars
            safe_role = role.replace("-", "_").replace(" ", "_")
            alt_room = f"DIR_{directorate}_{safe_role}"
            if alt_room != room_name:
                join_room(alt_room)
                print(f"Also joined: {alt_room}")




@parade_state.route('/dashboard_parade_state', methods=['GET', 'POST'])
def dashboard_parade_state():
    current_user = session.get('user', {})

    if not current_user:
        flash("Please log in to access the parade state dashboard.", "error")
        return redirect(url_for('auth.login'))

    today_date = datetime.today()
    today = today_date.strftime("%A, %d %b %Y")
    on_batch = get_on_batch(today_date)
    
    directorate = current_user.get("directorate")
    user_roles = current_user.get("roles", [])
    
    parade_coll = current_app.daily_parade_states
    
    # Get ALL filter parameters from request
    filter_directorate = request.args.get('directorate', '')
    filter_date_from = request.args.get('date_from', '')
    filter_date_to = request.args.get('date_to', '')
    filter_status = request.args.get('status', '')  # Add this
    filter_batch = request.args.get('batch', '')    # Add this
    
    # =========================
    # 🔥 FETCH PARADE STATES BASED ON ROLE
    # =========================
    
    # For DOA-RSM - fetch ALL approved parade states from ALL directorates
    if "DOA-RSM" in user_roles:
        # Base query: only approved parade states
        query = {"approval.status": "approved"}
        
        # Apply filters if provided
        if filter_directorate:
            query["directorate"] = filter_directorate
            
        if filter_date_from or filter_date_to:
            date_query = {}
            if filter_date_from:
                date_query["$gte"] = filter_date_from
            if filter_date_to:
                date_query["$lte"] = filter_date_to
            if date_query:
                query["date"] = date_query
        
        # Fetch filtered parade states
        parade_list = list(parade_coll.find(query).sort("date", -1).sort("createdAt", -1))
        
        # Get all unique directorates for filter dropdown
        all_directorates = parade_coll.distinct("directorate", {"approval.status": "approved"})
        
        # Count statistics
        total_count = len(parade_list)
        approved_count = total_count  # All are approved
        pending_count = 0
        rejected_count = 0
        
        # Get statistics by directorate (for dashboard cards)
        directorate_stats = []
        for dir_name in all_directorates:
            dir_count = parade_coll.count_documents({
                "directorate": dir_name,
                "approval.status": "approved"
            })
            if dir_count > 0:
                # Get latest parade for this directorate
                latest = parade_coll.find_one(
                    {"directorate": dir_name, "approval.status": "approved"},
                    sort=[("date", -1)]
                )
                directorate_stats.append({
                    "directorate": dir_name,
                    "count": dir_count,
                    "latest_date": latest.get('date') if latest else None,
                    "latest_batch": latest.get('batch') if latest else None
                })
        
        # Latest overall approved parade
        latest_parade = parade_coll.find_one(
            {"approval.status": "approved"}, 
            sort=[("date", -1), ("createdAt", -1)]
        )
        
    else:
        # For other roles - filter by their directorate
        query = {"directorate": directorate}
        
        #  APPLY FILTERS FOR NON-DOA ROLES
        if filter_status:
            query["approval.status"] = filter_status
            
        if filter_batch:
            query["batch"] = filter_batch
            
        if filter_date_from or filter_date_to:
            date_query = {}
            if filter_date_from:
                date_query["$gte"] = filter_date_from
            if filter_date_to:
                date_query["$lte"] = filter_date_to
            if date_query:
                query["date"] = date_query

        parade_list = list(parade_coll.find(query).sort("createdAt", -1))
        
        # Calculate counts
        total_count = len(parade_list)
        approved_count = sum(1 for p in parade_list if p.get("approval", {}).get("status") == "approved")
        pending_count = sum(1 for p in parade_list if p.get("approval", {}).get("status") == "pending")
        rejected_count = sum(1 for p in parade_list if p.get("approval", {}).get("status") == "rejected")
        
        # Latest parade for their directorate
        today_str = datetime.today().strftime("%Y-%m-%d")
        latest_parade = parade_coll.find_one({
            "directorate": directorate,
            "date": today_str
        })
        
        all_directorates = []
        directorate_stats = []

    return render_template(
        'dashboard_parade_state.html',
        user=current_user,
        today=today,
        on_batch=on_batch,
        parade_list=parade_list,
        latest_parade=latest_parade,
        total_count=total_count,
        approved_count=approved_count,
        pending_count=pending_count,
        rejected_count=rejected_count,
        # Filter data for all roles
        all_directorates=all_directorates,
        directorate_stats=directorate_stats,
        filter_directorate=filter_directorate,
        filter_date_from=filter_date_from,
        filter_date_to=filter_date_to,
        filter_status=filter_status,  
        filter_batch=filter_batch,    
        is_doa_rsm=("DOA-RSM" in user_roles)
    )




def get_on_batch(today=None):
    if not today:
        today = datetime.today()

    weekday = today.weekday()

    # Friday → everyone works
    if weekday == 4:
        return "ALL"

    # Anchor date (Monday where B started)
    anchor_date = datetime(2026, 2, 23)

    delta_days = (today - anchor_date).days
    week_offset = delta_days // 7

    # 🔥 Flip starting batch every week (NOW B starts first)
    start_batch = "B" if week_offset % 2 == 0 else "A"

    # Alternate within the week
    if weekday % 2 == 0:
        return start_batch
    else:
        return "A" if start_batch == "B" else "B"




def to_int(val):
    try:
        return int(val)
    except:
        return 0
    


@parade_state.route('/update_parade_state', methods=['GET', 'POST'])
def update_parade_state():
    current_user = session.get('user', {})

    if not current_user:
        flash("Please log in.", "error")
        return redirect(url_for('auth.login'))

    staff_coll = current_app.staff_collection
    app_coll = current_app.applications_collection

    directorate = current_user.get('directorate')

    today = datetime.utcnow()
    today_str = today.strftime("%Y-%m-%d")
    display_date = today.strftime("%d-%b-%Y")

    on_batch = get_on_batch(today)

    # =========================
    # 🔹 STAFF QUERY
    # =========================
    if on_batch == "ALL":
        query = {"directorate": directorate,
                 "batch": {"$in": ["A", "B"]}
        }
    else:
        query = {
            "directorate": directorate,
            "batch": on_batch
        }

    staff_list = list(staff_coll.find(query, {
        "_id": 0,
        "service_number": 1,
        "fullName": 1,
        "batch": 1,
        "status": 1
    }))

    strength = len(staff_list)

    # =========================
    # 🔹 APPLICATIONS (AUTO STATES)
    # =========================
    batch_staff_ids = [s["service_number"] for s in staff_list]

    if not batch_staff_ids:
        apps = []
    else:
        apps = app_coll.find({
            "applicantId": {"$in": batch_staff_ids},
            "status": "issued",
            "startDate": {"$lte": today},
            "endDate": {"$gte": today}
        })

    leave = 0
    pass_count = 0
    sick = 0
    seen_staff = set()

    staff_on_leave = []
    staff_on_pass = []
    staff_on_sick = []

    for app in apps:
        staff_id = app.get("applicantId")

        if staff_id in seen_staff:
            continue

        seen_staff.add(staff_id)

        lt = (app.get("leave_type") or "").lower()

        if lt == "casual":
            pass_count += 1
            staff_on_pass.append(staff_id)
        elif lt == "sick":
            sick += 1
            staff_on_sick.append(staff_id)
        else:
            leave += 1
            staff_on_leave.append(staff_id)

    # =========================
    # 🔹 VALIDATION FUNCTIONS
    # =========================
    def validate_unique_status(details):
        seen = {}
        conflicts = []

        for category, staff_list in details.items():
            for staff in staff_list:
                if staff in seen:
                    conflicts.append(f"{staff} → {seen[staff]} & {category}")
                else:
                    seen[staff] = category

        return conflicts

    def validate_staff_in_batch(all_selected):
        valid_staff_ids = set(batch_staff_ids)
        return [s for s in all_selected if s not in valid_staff_ids]

    def validate_no_duplicates(details):
        duplicates = []
        for key, lst in details.items():
            if len(lst) != len(set(lst)):
                duplicates.append(key)
        return duplicates

    # =========================
    # 🔹 POST (SAVE PARADE STATE)
    # =========================
    if request.method == "POST":

        hospital = to_int(request.form.get("hospital", 0))
        course = to_int(request.form.get("course", 0))
        absent = to_int(request.form.get("absent", 0))
        awol = to_int(request.form.get("awol", 0))
        excuse_duty = to_int(request.form.get("excuse_duty", 0))
        study_leave = to_int(request.form.get("study_leave", 0))
        cds = to_int(request.form.get("cds", 0))

        staff_absent = request.form.getlist("staff_absent")
        staff_on_hospital_admin = request.form.getlist("staff_on_hospital_admin")
        staff_on_course = request.form.getlist("staff_on_course")
        staff_on_awol = request.form.getlist("staff_on_awol")
        staff_on_excuse_duty = request.form.getlist("staff_on_excuse_duty")
        staff_on_study_leave = request.form.getlist("staff_on_study_leave")
        staff_on_cds = request.form.getlist("staff_on_cds")

        remark = request.form.get("remark", "")

        # =========================
        # 🔹 BASIC VALIDATIONS
        # =========================
        if absent != len(staff_absent):
            flash("Absent count does not match selected staff", "error")
            return redirect(request.url)

        if course != len(staff_on_course):
            flash("Course count mismatch", "error")
            return redirect(request.url)

        if hospital != len(staff_on_hospital_admin):
            flash("Hospital count mismatch", "error")
            return redirect(request.url)

        if awol != len(staff_on_awol):
            flash("AWOL count mismatch", "error")
            return redirect(request.url)

        if excuse_duty != len(staff_on_excuse_duty):
            flash("Excuse duty mismatch", "error")
            return redirect(request.url)

        if study_leave != len(staff_on_study_leave):
            flash("Study leave mismatch", "error")
            return redirect(request.url)

        if cds != len(staff_on_cds):
            flash("CDS count mismatch", "error")
            return redirect(request.url)

        numeric_fields = [hospital, course, absent, awol, excuse_duty, study_leave, cds]

        if any(n < 0 for n in numeric_fields):
            flash("Invalid negative values detected", "error")
            return redirect(request.url)

        # =========================
        # 🔹 BUILD DETAILS
        # =========================
        details = {
            "staff_absent": staff_absent,
            "staff_on_hospital_admin": staff_on_hospital_admin,
            "staff_on_course": staff_on_course,
            "staff_on_awol": staff_on_awol,
            "staff_on_excuse_duty": staff_on_excuse_duty,
            "staff_on_study_leave": staff_on_study_leave,
            "staff_on_cds": staff_on_cds,
            "staff_on_leave": staff_on_leave,
            "staff_on_pass": staff_on_pass,
            "staff_on_sick": staff_on_sick
        }

        # =========================
        # 🔥 ADVANCED VALIDATIONS
        # =========================

        # UNIQUE STATUS
        conflicts = validate_unique_status(details)
        if conflicts:
            flash(f"Conflict detected: {', '.join(conflicts)}", "error")
            return redirect(request.url)

        # BATCH VALIDATION
        all_selected = []
        for lst in details.values():
            all_selected.extend(lst)

        invalid_staff = validate_staff_in_batch(all_selected)
        if invalid_staff:
            flash(f"Invalid staff selected: {', '.join(invalid_staff)}", "error")
            return redirect(request.url)

        # DUPLICATES
        duplicate_lists = validate_no_duplicates(details)
        if duplicate_lists:
            flash(f"Duplicate entries in: {', '.join(duplicate_lists)}", "error")
            return redirect(request.url)

        # =========================
        # 🔥 FINAL CALCULATION
        # =========================
        total_states = (
            sick + leave + pass_count +
            hospital + course + absent + awol +
            excuse_duty + study_leave + cds
        )

        if total_states > strength:
            flash("Total states exceed strength", "error")
            return redirect(request.url)

        on_parade = max(0, strength - total_states)

        # =========================
        # 🔹 SAVE DOCUMENT
        # =========================
        parade_doc = {
            "date": today_str,
            "directorate": directorate,
            "batch": on_batch,
            "strength": strength,
            "on_parade": on_parade,
            "sick": sick,
            "leave": leave,
            "pass": pass_count,
            "hospital": hospital,
            "course": course,
            "absent": absent,
            "awol": awol,
            "excuse_duty": excuse_duty,
            "study_leave": study_leave,
            "cds": cds,
            "details": details,
            "remark": remark,
            "approval": {
                "status": "pending",
                "current_stage": "civilian_officer",
                "civilian_officer": {"status": "pending"},
                "deputy_director": {"status": "idle"},
                "chief_clerk": {"status": "idle"},
                "doa_rsm": {"status": "idle"}
            },
            "createdBy": current_user["service_number"],
            "createdAt": datetime.utcnow()
        }

        existing = current_app.daily_parade_states.find_one({
            "date": today_str,
            "directorate": directorate,
            "batch": on_batch
        })

        if existing:
            flash("Parade state already submitted for today!", "error")
            return redirect(request.url)

        result = current_app.daily_parade_states.insert_one(parade_doc)

        parade_doc['id'] = result.inserted_id

        # Send notification to Civilian Officer
        notify_parade_submitted(parade_doc, current_user)

        flash("Parade state saved successfully!", "success")
        return redirect(url_for('parade_state.dashboard_parade_state'))

    # =========================
    # 🔹 RENDER
    # =========================
    return render_template(
        'update_parade_state.html',
        staff_list=staff_list,
        strength=strength,
        sick=sick,
        leave=leave,
        pass_count=pass_count,
        on_batch=on_batch,
        today=display_date,
        user=current_user,
    )



def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def has_role(user, role):
    return role in user.get("roles", [])



@parade_state.route('/approve_civilian/<parade_id>', methods=['POST'])
@login_required
def approve_civilian(parade_id):
    current_user = session.get('user')

    if not has_role(current_user, "Civilian Officer"):
        flash("Unauthorized action", "error")
        return redirect(request.referrer)

    parade = current_app.daily_parade_states.find_one({"_id": ObjectId(parade_id)})

    if not parade:
        flash("Parade not found", "error")
        return redirect(request.referrer)

    if parade["directorate"] != current_user["directorate"]:
        flash("Access denied", "error")
        return redirect(request.referrer)

    if parade["approval"]["current_stage"] != "civilian_officer":
        flash("Invalid stage", "error")
        return redirect(request.referrer)

    current_app.daily_parade_states.update_one(
        {"_id": ObjectId(parade_id)},
        {"$set": {
            "approval.civilian_officer.status": "approved",
            "approval.civilian_officer.actionBy": current_user["service_number"],
            "approval.civilian_officer.actionAt": datetime.utcnow(),

            "approval.deputy_director.status": "pending",
            "approval.current_stage": "deputy_director"
        }}
    )

    # Send notification to Deputy Director
    notify_parade_next_approver(parade, "deputy_director", current_user)

    flash("Forwarded to Deputy Director", "success")
    return redirect(request.referrer)



@parade_state.route('/approve_deputy/<parade_id>', methods=['POST'])
@login_required
def approve_deputy(parade_id):
    current_user = session.get('user')

    if not has_role(current_user, "Deputy_Director"):
        flash("Unauthorized action", "error")
        return redirect(request.referrer)

    parade = current_app.daily_parade_states.find_one({"_id": ObjectId(parade_id)})

    if not parade:
        flash("Parade not found", "error")
        return redirect(request.referrer)

    if parade["directorate"] != current_user["directorate"]:
        flash("Access denied", "error")
        return redirect(request.referrer)

    if parade["approval"]["current_stage"] != "deputy_director":
        flash("Invalid stage", "error")
        return redirect(request.referrer)

    current_app.daily_parade_states.update_one(
        {"_id": ObjectId(parade_id)},
        {"$set": {
            "approval.deputy_director.status": "approved",
            "approval.deputy_director.actionBy": current_user["service_number"],
            "approval.deputy_director.actionAt": datetime.utcnow(),

            "approval.chief_clerk.status": "pending",
            "approval.doa_rsm.status": "pending",

            "approval.current_stage": "documentation",
            "approval.status": "approved"
        }}
    )

    # Send notifications to both Chief Clerk and DOA-RSM
    notify_parade_next_approver(parade, "documentation", current_user)

    flash("Sent to Chief Clerk & DOA-RSM", "success")
    return redirect(request.referrer)


@parade_state.route('/chief_clerk/<parade_id>', methods=['POST'])
@login_required
def chief_clerk(parade_id):
    current_user = session.get('user')

    if not has_role(current_user, "Chief Clerk"):
        flash("Unauthorized action", "error")
        return redirect(request.referrer)

    parade = current_app.daily_parade_states.find_one({"_id": ObjectId(parade_id)})

    if not parade:
        flash("Parade not found", "error")
        return redirect(request.referrer)

    # 🔥 CRITICAL FIX
    if parade["approval"]["current_stage"] != "documentation":
        flash("Parade not yet approved by Deputy Director", "error")
        return redirect(request.referrer)

    if parade["directorate"] != current_user["directorate"]:
        flash("Access denied", "error")
        return redirect(request.referrer)

    current_app.daily_parade_states.update_one(
        {"_id": ObjectId(parade_id)},
        {"$set": {
            "approval.chief_clerk.status": "acknowledged",
            "approval.chief_clerk.actionBy": current_user["service_number"],
            "approval.chief_clerk.actionAt": datetime.utcnow()
        }}
    )

    flash("Recorded by Chief Clerk", "success")
    return redirect(request.referrer)



@parade_state.route('/doa_rsm/<parade_id>', methods=['POST'])
@login_required
def doa_rsm(parade_id):
    current_user = session.get('user')

    if not has_role(current_user, "DOA-RSM"):
        flash("Unauthorized action", "error")
        return redirect(request.referrer)

    parade = current_app.daily_parade_states.find_one({"_id": ObjectId(parade_id)})

    if not parade:
        flash("Parade not found", "error")
        return redirect(request.referrer)

    # 🔥 CRITICAL FIX
    if parade["approval"]["current_stage"] != "documentation":
        flash("Parade not yet approved by Deputy Director", "error")
        return redirect(request.referrer)

    current_app.daily_parade_states.update_one(
        {"_id": ObjectId(parade_id)},
        {"$set": {
            "approval.doa_rsm.status": "acknowledged",
            "approval.doa_rsm.actionBy": current_user["service_number"],
            "approval.doa_rsm.actionAt": datetime.utcnow()
        }}
    )

    flash("Recorded by DOA-RSM", "success")
    return redirect(request.referrer)



@parade_state.route('/view_parade_state/<parade_id>', methods=['GET', 'POST'])
def view_parade_state(parade_id):
    current_user = session.get('user', {})

    if not current_user:
        flash("Please log in.", "error")
        return redirect(url_for('auth.login'))
    
    try:
        # Convert string to ObjectId
        obj_id = ObjectId(parade_id)
        
        # Find the parade
        parade = current_app.daily_parade_states.find_one({"_id": obj_id})
        
        if parade:
            print(f"Found parade: {parade.get('date')} - Batch {parade.get('batch')}")
            
            # Collect all service numbers from all categories
            all_service_numbers = []
            if parade.get('details'):
                for category, staff_list in parade['details'].items():
                    if isinstance(staff_list, list):
                        all_service_numbers.extend(staff_list)
            
            # Add the creator's service number
            if parade.get('createdBy'):
                all_service_numbers.append(parade['createdBy'])
            
            # Remove duplicates
            all_service_numbers = list(set(all_service_numbers))
            staff_coll = current_app.staff_collection
            staff_details = {}
            
            if all_service_numbers:
                staff_cursor = staff_coll.find({
                    "service_number": {"$in": all_service_numbers}
                })
                
                for staff in staff_cursor:
                    staff_details[staff['service_number']] = {
                        'fullName': staff.get('fullName', ''),
                        'rankOrGrade': staff.get('rankOrGrade', ''),
                        'designation': staff.get('designation', '')
                    }
            
            # Add staff details to the parade object
            parade['staff_details'] = staff_details
            
    except Exception as e:
        print(f"Error: {e}")
        flash("Error loading parade state.", "error")
        return redirect(url_for('parade_state.dashboard_parade_state'))

    if not parade:
        flash("Parade state not found.", "error")
        return redirect(url_for('parade_state.dashboard_parade_state'))

    # Format the parade date for display
    parade_date = datetime.strptime(parade['date'], "%Y-%m-%d")
    formatted_date = parade_date.strftime("%A, %d %b %Y")

    return render_template('view_parade_state.html',
                           parade=parade,
                           on_batch=parade.get('batch'),
                           today=formatted_date,
                           user=current_user)



@parade_state.route('/edit_parade_state/<parade_id>', methods=['GET', 'POST'])
def edit_parade_state(parade_id):
    current_user = session.get('user', {})

    if not current_user:
        flash("Please log in.", "error")
        return redirect(url_for('auth.login'))

    # Only Admin Officers can edit
    if "Admin Officer" not in current_user.get('roles', []):
        flash("Unauthorized access. Only Admin Officers can edit parade states.", "error")
        return redirect(url_for('parade_state.dashboard_parade_state'))

    try:
        # Find the parade state to edit
        parade = current_app.daily_parade_states.find_one({"_id": ObjectId(parade_id)})
        
        if not parade:
            flash("Parade state not found.", "error")
            return redirect(url_for('parade_state.dashboard_parade_state'))
        
        # Check if user belongs to the same directorate
        if parade.get('directorate') != current_user.get('directorate'):
            flash("You can only edit parade states from your directorate.", "error")
            return redirect(url_for('parade_state.dashboard_parade_state'))
        
        # Check if parade state is still pending (no approvals yet)
        if parade['approval']['status'] != "pending" or parade['approval']['current_stage'] != "civilian_officer":
            flash("This parade state has already entered the approval workflow and cannot be edited.", "error")
            return redirect(url_for('parade_state.dashboard_parade_state'))
        
        # Check if the user is the creator
        if parade.get('createdBy') != current_user.get('service_number'):
            flash("You can only edit parade states that you created.", "error")
            return redirect(url_for('parade_state.dashboard_parade_state'))
        
        # Get staff collection
        staff_coll = current_app.staff_collection
        directorate = current_user.get('directorate')
        on_batch = parade.get('batch')
        
        # Query staff for this batch (using the parade's batch, not today's)
        if on_batch == "ALL":
            query = {"directorate": directorate, "batch": {"$in": ["A", "B"]}}
        else:
            query = {"directorate": directorate, "batch": on_batch}
        
        staff_list = list(staff_coll.find(query, {
            "_id": 0,
            "service_number": 1,
            "fullName": 1,
            "batch": 1,
            "status": 1
        }))
        
        strength = len(staff_list)
        
        # Format the parade date for display
        parade_date = datetime.strptime(parade['date'], "%Y-%m-%d")
        display_date = parade_date.strftime("%d-%b-%Y")
        
        # Handle POST request (update the parade state)
        if request.method == "POST":
            return handle_edit_submission(parade, current_user, current_app, request, staff_list)
        
        # GET request - display the edit form with pre-filled values
        return render_template(
            'update_parade_state.html',
            staff_list=staff_list,
            strength=strength,
            parade=parade,
            is_edit=True,  # Flag for template to show edit mode
            edit_mode=True,
            on_batch=on_batch,
            today=display_date,  # Show the parade's date, not today
            user=current_user,
            # Pre-filled values from the existing parade
            sick=parade.get('sick', 0),
            leave=parade.get('leave', 0),
            pass_count=parade.get('pass', 0),
            hospital=parade.get('hospital', 0),
            course=parade.get('course', 0),
            absent=parade.get('absent', 0),
            awol=parade.get('awol', 0),
            excuse_duty=parade.get('excuse_duty', 0),
            study_leave=parade.get('study_leave', 0),
            cds=parade.get('cds', 0),
            remark=parade.get('remark', ''),
            # Staff lists from details
            staff_absent=parade.get('details', {}).get('staff_absent', []),
            staff_on_hospital_admin=parade.get('details', {}).get('staff_on_hospital_admin', []),
            staff_on_course=parade.get('details', {}).get('staff_on_course', []),
            staff_on_awol=parade.get('details', {}).get('staff_on_awol', []),
            staff_on_excuse_duty=parade.get('details', {}).get('staff_on_excuse_duty', []),
            staff_on_study_leave=parade.get('details', {}).get('staff_on_study_leave', []),
            staff_on_cds=parade.get('details', {}).get('staff_on_cds', []),
            # Auto-populated fields (preserved)
            staff_on_leave=parade.get('details', {}).get('staff_on_leave', []),
            staff_on_pass=parade.get('details', {}).get('staff_on_pass', []),
            staff_on_sick=parade.get('details', {}).get('staff_on_sick', [])
        )
        
    except Exception as e:
        print(f"Error in edit_parade_state: {e}")
        flash("Error loading parade state for editing.", "error")
        return redirect(url_for('parade_state.dashboard_parade_state'))


def handle_edit_submission(parade, current_user, current_app, request, staff_list):
    """Handle the POST submission for editing a parade state"""
    
    # Get form data
    hospital = int(request.form.get("hospital", 0))
    course = int(request.form.get("course", 0))
    absent = int(request.form.get("absent", 0))
    awol = int(request.form.get("awol", 0))
    excuse_duty = int(request.form.get("excuse_duty", 0))
    study_leave = int(request.form.get("study_leave", 0))
    cds = int(request.form.get("cds", 0))
    
    # Get staff lists
    staff_absent = request.form.getlist("staff_absent")
    staff_on_hospital_admin = request.form.getlist("staff_on_hospital_admin")
    staff_on_course = request.form.getlist("staff_on_course")
    staff_on_awol = request.form.getlist("staff_on_awol")
    staff_on_excuse_duty = request.form.getlist("staff_on_excuse_duty")
    staff_on_study_leave = request.form.getlist("staff_on_study_leave")
    staff_on_cds = request.form.getlist("staff_on_cds")
    
    # Get auto-populated staff from the original parade (these don't change in edit mode)
    staff_on_leave = parade.get('details', {}).get('staff_on_leave', [])
    staff_on_pass = parade.get('details', {}).get('staff_on_pass', [])
    staff_on_sick = parade.get('details', {}).get('staff_on_sick', [])
    
    remark = request.form.get("remark", "")
    
    # Validate counts
    if absent != len(staff_absent):
        flash("Absent count does not match selected staff", "error")
        return redirect(request.url)
    
    if course != len(staff_on_course):
        flash("Course count mismatch", "error")
        return redirect(request.url)
    
    if hospital != len(staff_on_hospital_admin):
        flash("Hospital count mismatch", "error")
        return redirect(request.url)
    
    if awol != len(staff_on_awol):
        flash("AWOL count mismatch", "error")
        return redirect(request.url)
    
    if excuse_duty != len(staff_on_excuse_duty):
        flash("Excuse duty mismatch", "error")
        return redirect(request.url)
    
    if study_leave != len(staff_on_study_leave):
        flash("Study leave mismatch", "error")
        return redirect(request.url)
    
    if cds != len(staff_on_cds):
        flash("CDS count mismatch", "error")
        return redirect(request.url)
    
    # Check for negative values
    numeric_fields = [hospital, course, absent, awol, excuse_duty, study_leave, cds]
    if any(n < 0 for n in numeric_fields):
        flash("Invalid negative values detected", "error")
        return redirect(request.url)
    
    # Build details dictionary
    details = {
        "staff_absent": staff_absent,
        "staff_on_hospital_admin": staff_on_hospital_admin,
        "staff_on_course": staff_on_course,
        "staff_on_awol": staff_on_awol,
        "staff_on_excuse_duty": staff_on_excuse_duty,
        "staff_on_study_leave": staff_on_study_leave,
        "staff_on_cds": staff_on_cds,
        "staff_on_leave": staff_on_leave,
        "staff_on_pass": staff_on_pass,
        "staff_on_sick": staff_on_sick
    }
    
    # Check for duplicate staff in different categories
    all_selected = []
    for lst in details.values():
        all_selected.extend(lst)
    
    # Check if any staff appears more than once
    from collections import Counter
    duplicates = [item for item, count in Counter(all_selected).items() if count > 1]
    if duplicates:
        flash(f"Staff cannot be in multiple categories: {', '.join(duplicates)}", "error")
        return redirect(request.url)
    
    # Calculate totals
    total_states = (
        parade.get('sick', 0) + parade.get('leave', 0) + parade.get('pass', 0) +
        hospital + course + absent + awol + excuse_duty + study_leave + cds
    )
    
    if total_states > parade.get('strength', 0):
        flash("Total states exceed strength", "error")
        return redirect(request.url)
    
    on_parade = max(0, parade.get('strength', 0) - total_states)
    
    # Update the parade state
    current_app.daily_parade_states.update_one(
        {"_id": parade['_id']},
        {"$set": {
            "sick": parade.get('sick', 0),
            "leave": parade.get('leave', 0),
            "pass": parade.get('pass', 0),
            "hospital": hospital,
            "course": course,
            "absent": absent,
            "awol": awol,
            "excuse_duty": excuse_duty,
            "study_leave": study_leave,
            "cds": cds,
            "on_parade": on_parade,
            "details": details,
            "remark": remark,
            "updatedAt": datetime.utcnow(),
            "updatedBy": current_user['service_number']
        }}
    )
    
    flash("Parade state updated successfully!", "success")
    return redirect(url_for('parade_state.dashboard_parade_state'))



@parade_state.route('/filter_parade_states', methods=['GET'])
def filter_parade_states():
    current_user = session.get('user', {})
    
    if not current_user:
        return jsonify({'error': 'Not logged in'}), 401
    
    directorate = current_user.get("directorate")
    filter_type = request.args.get('filter', '')
    filter_value = request.args.get('value', '')
    user_roles = current_user.get("roles", [])

    parade_coll = current_app.daily_parade_states

    # Base query
    if "DOA-RSM" in user_roles:
        # DOA-RSM sees only approved parade states
        query = {"approval.status": "approved"}
    else:
        # Others see their directorate
        query = {"directorate": directorate}
    
    # Apply additional filters
    if filter_type == 'status' and filter_value:
        query["approval.status"] = filter_value
    
    elif filter_type == 'batch' and filter_value:
        if filter_value in ['A', 'B']:
            query["batch"] = filter_value
    
    elif filter_type == 'date' and filter_value:
        query["date"] = filter_value
    
    elif filter_type == 'month' and filter_value:
        from bson import Regex
        # filter_value should be like '2026-03'
        query["date"] = Regex(f"^{filter_value}")
    
    # Execute query
    parade_list = list(parade_coll.find(query).sort("createdAt", -1))
    
    # Convert ObjectId to string for JSON serialization
    for parade in parade_list:
        parade['_id'] = str(parade['_id'])

        # Ensure all fields exist
        parade.setdefault('batch', '')
        parade.setdefault('date', '')
        parade.setdefault('strength', 0)
        parade.setdefault('on_parade', 0)
        parade.setdefault('sick', 0)
        parade.setdefault('leave', 0)
        parade.setdefault('pass', 0)
        parade.setdefault('course', 0)
        parade.setdefault('hospital', 0)
        parade.setdefault('absent', 0)
        parade.setdefault('awol', 0)
        parade.setdefault('excuse_duty', 0)
        parade.setdefault('study_leave', 0)
        parade.setdefault('cds', 0)
        parade.setdefault('directorate', '')
        parade.setdefault('approval', {'status': 'pending'})
    
    return jsonify(parade_list)



@parade_state.route('/mark_notification_read/<notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    current_user = session.get('user')
    
    if not current_user:
        return jsonify({"error": "Not logged in"}), 401
    
    notifications_coll = current_app.notifications_collection
    
    try:
        result = notifications_coll.update_one(
            {"_id": ObjectId(notification_id)},
            {
                "$set": {
                    "status": "read",
                    "updatedAt": datetime.utcnow()
                },
                "$addToSet": {
                    "readBy": current_user["service_number"]
                }
            }
        )
        
        if result.modified_count > 0:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "message": "Notification not found"}), 404
            
    except Exception as e:
        print(f"Error marking notification as read: {e}")
        return jsonify({"error": str(e)}), 500


@parade_state.route('/get_unread_notifications', methods=['GET'])
@login_required
def get_unread_notifications():
    current_user = session.get('user')
    
    if not current_user:
        return jsonify({"error": "Not logged in"}), 401
    
    directorate = current_user.get('directorate')
    roles = current_user.get('roles', [])
    service_number = current_user.get('service_number')
    
    notifications_coll = current_app.notifications_collection
    
    # Build query for notifications targeting this user
    query = {
        "status": "unread",
        "isActive": True,
        "$or": [
            {"target.userId": service_number},
            {"target.role": {"$in": roles}, "target.directorate": directorate}
        ]
    }
    
    # If user is DOA-RSM, they might need to see notifications from all directorates
    if "DOA-RSM" in roles:
        query = {
            "status": "unread",
            "isActive": True,
            "$or": [
                {"target.userId": service_number},
                {"target.role": {"$in": roles}}
            ]
        }
    
    try:
        notifications = list(notifications_coll.find(query).sort("createdAt", -1).limit(10))
        
        # Format notifications for frontend
        formatted_notifications = []
        for notif in notifications:
            # Extract meta data if it exists
            meta = notif.get('meta', {})
            
            formatted_notif = {
                '_id': str(notif.get('applicationId', notif['_id'])),  # Use applicationId if available
                'notification_id': str(notif['_id']),
                'type': notif.get('type', 'unknown'),
                'message': notif.get('message', ''),
                'status': notif.get('status', 'unread'),
                'triggeredBy': meta.get('triggeredByName', notif.get('meta', {}).get('triggeredBy', 'System')),
                'date': meta.get('date'),
                'batch': meta.get('batch'),
                'directorate': meta.get('directorate'),
                'action': 'submitted' if 'submitted' in notif.get('message', '').lower() else 'approval'
            }
            
            formatted_notifications.append(formatted_notif)
        
        return jsonify(formatted_notifications)
        
    except Exception as e:
        print(f"Error fetching notifications: {e}")
        return jsonify({"error": str(e)}), 500