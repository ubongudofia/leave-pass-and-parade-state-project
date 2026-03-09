from flask import Blueprint, app, render_template, session, jsonify, make_response, flash, redirect, url_for, current_app, send_file, abort, request
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from functools import wraps
from flask_login import current_user
import gridfs
import io
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from app.extensions import socketio
from flask_socketio import emit, join_room

# Insufficient annual leave balance. Available: 1 days, Requested: 5 days

approver_dashboard = Blueprint('approver_dashboard', __name__)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function



def notify_pending_approval(app, next_step, current_user):
    """
    Emits a Socket.IO notification to the next approver for real-time modal.
    """
    approver_id = next_step.get("approverId")
    if not approver_id:
        return

    print(f"🔍 Looking for approver with service_number: {approver_id}")

    # Find staff member
    approver_user = current_app.staff_collection.find_one({"service_number": approver_id})
    if not approver_user:
        return


    # Notification message
    message = f"Application {app['referenceId']} is awaiting your approval."
    print("DEBUG leave_type:", app.get("leave_type"))
    print("DEBUG APP:", app)

    # Build payload
    payload = {
        "type": "leave_approval",
        "_id": str(app["_id"]),
        "applicationId": str(app["_id"]),
        "triggeredBy": current_user.get("fullName"),
        "referenceId": app["referenceId"],
        "message": message,
        "role": next_step.get("role"),
        "leave_type": app.get("leave_type"),
        "directorate": approver_user.get("directorate"),
        "date": app.get("createdAt").strftime('%Y-%m-%d') if app.get("createdAt") else None,


    }

    # Make service_number safe for room naming
    safe_approver_id = approver_id.replace("/", "_")
    room = f"USER_{safe_approver_id}"
    socketio.emit("new_notification", payload, room=room)




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

    print("Joining rooms for:", service_number)
    safe_service_number = service_number.replace("/", "_")  # Replace slashes for room naming

    join_room(f"USER_{safe_service_number}")


    print("Joined:", f"USER_{safe_service_number}")

    for role in roles:
        if role == "SO1-DOA":
            join_room(f"ROLE_{role}")
            print("Joined:", f"ROLE_{role}")
        elif directorate:
            join_room(f"DIR_{directorate}_{role}")
            print("Joined:", f"DIR_{directorate}_{role}")



@approver_dashboard.route('/dashboard_main')
@login_required
def dashboard_main():
    # Get current logged-in user info from session
    current_user = session.get('user')
    if not current_user:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for('auth.login'))

    user_id = current_user['service_number']
    user_directorate = current_user['directorate']
    user_roles = current_user.get('roles', [])
    
    is_so1_doa = 'SO1-DOA' in user_roles
    is_chief_clerk = 'Chief Clerk' in user_roles

    applications_coll = current_app.applications_collection
    staff_coll = current_app.staff_collection

    # ========== BUILD FILTER QUERY FROM REQUEST PARAMS ==========
    filter_query = {}
    
    # Get filter parameters from request
    filter_directorate = request.args.get('directorate', '')
    filter_status = request.args.get('status', '')
    filter_leave_type = request.args.get('batch', '')
    filter_date_from = request.args.get('date_from', '')
    filter_date_to = request.args.get('date_to', '')
    
    # Apply directorate filter (only for SO1-DOA)
    if filter_directorate and is_so1_doa:
        filter_query['directorate'] = filter_directorate
    elif not is_so1_doa and not is_chief_clerk:
        # Non-SO1-DOA, non-Chief Clerk only see their directorate
        filter_query['directorate'] = user_directorate
    elif is_chief_clerk:
        # Chief Clerk sees their directorate
        filter_query['directorate'] = user_directorate
    
    # Apply leave type filter
    if filter_leave_type:
        filter_query['leave_type'] = filter_leave_type
    
    # Date range filter
    date_query = {}
    if filter_date_from:
        try:
            date_from = datetime.strptime(filter_date_from, '%Y-%m-%d')
            date_query['$gte'] = date_from
        except ValueError:
            pass
    
    if filter_date_to:
        try:
            date_to = datetime.strptime(filter_date_to, '%Y-%m-%d')
            date_to = date_to.replace(hour=23, minute=59, second=59)
            date_query['$lte'] = date_to
        except ValueError:
            pass
    
    if date_query:
        filter_query['createdAt'] = date_query

    print(f"🔍 Filter Query: {filter_query}")

    # ────────────────────────────────────────────────────────────────
    # FETCH ALL APPLICATIONS FOR THIS USER (ONE TIME ONLY)
    # ────────────────────────────────────────────────────────────────
    
    pending_applications = []
    approved_applications = []
    rejected_applications = []
    
    if is_so1_doa:
        # ==================== SO1-DOA ====================
        # SO1-DOA sees applications forwarded by Chief Clerk
        
        # Build base query for SO1-DOA
        base_query = {
            "finalApproval.status": "pending",
            "approvalChain.forward_status": "forwarded",
            **filter_query
        }
        
        # Get all applications matching criteria
        all_apps_cursor = applications_coll.find(base_query).sort("createdAt", -1).limit(200)
        
        for app in all_apps_cursor:
            chain = app.get("approvalChain", [])
            
            # Check if all non-Chief Clerk steps are approved
            all_non_chief_approved = all(
                step["status"] == "approved" 
                for step in chain 
                if step["role"] != "Chief Clerk"
            )
            
            # Check Chief Clerk has forwarded
            chief_clerk_step = next((s for s in chain if s["role"] == "Chief Clerk"), None)
            chief_clerk_forwarded = chief_clerk_step and chief_clerk_step.get("forward_status") == "forwarded"
            
            if all_non_chief_approved and chief_clerk_forwarded:
                # This is pending for SO1-DOA's final approval
                pending_applications.append(app)
                
                # Also add to appropriate status lists for display
                if app.get("status") == "pending":
                    pass  # Already in pending_applications
                elif app.get("status") == "approved" or app.get("status") == "issued":
                    approved_applications.append(app)
                elif app.get("status") == "rejected":
                    rejected_applications.append(app)
        
        # Also fetch approved/rejected applications (with filters)
        approved_query = {
            "finalApproval.status": "approved",
            **filter_query
        }
        for app in applications_coll.find(approved_query).sort("finalApproval.timestamp", -1).limit(50):
            approved_applications.append(app)
        
        rejected_query = {
            "finalApproval.status": "rejected",
            **filter_query
        }
        for app in applications_coll.find(rejected_query).sort("finalApproval.timestamp", -1).limit(50):
            rejected_applications.append(app)
            
    elif is_chief_clerk:
        # ==================== CHIEF CLERK ====================
        
        # Pending applications (waiting for Chief Clerk to forward)
        pending_query = {
            "directorate": user_directorate,
            "finalApproval.status": "pending",
            "approvalChain": {
                "$elemMatch": {
                    "role": "Chief Clerk",
                    "approverId": user_id,
                    "forward_status": "not_forwarded",
                    "status": "pending"
                }
            },
            **filter_query
        }
        
        cursor_pending = applications_coll.find(pending_query).sort("updatedAt", -1).limit(200)
        
        for app in cursor_pending:
            chain = app.get("approvalChain", [])
            
            # Find Chief Clerk position
            chief_clerk_index = None
            for i, step in enumerate(chain):
                if step["role"] == "Chief Clerk" and step["approverId"] == user_id:
                    chief_clerk_index = i
                    break
            
            if chief_clerk_index is None:
                continue
            
            # Check if all steps before Chief Clerk are approved
            all_previous_approved = all(
                chain[i]["status"] == "approved" 
                for i in range(chief_clerk_index)
            )
            
            if all_previous_approved:
                pending_applications.append(app)
        
        # Approved/forwarded applications
        approved_query = {
            "directorate": user_directorate,
            "finalApproval.status": "approved",
            "approvalChain": {
                "$elemMatch": {
                    "role": "Chief Clerk",
                    "approverId": user_id,
                    "forward_status": "forwarded"
                }
            },
            **filter_query
        }
        
        cursor_approved = applications_coll.find(approved_query).sort("finalApproval.timestamp", -1).limit(50)
        for app in cursor_approved:
            approved_applications.append(app)
        
        # Rejected applications
        rejected_query = {
            "directorate": user_directorate,
            "$or": [
                {"finalApproval.status": "rejected"},
                {"approvalChain.status": "rejected"}
            ],
            "approvalChain": {
                "$elemMatch": {
                    "role": "Chief Clerk",
                    "approverId": user_id
                }
            },
            **filter_query
        }
        
        cursor_rejected = applications_coll.find(rejected_query).sort("updatedAt", -1).limit(50)
        for app in cursor_rejected:
            rejected_applications.append(app)
    
    else:
        # ==================== NORMAL APPROVERS (Civilian Officer, SSO, DD, Director) ====================
        
        # Get ALL applications where this user appears in approval chain
        user_apps_query = {
            "approvalChain.approverId": user_id,
            **filter_query
        }
        
        all_apps_cursor = applications_coll.find(user_apps_query).sort("createdAt", -1).limit(500)
        
        for app in all_apps_cursor:
            chain = app.get("approvalChain", [])
            app_status = app.get("status")
            final_approval = app.get("finalApproval", {})
            
            # Find this user's position and status
            user_found = False
            user_status = None
            user_index = None
            
            for i, step in enumerate(chain):
                if step.get("approverId") == user_id:
                    user_found = True
                    user_status = step.get("status")
                    user_index = i
                    break
            
            if not user_found:
                continue
            

            if app_status == "issued" or final_approval.get("status") == "approved":
                approved_applications.append(app)

            elif app_status == "rejected" or any(step.get("status") == "rejected" for step in chain):
                rejected_applications.append(app)

            elif user_status == "approved":
                approved_applications.append(app)

            elif user_status == "rejected":
                rejected_applications.append(app)

            elif user_status == "pending":
                all_previous_approved = all(
                    chain[i]["status"] == "approved"
                    for i in range(user_index)
                )

                if all_previous_approved:
                    pending_applications.append(app)

    # ========== CALCULATE COUNTS ==========
    pending_count = len(pending_applications)
    approved_count = len(approved_applications)
    rejected_count = len(rejected_applications)
    total_count = pending_count + approved_count + rejected_count

    # ========== COMBINE ALL APPLICATIONS FOR DISPLAY ==========
    all_apps = pending_applications + approved_applications + rejected_applications
    
    # Remove duplicates
    seen_ids = set()
    unique_apps = []
    for app in all_apps:
        app_id = str(app['_id'])
        if app_id not in seen_ids:
            seen_ids.add(app_id)
            unique_apps.append(app)

    # Sort by createdAt date (newest first)
    unique_apps.sort(key=lambda x: x.get('createdAt', datetime.min), reverse=True)

    # ========== ENRICH WITH APPLICANT NAME ==========
    for app in unique_apps:
        if 'applicantName' not in app or not app.get('applicantName'):
            # Try to find by service_number
            applicant = staff_coll.find_one(
                {"service_number": app.get("applicantId")},
                {"fullName": 1}
            )
            if not applicant:
                # Try by _id as fallback
                applicant = staff_coll.find_one(
                    {"_id": app.get("applicantId")},
                    {"fullName": 1}
                )
            app['applicantName'] = applicant['fullName'] if applicant else "Unknown"

    # ========== FETCH DIRECTORATE STATISTICS (FOR SO1-DOA) ==========
    directorate_stats = []
    all_directorates = []
    
    if is_so1_doa:
        all_directorates = applications_coll.distinct('directorate')
        
        stats_match = {
            "finalApproval.status": "pending",
            "approvalChain.forward_status": "forwarded",
            **filter_query
        }
        
        pipeline = [
            {"$match": stats_match},
            {"$group": {
                "_id": "$directorate",
                "count": {"$sum": 1},
                "latest_date": {"$max": "$createdAt"}
            }},
            {"$sort": {"_id": 1}}
        ]
        directorate_stats = list(applications_coll.aggregate(pipeline))
        
        for stat in directorate_stats:
            if stat.get('latest_date'):
                if isinstance(stat['latest_date'], datetime):
                    stat['latest_date'] = stat['latest_date'].strftime('%d %b %Y')
            stat['latest_batch'] = 'N/A'

    # ========== PREPARE FILTER VALUES FOR TEMPLATE ==========
    filter_values = {
        'filter_directorate': filter_directorate if is_so1_doa else '',
        'filter_status': filter_status,
        'filter_leave_type': filter_leave_type,
        'filter_date_from': filter_date_from,
        'filter_date_to': filter_date_to
    }

    # Debug output
    print(f"📊 Results: {len(unique_apps)} total applications")
    print(f"   Pending: {pending_count}, Approved: {approved_count}, Rejected: {rejected_count}")

    return render_template(
        'dashboard_main.html',
        applications=unique_apps,
        user=current_user,
        current_time=datetime.utcnow(),
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        total_count=total_count,
        is_so1_doa=is_so1_doa,
        is_chief_clerk=is_chief_clerk,
        directorate_stats=directorate_stats,
        all_directorates=all_directorates,
        **filter_values
    )

@approver_dashboard.route('/approve/<string:app_id>', methods=['POST'])
@login_required
def approve(app_id):
    current_user = session.get('user')
    if not current_user:
        flash("Session expired.", "error")
        return redirect(url_for('auth.login'))

    applications_coll = current_app.applications_collection
    notifications_coll = current_app.notifications_collection
    staff_coll = current_app.staff_collection

    # Fetch application
    try:
        app = applications_coll.find_one({"_id": ObjectId(app_id)})
        if not app:
            flash("Application not found.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))
    except Exception:
        flash("Invalid application ID.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    if app.get("status") != "pending":
        flash(f"Cannot approve: Application is already {app.get('status')}.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    approval_chain = app.get("approvalChain", [])

    # Find current user's pending step
    user_step_index = next(
        (i for i, s in enumerate(approval_chain)
         if s.get("approverId") == current_user["service_number"]
         and s.get("status") == "pending"),
        None
    )

    if user_step_index is None:
        flash("This application is not waiting for your approval.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    # Ensure previous steps approved
    for i in range(user_step_index):
        if approval_chain[i]["status"] != "approved":
            flash("Previous approvals are still pending.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))

    # Approve current step
    step = approval_chain[user_step_index]
    step.update({
        "status": "approved",
        "comments": request.form.get("comments", "").strip() or "Approved",
        "timestamp": datetime.utcnow(),
        "approverName": current_user.get("fullName"),
        "approverRank": current_user.get("rankOrGrade"),
        "approverDesignation": current_user.get("designation")
    })

    # Find next pending step
    next_step = next((s for s in approval_chain if s["status"] == "pending"), None)

    notification = notifications_coll.find_one({"applicationId": app["_id"]})

    # ===============================
    # CASE 1: There is a next approver
    # ===============================
    if next_step:

        approver_user = staff_coll.find_one({"service_number": next_step["approverId"]})

        # If next step is SO1-DOA → Activate finalApproval
        if next_step["role"] == "SO1-DOA":
            app["finalApproval"] = {
                "approverId": next_step["approverId"],
                "status": "pending"
            }

        target = {
            "type": "role",
            "directorate": approver_user["directorate"] if approver_user else None,
            "role": next_step["role"],
            "userId": next_step["approverId"]
        }

        if not notification:
            notification = {
                "type": "approval_required",
                "applicationId": app["_id"],
                "referenceId": app.get("referenceId"),
                "target": target,
                "message": f"Application {app.get('referenceId')} is awaiting your approval.",
                "status": "unread",
                "readBy": [],
                "meta": {
                    "triggeredBy": current_user["service_number"],
                    "triggeredByName": current_user["fullName"]
                },
                "createdAt": datetime.utcnow(),
                "isActive": True
            }
            notifications_coll.insert_one(notification)
        else:
            notifications_coll.update_one(
                {"_id": notification["_id"]},
                {"$set": {
                    "target": target,
                    "status": "unread",
                    "meta": {
                        "triggeredBy": current_user["service_number"],
                        "triggeredByName": current_user["fullName"]
                    },
                    "updatedAt": datetime.utcnow(),
                    "isActive": True
                }}
            )

        # Emit real-time notification for modal
        notify_pending_approval(app, next_step, current_user)

    # ===============================
    # CASE 2: No next step → Final approval completed
    # ===============================
    else:

        # If finalApproval exists → mark completed
        if app.get("finalApproval"):
            app["finalApproval"]["status"] = "approved"

        app["status"] = "approved"

        if notification:
            notifications_coll.update_one(
                {"_id": notification["_id"]},
                {"$set": {
                    "type": "approval_completed",
                    "status": "read",
                    "isActive": False,
                    "updatedAt": datetime.utcnow()
                }}
            )

    # ===============================
    # SAVE APPLICATION (Schema Safe)
    # ===============================

    update_data = {
        "approvalChain": approval_chain,
        "status": app.get("status", "pending"),
        "updatedAt": datetime.utcnow()
    }

    if "finalApproval" in app:
        update_data["finalApproval"] = app["finalApproval"]

    applications_coll.update_one(
        {"_id": app["_id"]},
        {"$set": update_data}
    )

    flash("Application approved successfully.", "success")
    return redirect(url_for('approver_dashboard.dashboard_main'))



@approver_dashboard.route('/reject/<string:app_id>', methods=['GET', 'POST'])
@login_required
def reject(app_id):
    """Reject a pending application by an approver in the chain"""
    current_user = session.get('user')
    if not current_user:
        flash("Session expired.", "error")
        return redirect(url_for('auth.login'))

    applications_coll = current_app.applications_collection

    try:
        app = applications_coll.find_one({"_id": ObjectId(app_id)})
        if not app:
            flash("Application not found.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))
    except:
        flash("Invalid application ID.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    # Check if application is still pending
    if app.get("status") != "pending":
        flash(f"Cannot reject: Application is already {app.get('status')}.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    user_id = current_user['service_number']
    
    # Find user's position in chain
    chain = app.get("approvalChain", [])
    user_index = None
    
    for i, step in enumerate(chain):
        if step["approverId"] == user_id and step["status"] == "pending":
            user_index = i
            break
    
    if user_index is None:
        flash("This application is not waiting for your action.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    if request.method == 'POST':
        comments = request.form.get('comments', '').strip()

        if not comments:
            flash("Comments are required for rejection.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))

        # ============ ADD REFUND FUNCTION ============
        # Check if balance was already deducted (status would be 'issued')
        if app.get("status") == "issued":
            # Only SO1-DOA can issue, so this shouldn't happen at lower levels
            # But just in case, refund if it was somehow issued
            try:
                from .leave_helper import refund_leave_balance
                refund_success = refund_leave_balance(
                    service_number=app.get("applicantId"),
                    application=app
                )
                if refund_success:
                    print(f"✓ Leave balance refunded for {app.get('applicantId')}")
            except Exception as e:
                print(f"ERROR refunding leave balance: {e}")
        # =============================================

        updated = False

        for step in chain:
            if step["approverId"] == current_user['service_number'] and step["status"] == "pending":
                step["status"] = "rejected"
                step["comments"] = comments
                step["timestamp"] = datetime.utcnow()

                if not step.get("approverName"):
                    step["approverName"] = current_user['fullName']
                if not step.get("approverRank"):
                    step["approverRank"] = current_user.get('rankOrGrade', '')
                if not step.get("approverDesignation"):
                    step["approverDesignation"] = current_user.get('designation', '')

                updated = True
                break

        if not updated:
            flash("You are not authorized to reject this application or it has already been processed.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))

        # Set overall status to rejected
        applications_coll.update_one(
            {"_id": ObjectId(app_id)},
            {
                "$set": {
                    "approvalChain": chain,
                    "status": "rejected",
                    "finalApproval.status": "rejected",
                    "updatedAt": datetime.utcnow()
                }
            }
        )

        # TRIGGER REJECTION NOTIFICATION EMAIL TO APPLICANT 
        staff_coll = current_app.staff_collection

        applicant = staff_coll.find_one(
            {"service_number": app.get("applicantId")}
        )

        if applicant and applicant.get("email"):
            try:
                from utils.email_service import send_rejection_email
                send_rejection_email(
                    applicant_email=applicant["email"],
                    applicant_name=applicant.get("fullName"),
                    application=app,
                    rejected_by=current_user.get("fullName"),
                    comments=comments
                )
            except Exception as e:
                print("Email sending failed:", e)
        # Emit Socket.IO notification to applicant room
        try:
            current_app.socketio.emit(
                "application_update",
                {"status": "rejected", "comments": comments, "referenceId": app.get("referenceId")},
                room=f"APPLICATION_{app.get('referenceId')}"
            )
        except Exception as e:
            print(f"Socket.IO emit failed: {e}")

        flash("Application rejected.", "info")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    return redirect(url_for('approver_dashboard.dashboard_main'))



@approver_dashboard.route('/forward/<string:app_id>', methods=['POST'])
@login_required
def forward(app_id):
    current_user = session.get('user')
    if not current_user:
        flash("Session expired.", "error")
        return redirect(url_for('auth.login'))

    if "Chief Clerk" not in current_user.get('roles', []):
        flash("You are not authorized to forward applications.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    applications_coll = current_app.applications_collection
    notifications_coll = current_app.notifications_collection

    try:
        app = applications_coll.find_one({"_id": ObjectId(app_id)})
        if not app:
            flash("Application not found.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))
    except:
        flash("Invalid application ID.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    # Ensure application is still pending
    if app.get("status") != "pending":
        flash(f"Cannot forward: Application already {app.get('status')}.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    chain = app.get("approvalChain", [])
    chief_index = None

    # --------------------------------------------------
    # FIND CHIEF CLERK STEP (BASED ON approverId)
    # --------------------------------------------------
    for i, step in enumerate(chain):
        if (
            step.get("role") == "Chief Clerk"
            and step.get("approverId") == current_user.get("service_number")
            and step.get("status") == "pending"
        ):
            chief_index = i
            break

    if chief_index is None:
        flash("This application is not waiting for your action.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    # --------------------------------------------------
    # ENSURE PREVIOUS APPROVALS ARE COMPLETE
    # --------------------------------------------------
    for i in range(chief_index):
        if chain[i].get("status") != "approved":
            flash("Cannot forward: Previous approvals incomplete.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))

    # Prevent double forward
    if chain[chief_index].get("forward_status") == "forwarded":
        flash("Application already forwarded.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    comments = request.form.get('comments', '').strip()

    # --------------------------------------------------
    # MARK CHIEF CLERK AS APPROVED + FORWARDED
    # --------------------------------------------------
    chain[chief_index].update({
        "status": "approved",
        "forward_status": "forwarded",
        "forwardedAt": datetime.utcnow(),
        "timestamp": datetime.utcnow(),
        "comments": comments or "Forwarded to SO1-DOA",
        "approverName": current_user.get("fullName"),
        "approverRank": current_user.get("rankOrGrade"),
        "approverDesignation": current_user.get("designation")
    })

    # --------------------------------------------------
    # GET FINAL APPROVER (SO1-DOA)
    # --------------------------------------------------
    final_approver_id = app.get("finalApproval", {}).get("approverId")

    if not final_approver_id:
        flash("Final approver not configured.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    # --------------------------------------------------
    # UPDATE APPLICATION
    # --------------------------------------------------
    applications_coll.update_one(
        {"_id": ObjectId(app_id)},
        {
            "$set": {
                "approvalChain": chain,
                "updatedAt": datetime.utcnow()
            },
            "$push": {
                "auditTrail": {
                    "action": "forward_to_final_approval",
                    "by": current_user.get("service_number"),
                    "byName": current_user.get("fullName"),
                    "role": "Chief Clerk",
                    "timestamp": datetime.utcnow(),
                    "comments": comments
                }
            }
        }
    )

    # --------------------------------------------------
    # CREATE NOTIFICATION FOR SO1-DOA
    # --------------------------------------------------
    notification_doc = {
        "type": "final_approval_required",
        "applicationId": app["_id"],
        "referenceId": app.get("referenceId"),

        "target": {
            "type": "user",
            "userId": final_approver_id
        },

        "message": f"Application {app.get('referenceId')} awaiting final approval.",

        "status": "unread",
        "readBy": [],
        "isActive": True,  # 🔥 REQUIRED BY YOUR SCHEMA
        "createdAt": datetime.utcnow(),

        "meta": {
            "triggeredBy": current_user.get("service_number"),
            "triggeredByName": current_user.get("fullName")
        }
    }

    notifications_coll.insert_one(notification_doc)

    # --------------------------------------------------
    # EMIT DIRECTLY TO SO1 USER ROOM
    # --------------------------------------------------
    # socketio.emit(
    #     "new_notification",
    #     notification_doc,
    #     room=f"USER_{final_approver_id}"
    # )

    # --------------------------------------------------
    # EMIT REAL-TIME NOTIFICATION TO FINAL APPROVER
    # --------------------------------------------------
    # Build a proper next_step dict
    next_step = {
        "approverId": final_approver_id,
        "role": "SO1-DOA"
    }

    notify_pending_approval(app, next_step, current_user)

    flash("Application forwarded to SO1-DOA successfully.", "success")
    return redirect(url_for('approver_dashboard.dashboard_main'))




def calendar_days_between(start_date, end_date):
    """Calculate calendar days between two dates."""
    if not start_date or not end_date:
        return 0
    if isinstance(start_date, dict) and "$date" in start_date:
        start_date = datetime.fromisoformat(start_date["$date"].replace("Z", "+00:00"))
    if isinstance(end_date, dict) and "$date" in end_date:
        end_date = datetime.fromisoformat(end_date["$date"].replace("Z", "+00:00"))
    return (end_date - start_date).days + 1


# @approver_dashboard.route('/final_approve/<string:app_id>', methods=['GET', 'POST'])
# @login_required
# def final_approve(app_id):
#     current_user = session.get('user')
    
#     if not current_user:
#         flash("Session expired.", "error")
#         return redirect(url_for('auth.login'))

#     if "SO1-DOA" not in current_user.get('roles', []):
#         flash("You are not authorized for final approval.", "error")
#         return redirect(url_for('approver_dashboard.dashboard_main'))

#     applications_coll = current_app.applications_collection
#     leave_balances_coll = current_app.leave_balances
#     notifications_coll = current_app.notifications_collection

#     try:
#         app = applications_coll.find_one({"_id": ObjectId(app_id)})
#         if not app:
#             flash("Application not found.", "error")
#             return redirect(url_for('approver_dashboard.dashboard_main'))
#     except:
#         flash("Invalid application ID.", "error")
#         return redirect(url_for('approver_dashboard.dashboard_main'))

#     # Check if application is still pending (not already issued/rejected)
#     if app.get("status") != "pending":
#         flash(f"Cannot approve: Application is already {app.get('status')}.", "error")
#         return redirect(url_for('approver_dashboard.dashboard_main'))

#     # Check if all conditions are met for final approval
#     chain = app.get("approvalChain", [])
    
#     # Check if all non-Chief Clerk steps are approved
#     all_non_chief_approved = True
#     for step in chain:
#         if step["role"] != "Chief Clerk" and step["status"] != "approved":
#             all_non_chief_approved = False
#             break
    
#     # Check Chief Clerk has forwarded
#     chief_clerk_step = next((s for s in chain if s["role"] == "Chief Clerk"), None)
#     chief_clerk_forwarded = chief_clerk_step and chief_clerk_step.get("forward_status") == "forwarded"
    
#     if not (all_non_chief_approved and chief_clerk_forwarded):
#         flash("Application is not ready for final approval. All previous steps must be completed.", "error")
#         return redirect(url_for('approver_dashboard.dashboard_main'))

#     if request.method == 'POST':
#         comments = request.form.get('comments', '').strip()
        
#         # ==================== LEAVE BALANCE DEDUCTIONS ====================
#         applicant_id = app.get("applicantId")
#         leave_type = app.get("leave_type")
#         days_requested = app.get("numberOfDays", 0)
        
#         # Get the year from effective date
#         if "effectiveDate" in app:
#             effective_date = app["effectiveDate"]
#             if isinstance(effective_date, datetime):
#                 year = effective_date.year
#             elif isinstance(effective_date, dict) and "$date" in effective_date:
#                 year = datetime.fromisoformat(effective_date["$date"].replace("Z", "+00:00")).year
#             else:
#                 year = datetime.now().year
#         else:
#             year = datetime.now().year
        
#         # Find the leave balance for this staff member
#         balance = leave_balances_coll.find_one({
#             "serviceNumber": applicant_id,
#             "year": year
#         })
        
#         if not balance:
#             flash(f"No leave balance found for {applicant_id} in year {year}. Cannot approve.", "error")
#             return redirect(url_for('approver_dashboard.dashboard_main'))
        
        
#         update_fields = {}
#         success_message = "Application finally approved. Receipt generated."
        
        
#         # ============= FIXED: TACOS DEDUCTIONS BASED ON LEAVE TYPE =============
#         if leave_type == "annual":
#             if balance.get("annualRemaining", 0) < days_requested:
#                 flash(f"Insufficient annual leave balance. Available: {balance.get('annualRemaining', 0)} days, Requested: {days_requested} days", "error")
#                 return redirect(url_for('approver_dashboard.dashboard_main'))
            
#             new_annual = balance.get("annualRemaining", 0) - days_requested
#             update_fields["annualRemaining"] = new_annual
#             success_message += f" {days_requested} days deducted from annual leave."
        
#         elif leave_type == "compassionate":
#             if balance.get("compassionateRemaining", 0) < days_requested:
#                 flash(f"Insufficient compassionate leave balance. Available: {balance.get('compassionateRemaining', 0)} days, Requested: {days_requested} days", "error")
#                 return redirect(url_for('approver_dashboard.dashboard_main'))
            
#             new_compassionate_used = balance.get("compassionateUsed", 0) + days_requested
#             new_compassionate_remaining = balance.get("compassionateRemaining", 0) - days_requested
#             update_fields["compassionateUsed"] = new_compassionate_used
#             update_fields["compassionateRemaining"] = new_compassionate_remaining
#             success_message += f" {days_requested} days deducted from compassionate leave."
        
#         elif leave_type == "casual":
#             # ============ FIXED: CORRECT CASUAL LEAVE DEDUCTION LOGIC ============
#             # Get validation metadata from the application
#             validation = app.get("validation", {})
#             metadata = validation.get("metadata", {})
            
#             # First, check if this was already calculated during validation
#             deduct_from_annual = metadata.get("deduct_from_annual", 0)
            
#             # Calculate calendar days
#             start_date = app.get("effectiveDate")
#             end_date = app.get("endDate")
#             calendar_days = 0
            
#             if isinstance(start_date, datetime) and isinstance(end_date, datetime):
#                 calendar_days = (end_date - start_date).days + 1
#             elif "dates" in app and isinstance(app["dates"], dict):
#                 eff_date = app["dates"].get("effectiveDate")
#                 end_date_field = app["dates"].get("endDate")
#                 if eff_date and end_date_field:
#                     if isinstance(eff_date, datetime) and isinstance(end_date_field, datetime):
#                         calendar_days = (end_date_field - eff_date).days + 1
            
#             current_casual_used = balance.get("casualCalendarDaysUsed", 0)
#             casual_remaining = balance.get("casualCalendarDaysRemaining", 7)
            
#             # Determine free days vs excess days
#             if calendar_days <= casual_remaining:
#                 # CASE 1: FULLY WITHIN CASUAL ALLOWANCE
#                 free_days = calendar_days
#                 excess_days = 0
#                 excess_working = 0
#             else:
#                 # CASE 2: PARTIALLY EXCEEDS CASUAL ALLOWANCE
#                 free_days = casual_remaining
#                 excess_days = calendar_days - casual_remaining
                
#                 # Calculate working days for excess period
#                 if free_days > 0 and isinstance(effective_date, datetime):
#                     free_end_date = effective_date + timedelta(days=free_days - 1)
#                     excess_start_date = free_end_date + timedelta(days=1)
                    
#                     # Get public holidays for calculation
#                     from .leave_helper import get_public_holidays, working_days_between
#                     public_holidays = get_public_holidays(year)
#                     excess_working = working_days_between(excess_start_date, end_date, public_holidays)
#                 else:
#                     # No free days left, entire leave is excess
#                     excess_working = days_requested  # working days
            
#             # Update casual leave usage
#             new_casual_used = current_casual_used + calendar_days
#             update_fields["casualCalendarDaysUsed"] = new_casual_used
#             update_fields["casualCalendarDaysRemaining"] = max(0, 7 - new_casual_used)
            
#             # Deduct excess from annual leave
#             if excess_working > 0:
#                 if balance.get("annualRemaining", 0) < excess_working:
#                     flash(f"Insufficient annual leave for excess casual. Need {excess_working} days, Available: {balance.get('annualRemaining', 0)} days", "error")
#                     return redirect(url_for('approver_dashboard.dashboard_main'))
                
#                 new_annual = balance.get("annualRemaining", 0) - excess_working
#                 update_fields["annualRemaining"] = new_annual
                
#                 success_message += f" {free_days} calendar days casual + {excess_working} working days from annual leave."
#             else:
#                 success_message += f" {calendar_days} calendar days within casual allowance."
        
#         elif leave_type == "sick":
#             # For sick leave, track usage but don't deduct from annual
#             current_sick = balance.get("sickThisYear", 0)
#             new_sick = current_sick + days_requested
            
#             # Update sick leave tracking
#             update_fields["sickThisYear"] = new_sick
#             update_fields["sickThisYearRemaining"] = max(0, 21 - new_sick)
            
#             # Update rolling 12-month sick leave
#             rolling_sick = balance.get("sickRolling12m", 0) + days_requested
#             update_fields["sickRolling12m"] = rolling_sick
#             update_fields["sickRollingRemaining"] = max(0, 42 - rolling_sick)
            
#             success_message += f" {days_requested} days added to sick leave tracking."
            
#             # Check if hospitalized (from tacosDetails)
#             tacos_details = app.get("tacosDetails", {})
#             if tacos_details.get("hospitalized", False):
#                 current_hosp = balance.get("hospitalizationDaysUsed", 0)
#                 update_fields["hospitalizationDaysUsed"] = current_hosp + calendar_days
                
#                 if tacos_details.get("firstHospitalization", False):
#                     update_fields["firstHospitalizationUsed"] = True
        
#         elif leave_type == "maternity":
#             # Maternity is 112 working days block
#             if balance.get("maternityAvailable", True):
#                 update_fields["maternityAvailable"] = False
#                 update_fields["maternityStartDate"] = datetime.utcnow()
#                 success_message += " Maternity leave (112 days) approved."
#             else:
#                 flash("Maternity leave already used.", "error")
#                 return redirect(url_for('approver_dashboard.dashboard_main'))
        
#         elif leave_type == "paternity":
#             # Paternity is 14 working days
#             if balance.get("paternityAvailable", True):
#                 update_fields["paternityAvailable"] = False
#                 update_fields["paternityDaysUsed"] = 14
#                 success_message += " Paternity leave (14 days) approved."
#             else:
#                 flash("Paternity leave already used.", "error")
#                 return redirect(url_for('approver_dashboard.dashboard_main'))
        
#         elif leave_type == "disembarkation":
#             # Disembarkation leave (7 or 14 days based on attachment duration)
#             if balance.get("disembarkationAvailable", True):
#                 tacos_details = app.get("tacosDetails", {})
#                 attachment_months = tacos_details.get("attachmentMonths", 0)
                
#                 if attachment_months > 6:
#                     days_to_deduct = 14
#                 else:
#                     days_to_deduct = 7
                
#                 # Disembarkation typically comes from annual leave
#                 if balance.get("annualRemaining", 0) < days_to_deduct:
#                     flash(f"Insufficient annual leave for disembarkation. Available: {balance.get('annualRemaining', 0)} days, Required: {days_to_deduct} days", "error")
#                     return redirect(url_for('approver_dashboard.dashboard_main'))
                
#                 update_fields["annualRemaining"] = balance.get("annualRemaining", 0) - days_to_deduct
#                 update_fields["disembarkationAvailable"] = False
#                 success_message += f" Disembarkation leave ({days_to_deduct} days) approved and deducted from annual leave."
#             else:
#                 flash("Disembarkation leave already used.", "error")
#                 return redirect(url_for('approver_dashboard.dashboard_main'))
        
#         elif leave_type == "terminal":
#             # Terminal leave - one-time on retirement
#             if balance.get("terminalAvailable", True) and not balance.get("terminalGranted", False):
#                 update_fields["terminalGranted"] = True
#                 update_fields["terminalAvailable"] = False
#                 success_message += " Terminal leave approved."
#             else:
#                 flash("Terminal leave not available or already granted.", "error")
#                 return redirect(url_for('approver_dashboard.dashboard_main'))
        
#         else:
#             flash(f"Unknown leave type: {leave_type}", "error")
#             return redirect(url_for('approver_dashboard.dashboard_main'))
        
#         # Apply balance updates if any
#         if update_fields:
#             update_fields["updatedAt"] = datetime.utcnow()
#             update_fields["notes"] = balance.get("notes", [])
#             update_fields["notes"].append(f"{datetime.utcnow().isoformat()}: Leave issued - {leave_type} - {days_requested} days")
            
#             leave_balances_coll.update_one(
#                 {"_id": balance["_id"]},
#                 {"$set": update_fields}
#             )
        
#         # ==================== FINAL APPROVAL PROCESSING ====================
#         # Generate receipt number
#         receipt_number = f"REC-{datetime.utcnow().strftime('%Y%m%d')}-{app_id[-6:]}"
        
#         # Update final approval
#         final_approval = app.get("finalApproval", {})
#         final_approval.update({
#             "approverId": current_user['service_number'],
#             "approverName": current_user['fullName'],
#             "approverRank": current_user.get('rankOrGrade', ''),
#             "approverDesignation": current_user.get('designation', ''),
#             "status": "approved",
#             "comments": comments or "Final approval granted",
#             "timestamp": datetime.utcnow(),
#             "receipt": {
#                 "receiptNumber": receipt_number,
#                 "issuedDate": datetime.utcnow(),
#                 "pdfUrl": f"/receipts/{receipt_number}.pdf"
#             }
#         })

#         # Update application in database
#         applications_coll.update_one(
#             {"_id": ObjectId(app_id)},
#             {
#                 "$set": {
#                     "finalApproval": final_approval,
#                     "status": "issued",
#                     "updatedAt": datetime.utcnow()
#                 },
#                 "$push": {
#                     "auditTrail": {
#                         "action": "final_approval",
#                         "approver": current_user['service_number'],
#                         "approverName": current_user['fullName'],
#                         "timestamp": datetime.utcnow(),
#                         "comments": comments,
#                         "receiptNumber": receipt_number,
#                         "balance_updates": update_fields
#                     }
#                 }
#             }
#         )

#         # ==================== NOTIFICATION TO APPLICANT ====================
#         notification_doc = {
#             "type": "approved",
#             "applicationId": app["_id"],
#             "referenceId": app.get("referenceId"),
#             "target": {
#                 "type": "user",
#                 "directorate": None,
#                 "role": None,
#                 "userId": applicant_id
#             },
#             "message": f"Your application {app.get('referenceId')} has been approved. Receipt generated.",
#             "status": "unread",
#             "readBy": [],
#             "isActive": True, 
#             "createdAt": datetime.utcnow(),
#             "meta": {"receiptNumber": receipt_number}
#         }
        

#         notifications_coll.insert_one(notification_doc)

#         # Create a JSON-safe copy for Socket.IO
#         socket_payload = {
#             "type": "approved",
#             "applicationId": str(app["_id"]),  # Convert to string
#             "referenceId": app.get("referenceId"),
#             "message": f"Your application {app.get('referenceId')} has been approved. Receipt generated.",
#             "receiptNumber": receipt_number,
#             "timestamp": datetime.utcnow().isoformat(),  # Convert datetime to string
#             "applicantId": applicant_id
#         }

#         socketio.emit(
#             "new_notification",
#             socket_payload,
#             room=f"USER_{applicant_id}"
#         )

#         # ================= EMAIL NOTIFICATION =================
#         staff_coll = current_app.staff_collection

#         try:
#             staff_coll = current_app.staff_collection
#             applicant = staff_coll.find_one({
#                 "_id": applicant_id,
#                 "isActive": True
#             })

#             if applicant and applicant.get("email"):
#                 from utils.email_service import send_final_approval_email
                
#                 send_final_approval_email(
#                     applicant,
#                     app,
#                     receipt_number
#                 )
#             else:
#                 current_app.logger.warning(
#                     f"Applicant email not found for {applicant_id}"
#                 )

#         except Exception as e:
#             current_app.logger.error(
#                 f"Failed to send final approval email: {str(e)}"
#             )
#         flash(success_message, "success")
#         return redirect(url_for('approver_dashboard.dashboard_main'))

#     return redirect(url_for('approver_dashboard.dashboard_main'))

@approver_dashboard.route('/final_approve/<string:app_id>', methods=['GET', 'POST'])
@login_required
def final_approve(app_id):
    current_user = session.get('user')
    
    if not current_user:
        flash("Session expired.", "error")
        return redirect(url_for('auth.login'))

    if "SO1-DOA" not in current_user.get('roles', []):
        flash("You are not authorized for final approval.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    applications_coll = current_app.applications_collection
    leave_balances_coll = current_app.leave_balances
    notifications_coll = current_app.notifications_collection

    try:
        app = applications_coll.find_one({"_id": ObjectId(app_id)})
        if not app:
            flash("Application not found.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))
    except:
        flash("Invalid application ID.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    # Check if application is still pending (not already issued/rejected)
    if app.get("status") != "pending":
        flash(f"Cannot approve: Application is already {app.get('status')}.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    # Check if all conditions are met for final approval
    chain = app.get("approvalChain", [])
    
    # Check if all non-Chief Clerk steps are approved
    all_non_chief_approved = True
    for step in chain:
        if step["role"] != "Chief Clerk" and step["status"] != "approved":
            all_non_chief_approved = False
            break
    
    # Check Chief Clerk has forwarded
    chief_clerk_step = next((s for s in chain if s["role"] == "Chief Clerk"), None)
    chief_clerk_forwarded = chief_clerk_step and chief_clerk_step.get("forward_status") == "forwarded"
    
    if not (all_non_chief_approved and chief_clerk_forwarded):
        flash("Application is not ready for final approval. All previous steps must be completed.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    if request.method == 'POST':
        comments = request.form.get('comments', '').strip()
        
        # ==================== LEAVE BALANCE DEDUCTIONS ====================
        applicant_id = app.get("applicantId")
        leave_type = app.get("leave_type")
        days_requested = app.get("numberOfDays", 0)
        
        # Get the year from effective date
        if "effectiveDate" in app:
            effective_date = app["effectiveDate"]
            if isinstance(effective_date, datetime):
                year = effective_date.year
            elif isinstance(effective_date, dict) and "$date" in effective_date:
                year = datetime.fromisoformat(effective_date["$date"].replace("Z", "+00:00")).year
            else:
                year = datetime.now().year
        else:
            year = datetime.now().year
        
        # Find the leave balance for this staff member
        balance = leave_balances_coll.find_one({
            "serviceNumber": applicant_id,
            "year": year
        })
        
        if not balance:
            flash(f"No leave balance found for {applicant_id} in year {year}. Cannot approve.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))
        
        # ============= 🔥 NEW: CHECK BALANCE SUFFICIENCY AT FINAL APPROVAL =============
        balance_sufficient = True
        insufficient_message = ""
        expected_annual_deduction = 0

        # Get validation metadata for casual leave expected deduction
        validation = app.get("validation", {})
        metadata = validation.get("metadata", {})
        
        if leave_type == "annual":
            if balance.get("annualRemaining", 0) < days_requested:
                balance_sufficient = False
                insufficient_message = f"Insufficient annual leave. Available: {balance.get('annualRemaining', 0)} days, Requested: {days_requested} days"

        elif leave_type == "casual":
            expected_annual_deduction = metadata.get("deduct_from_annual", 0)
            if expected_annual_deduction > 0:
                if balance.get("annualRemaining", 0) < expected_annual_deduction:
                    balance_sufficient = False
                    insufficient_message = f"Insufficient annual leave for excess casual. Need {expected_annual_deduction} days from annual leave, Available: {balance.get('annualRemaining', 0)} days"

        elif leave_type == "compassionate":
            if balance.get("compassionateRemaining", 0) < days_requested:
                balance_sufficient = False
                insufficient_message = f"Insufficient compassionate leave. Available: {balance.get('compassionateRemaining', 0)} days, Requested: {days_requested} days"

        elif leave_type == "disembarkation":
            tacos_details = app.get("tacosDetails", {})
            attachment_months = tacos_details.get("attachmentMonths", 0)
            required_days = 14 if attachment_months > 6 else 7
            
            if balance.get("annualRemaining", 0) < required_days:
                balance_sufficient = False
                insufficient_message = f"Insufficient annual leave for disembarkation. Need {required_days} days, Available: {balance.get('annualRemaining', 0)} days"

        # 🔥 AUTO-REJECT IF INSUFFICIENT
        if not balance_sufficient:
            flash(f"❌ {insufficient_message}. Application has been rejected.", "error")
            
            # Update application as rejected
            applications_coll.update_one(
                {"_id": ObjectId(app_id)},
                {
                    "$set": {
                        "status": "rejected",
                        "finalApproval.status": "rejected",
                        "finalApproval.comments": f"Auto-rejected: {insufficient_message}",
                        "updatedAt": datetime.utcnow()
                    },
                    "$push": {
                        "auditTrail": {
                            "action": "auto_rejected",
                            "reason": insufficient_message,
                            "timestamp": datetime.utcnow(),
                            "approver": "System"
                        }
                    }
                }
            )
            
            # Notify applicant
            notification_doc = {
                "type": "rejected",
                "applicationId": app["_id"],
                "referenceId": app.get("referenceId"),
                "target": {
                    "type": "user",
                    "directorate": None,
                    "role": None,
                    "userId": applicant_id
                },
                "message": f"Your application {app.get('referenceId')} was rejected due to insufficient leave balance.",
                "status": "unread",
                "readBy": [],
                "isActive": True,
                "createdAt": datetime.utcnow(),
                "meta": {"reason": insufficient_message}
            }
            notifications_coll.insert_one(notification_doc)
            
            # Socket notification
            socket_payload = {
                "type": "rejected",
                "applicationId": str(app["_id"]),
                "referenceId": app.get("referenceId"),
                "message": f"Your application was rejected: {insufficient_message}",
                "timestamp": datetime.utcnow().isoformat()
            }
            socketio.emit("new_notification", socket_payload, room=f"USER_{applicant_id.replace('/', '_')}")
            
            return redirect(url_for('approver_dashboard.dashboard_main'))

        # ============= CONTINUE WITH NORMAL APPROVAL PROCESS =============
        update_fields = {}
        success_message = "Application finally approved. Receipt generated."
        
        # TACOS DEDUCTIONS BASED ON LEAVE TYPE
        if leave_type == "annual":
            if balance.get("annualRemaining", 0) < days_requested:
                flash(f"Insufficient annual leave balance. Available: {balance.get('annualRemaining', 0)} days, Requested: {days_requested} days", "error")
                return redirect(url_for('approver_dashboard.dashboard_main'))
            
            new_annual = balance.get("annualRemaining", 0) - days_requested
            update_fields["annualRemaining"] = new_annual
            success_message += f" {days_requested} days deducted from annual leave."
        
        elif leave_type == "compassionate":
            if balance.get("compassionateRemaining", 0) < days_requested:
                flash(f"Insufficient compassionate leave balance. Available: {balance.get('compassionateRemaining', 0)} days, Requested: {days_requested} days", "error")
                return redirect(url_for('approver_dashboard.dashboard_main'))
            
            new_compassionate_used = balance.get("compassionateUsed", 0) + days_requested
            new_compassionate_remaining = balance.get("compassionateRemaining", 0) - days_requested
            update_fields["compassionateUsed"] = new_compassionate_used
            update_fields["compassionateRemaining"] = new_compassionate_remaining
            success_message += f" {days_requested} days deducted from compassionate leave."
        
        elif leave_type == "casual":
            # Get validation metadata from the application
            validation = app.get("validation", {})
            metadata = validation.get("metadata", {})
            
            # First, check if this was already calculated during validation
            deduct_from_annual = metadata.get("deduct_from_annual", 0)
            
            # Calculate calendar days
            start_date = app.get("effectiveDate")
            end_date = app.get("endDate")
            calendar_days = 0
            
            if isinstance(start_date, datetime) and isinstance(end_date, datetime):
                calendar_days = (end_date - start_date).days + 1
            elif "dates" in app and isinstance(app["dates"], dict):
                eff_date = app["dates"].get("effectiveDate")
                end_date_field = app["dates"].get("endDate")
                if eff_date and end_date_field:
                    if isinstance(eff_date, datetime) and isinstance(end_date_field, datetime):
                        calendar_days = (end_date_field - eff_date).days + 1
            
            current_casual_used = balance.get("casualCalendarDaysUsed", 0)
            casual_remaining = balance.get("casualCalendarDaysRemaining", 7)
            
            # Determine free days vs excess days
            if calendar_days <= casual_remaining:
                # CASE 1: FULLY WITHIN CASUAL ALLOWANCE
                free_days = calendar_days
                excess_days = 0
                excess_working = 0
            else:
                # CASE 2: PARTIALLY EXCEEDS CASUAL ALLOWANCE
                free_days = casual_remaining
                excess_days = calendar_days - casual_remaining
                
                # Calculate working days for excess period
                if free_days > 0 and isinstance(effective_date, datetime):
                    free_end_date = effective_date + timedelta(days=free_days - 1)
                    excess_start_date = free_end_date + timedelta(days=1)
                    
                    # Get public holidays for calculation
                    from .leave_helper import get_public_holidays, working_days_between
                    public_holidays = get_public_holidays(year)
                    excess_working = working_days_between(excess_start_date, end_date, public_holidays)
                else:
                    # No free days left, entire leave is excess
                    excess_working = days_requested
            
            # Update casual leave usage
            new_casual_used = current_casual_used + calendar_days
            update_fields["casualCalendarDaysUsed"] = new_casual_used
            update_fields["casualCalendarDaysRemaining"] = max(0, 7 - new_casual_used)
            
            # Deduct excess from annual leave
            if excess_working > 0:
                if balance.get("annualRemaining", 0) < excess_working:
                    flash(f"Insufficient annual leave for excess casual. Need {excess_working} days, Available: {balance.get('annualRemaining', 0)} days", "error")
                    return redirect(url_for('approver_dashboard.dashboard_main'))
                
                new_annual = balance.get("annualRemaining", 0) - excess_working
                update_fields["annualRemaining"] = new_annual
                
                success_message += f" {free_days} calendar days casual + {excess_working} working days from annual leave."
            else:
                success_message += f" {calendar_days} calendar days within casual allowance."
        
        elif leave_type == "sick":
            # For sick leave, track usage but don't deduct from annual
            current_sick = balance.get("sickThisYear", 0)
            new_sick = current_sick + days_requested
            
            # Update sick leave tracking
            update_fields["sickThisYear"] = new_sick
            update_fields["sickThisYearRemaining"] = max(0, 21 - new_sick)
            
            # Update rolling 12-month sick leave
            rolling_sick = balance.get("sickRolling12m", 0) + days_requested
            update_fields["sickRolling12m"] = rolling_sick
            update_fields["sickRollingRemaining"] = max(0, 42 - rolling_sick)
            
            success_message += f" {days_requested} days added to sick leave tracking."
            
            # Check if hospitalized (from tacosDetails)
            tacos_details = app.get("tacosDetails", {})
            if tacos_details.get("hospitalized", False):
                current_hosp = balance.get("hospitalizationDaysUsed", 0)
                update_fields["hospitalizationDaysUsed"] = current_hosp + calendar_days
                
                if tacos_details.get("firstHospitalization", False):
                    update_fields["firstHospitalizationUsed"] = True
        
        elif leave_type == "maternity":
            # Maternity is 112 working days block
            if balance.get("maternityAvailable", True):
                update_fields["maternityAvailable"] = False
                update_fields["maternityStartDate"] = datetime.utcnow()
                success_message += " Maternity leave (112 days) approved."
            else:
                flash("Maternity leave already used.", "error")
                return redirect(url_for('approver_dashboard.dashboard_main'))
        
        elif leave_type == "paternity":
            # Paternity is 14 working days
            if balance.get("paternityAvailable", True):
                update_fields["paternityAvailable"] = False
                update_fields["paternityDaysUsed"] = 14
                success_message += " Paternity leave (14 days) approved."
            else:
                flash("Paternity leave already used.", "error")
                return redirect(url_for('approver_dashboard.dashboard_main'))
        
        elif leave_type == "disembarkation":
            # Disembarkation leave (7 or 14 days based on attachment duration)
            if balance.get("disembarkationAvailable", True):
                tacos_details = app.get("tacosDetails", {})
                attachment_months = tacos_details.get("attachmentMonths", 0)
                
                if attachment_months > 6:
                    days_to_deduct = 14
                else:
                    days_to_deduct = 7
                
                # Disembarkation typically comes from annual leave
                if balance.get("annualRemaining", 0) < days_to_deduct:
                    flash(f"Insufficient annual leave for disembarkation. Available: {balance.get('annualRemaining', 0)} days, Required: {days_to_deduct} days", "error")
                    return redirect(url_for('approver_dashboard.dashboard_main'))
                
                update_fields["annualRemaining"] = balance.get("annualRemaining", 0) - days_to_deduct
                update_fields["disembarkationAvailable"] = False
                success_message += f" Disembarkation leave ({days_to_deduct} days) approved and deducted from annual leave."
            else:
                flash("Disembarkation leave already used.", "error")
                return redirect(url_for('approver_dashboard.dashboard_main'))
        
        elif leave_type == "terminal":
            # Terminal leave - one-time on retirement
            if balance.get("terminalAvailable", True) and not balance.get("terminalGranted", False):
                update_fields["terminalGranted"] = True
                update_fields["terminalAvailable"] = False
                success_message += " Terminal leave approved."
            else:
                flash("Terminal leave not available or already granted.", "error")
                return redirect(url_for('approver_dashboard.dashboard_main'))
        
        else:
            flash(f"Unknown leave type: {leave_type}", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))
        
        # Apply balance updates if any
        if update_fields:
            update_fields["updatedAt"] = datetime.utcnow()
            update_fields["notes"] = balance.get("notes", [])
            update_fields["notes"].append(f"{datetime.utcnow().isoformat()}: Leave issued - {leave_type} - {days_requested} days")
            
            leave_balances_coll.update_one(
                {"_id": balance["_id"]},
                {"$set": update_fields}
            )
        
        # ==================== FINAL APPROVAL PROCESSING ====================
        # Generate receipt number
        receipt_number = f"REC-{datetime.utcnow().strftime('%Y%m%d')}-{app_id[-6:]}"
        
        # Update final approval
        final_approval = app.get("finalApproval", {})
        final_approval.update({
            "approverId": current_user['service_number'],
            "approverName": current_user['fullName'],
            "approverRank": current_user.get('rankOrGrade', ''),
            "approverDesignation": current_user.get('designation', ''),
            "status": "approved",
            "comments": comments or "Final approval granted",
            "timestamp": datetime.utcnow(),
            "receipt": {
                "receiptNumber": receipt_number,
                "issuedDate": datetime.utcnow(),
                "pdfUrl": f"/receipts/{receipt_number}.pdf"
            }
        })

        # Update application in database
        applications_coll.update_one(
            {"_id": ObjectId(app_id)},
            {
                "$set": {
                    "finalApproval": final_approval,
                    "status": "issued",
                    "updatedAt": datetime.utcnow()
                },
                "$push": {
                    "auditTrail": {
                        "action": "final_approval",
                        "approver": current_user['service_number'],
                        "approverName": current_user['fullName'],
                        "timestamp": datetime.utcnow(),
                        "comments": comments,
                        "receiptNumber": receipt_number,
                        "balance_updates": update_fields
                    }
                }
            }
        )

        # ==================== NOTIFICATION TO APPLICANT ====================
        notification_doc = {
            "type": "approved",
            "applicationId": app["_id"],
            "referenceId": app.get("referenceId"),
            "target": {
                "type": "user",
                "directorate": None,
                "role": None,
                "userId": applicant_id
            },
            "message": f"Your application {app.get('referenceId')} has been approved. Receipt generated.",
            "status": "unread",
            "readBy": [],
            "isActive": True, 
            "createdAt": datetime.utcnow(),
            "meta": {"receiptNumber": receipt_number}
        }
        
        notifications_coll.insert_one(notification_doc)

        # Create a JSON-safe copy for Socket.IO
        socket_payload = {
            "type": "approved",
            "applicationId": str(app["_id"]),
            "referenceId": app.get("referenceId"),
            "message": f"Your application {app.get('referenceId')} has been approved. Receipt generated.",
            "receiptNumber": receipt_number,
            "timestamp": datetime.utcnow().isoformat(),
            "applicantId": applicant_id
        }

        socketio.emit(
            "new_notification",
            socket_payload,
            room=f"USER_{applicant_id.replace('/', '_')}"
        )

        # ================= EMAIL NOTIFICATION =================
        staff_coll = current_app.staff_collection

        try:
            applicant = staff_coll.find_one({
                "service_number": applicant_id,
                "isActive": True
            })

            if applicant and applicant.get("email"):
                from utils.email_service import send_final_approval_email
                
                send_final_approval_email(
                    applicant,
                    app,
                    receipt_number
                )
            else:
                current_app.logger.warning(
                    f"Applicant email not found for {applicant_id}"
                )

        except Exception as e:
            current_app.logger.error(
                f"Failed to send final approval email: {str(e)}"
            )
            
        flash(success_message, "success")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    return redirect(url_for('approver_dashboard.dashboard_main'))



@approver_dashboard.route('/final-reject/<string:app_id>', methods=['GET', 'POST'])
@login_required
def final_reject(app_id):
    """Final rejection by SO1-DOA"""
    current_user = session.get('user')
    if not current_user:
        flash("Session expired.", "error")
        return redirect(url_for('auth.login'))
        
    if "SO1-DOA" not in current_user.get('roles', []):
        flash("You are not authorized to perform final rejection.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    applications_coll = current_app.applications_collection
    # leave_balances_coll = current_app.leave_balances

    try:
        app = applications_coll.find_one({"_id": ObjectId(app_id)})
        if not app:
            flash("Application not found.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))
    except:
        flash("Invalid application ID.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    # Check if application is still pending (not already issued/rejected)
    if app.get("status") != "pending":
        flash(f"Cannot reject: Application is already {app.get('status')}.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    if app.get("finalApproval", {}).get("status") != "pending":
        flash("This application is not awaiting final approval.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    if request.method == 'POST':
        comments = request.form.get('comments', '').strip()
        if not comments:
            flash("Comments are required for final rejection.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))

        # ============ ADD REFUND FUNCTION ============
        # Check if balance was already deducted (status would be 'issued')
        if app.get("status") == "issued":
            # Refund the leave balance
            try:
                from .leave_helper import refund_leave_balance
                refund_success = refund_leave_balance(
                    service_number=app.get("applicantId"),
                    application=app
                )
                if refund_success:
                    print(f"✓ Leave balance refunded for {app.get('applicantId')}")
                else:
                    print(f"⚠️ Failed to refund leave balance for {app.get('applicantId')}")
            except Exception as e:
                print(f"ERROR refunding leave balance: {e}")
        # =============================================

        # Update final approval
        final_approval = app.get("finalApproval", {})
        final_approval.update({
            "approverId": current_user['service_number'],
            "approverName": current_user['fullName'],
            "approverRank": current_user.get('rankOrGrade', ''),
            "approverDesignation": current_user.get('designation', ''),
            "status": "rejected",
            "comments": comments,
            "timestamp": datetime.utcnow()
        })

        # Update application in database
        applications_coll.update_one(
            {"_id": ObjectId(app_id)},
            {
                "$set": {
                    "finalApproval": final_approval,
                    "status": "rejected",
                    "updatedAt": datetime.utcnow()
                }
            }
        )

        # TRIGGER REJECTION NOTIFICATION EMAIL TO APPLICANT 
        staff_coll = current_app.staff_collection

        applicant = staff_coll.find_one(
            {"service_number": app.get("applicantId")}
        )

        if applicant and applicant.get("email"):
            try:
                from utils.email_service import send_rejection_email
                send_rejection_email(
                    applicant_email=applicant["email"],
                    applicant_name=applicant.get("fullName"),
                    application=app,
                    rejected_by=current_user.get("fullName"),
                    comments=comments
                )
            except Exception as e:
                print("Email sending failed:", e)

        # Emit Socket.IO notification to applicant room
        try:
            current_app.socketio.emit(
                "application_update",
                {"status": "rejected", "comments": comments, "referenceId": app.get("referenceId")},
                room=f"APPLICATION_{app.get('referenceId')}"
            )
        except Exception as e:
            print(f"Socket.IO emit failed: {e}")
        
        flash("Application finally rejected. Leave balance refunded if previously deducted.", "info")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    return redirect(url_for('approver_dashboard.dashboard_main'))




@approver_dashboard.route('/view/<string:app_id>')
@login_required
def view_application(app_id):

    current_user = session.get('user')
    if not current_user:
        flash("Session expired.", "error")
        return redirect(url_for('auth.login'))

    # Fetch the application
    app = current_app.applications_collection.find_one({"_id": ObjectId(app_id)})
    if not app:
        flash("Application not found", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))

    # Get applicant name
    applicant = current_app.staff_collection.find_one(
        {"service_number": app["applicantId"]},
        {"fullName": 1}
    )
    app['applicantName'] = applicant['fullName'] if applicant else "Unknown"

    # Simple date formatter
    def format_date(date_field):
        if not date_field:
            return None
        
        # If it's a MongoDB date object
        if isinstance(date_field, dict) and '$date' in date_field:
            try:
                # Extract ISO string and convert to datetime
                iso_str = date_field['$date']
                # Handle Z timezone
                if iso_str.endswith('Z'):
                    iso_str = iso_str[:-1] + '+00:00'
                dt = datetime.fromisoformat(iso_str)
                return dt.strftime('%d %b %Y')
            except:
                return str(date_field)
        
        # If it's already a datetime
        if isinstance(date_field, datetime):
            return date_field.strftime('%d %b %Y')
        
        # If it's a string
        if isinstance(date_field, str):
            return date_field
        
        return str(date_field)


    # Format main dates
    app['startDate'] = format_date(app.get('startDate'))
    app['endDate'] = format_date(app.get('endDate'))
    app['effectiveDate'] = format_date(app.get('effectiveDate'))
    app['createdAt'] = format_date(app.get('createdAt'))

    return render_template('application_detail.html', application=app, user=current_user)



# serve/download the attachment
@approver_dashboard.route('/attachment/<attachment_id>')
def serve_attachment(attachment_id):
    try:
        fs = current_app.fs
        file = fs.get(ObjectId(attachment_id))
        return send_file(
            file,
            download_name=file.filename,
            mimetype=file.content_type,
            as_attachment=False   # or True to force download
        )
    except Exception:
        flash("Attachment not found or access denied.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))




@approver_dashboard.route('/applicant-previous-leaves', methods=['GET'])
@login_required
def applicant_history():
    try:
        applicant_id = request.args.get('applicant_id')
        if not applicant_id:
            return jsonify({"success": False, "error": "No applicant ID provided"}), 400
            
        print(f"Searching for applicantId: '{applicant_id}'")  # Debug log
        
        six_months_ago = datetime.utcnow() - timedelta(days=180)
        
        # Query the database
        apps_cursor = current_app.applications_collection.find({
            "applicantId": applicant_id,
            "status": {"$in": ["approved", "issued", "rejected"]},
            "createdAt": {"$gte": six_months_ago}
        }).sort("createdAt", -1).limit(12)
        
        apps = list(apps_cursor)
        print(f"Found {len(apps)} applications")  # Debug log
        
        applications = []
        for app in apps:
            dates = app.get("dates", {})
            
            # Handle finalApproval field - convert datetime objects to strings for JSON
            final_approval = app.get("finalApproval", {})
            if final_approval:
                # Convert timestamp if it exists
                if final_approval.get("timestamp"):
                    if hasattr(final_approval["timestamp"], 'strftime'):
                        final_approval["timestamp"] = final_approval["timestamp"].strftime('%d %b %Y %H:%M:%S')
                
                # Convert receipt issuedDate if it exists
                if final_approval.get("receipt") and final_approval["receipt"].get("issuedDate"):
                    issued_date = final_approval["receipt"]["issuedDate"]
                    if hasattr(issued_date, 'strftime'):
                        final_approval["receipt"]["issuedDate"] = issued_date.strftime('%d %b %Y')
            
            applications.append({
                "referenceId": app.get("referenceId", "N/A"),  # ADD THIS
                "leave_type": app.get("leave_type", "Unknown"),
                "status": app.get("status"),
                "dates": {
                    "effectiveDate": dates.get("effectiveDate").strftime('%d %b %Y') 
                        if dates.get("effectiveDate") else None,
                    "endDate": dates.get("endDate").strftime('%d %b %Y') 
                        if dates.get("endDate") else None
                },
                "numberOfDays": app.get("numberOfDays"),
                "createdAt": app.get("createdAt").strftime('%d %b %Y') 
                    if app.get("createdAt") else None,
                "reason": app.get("reason"),
                "approvalChain": app.get("approvalChain", []),
                "finalApproval": final_approval  # ADD THIS - CRITICAL FOR SO1-DOA
            })
        
        return jsonify({
            "success": True,
            "applications": applications
        })
        
    except Exception as e:
        print(f"Error in applicant_history for ID {applicant_id}:", str(e))
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@approver_dashboard.route('/view_receipt/<string:app_id>')
@login_required
def view_receipt(app_id):
    """Display receipt HTML page"""
    try:
        applications_coll = current_app.applications_collection
        app = applications_coll.find_one({"_id": ObjectId(app_id)})
        if not app:
            flash("Application not found.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))
        
        # Check if user has permission to view this receipt
        current_user = session.get('user')
        user_roles = current_user.get('roles', [])
        user_id = current_user.get('service_number')
        
        has_permission = False
        
        # Chief Clerk can view if they were involved
        if "Chief Clerk" in user_roles:
            for step in app.get('approvalChain', []):
                if step['role'] == 'Chief Clerk' and step['approverId'] == user_id:
                    has_permission = True
                    break
        
        # SO1-DOA can view any receipt
        if "SO1-DOA" in user_roles:
            has_permission = True
        
        # Applicant can view their own receipt
        if app['applicantId'] == user_id:
            has_permission = True
        
        if not has_permission:
            flash("You are not authorized to view this receipt.", "error")
            return redirect(url_for('approver_dashboard.dashboard_main'))
        
        return render_template('receipt.html', app=app, user=current_user)
        
    except Exception as e:
        print(f"Error viewing receipt: {e}")
        flash("Error viewing receipt.", "error")
        return redirect(url_for('approver_dashboard.dashboard_main'))




@approver_dashboard.route('/download_receipt/<string:app_id>')
def download_receipt(app_id):
    """Download receipt as PDF - no permission check"""
    try:
        applications_coll = current_app.applications_collection
        app = applications_coll.find_one({"_id": ObjectId(app_id)})
        
        if not app:
            # Return a simple error response instead of redirecting
            return "Application not found.", 404
        
        # Check if application is issued and has receipt
        if app.get('status') != 'issued':
            return "Receipt not available - application not issued.", 404
        
        if not app.get('finalApproval') or not app['finalApproval'].get('receipt'):
            return "Receipt not available.", 404
        
        # Generate PDF
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # Add content to PDF
        c.setFont("Helvetica-Bold", 16)
        c.drawString(100, height - 100, "LEAVE APPROVAL RECEIPT - DSA")
        
        c.setFont("Helvetica", 12)
        
        # Get dates - handle different date formats
        start_date = app.get('startDate') or app.get('dates', {}).get('applicationDate')
        end_date = app.get('endDate') or app.get('dates', {}).get('endDate')
        effective_date = app.get('effectiveDate') or app.get('dates', {}).get('effectiveDate')
        
        # Format dates
        def format_date(date_value):
            if isinstance(date_value, datetime):
                return date_value.strftime('%d-%b-%Y')
            elif isinstance(date_value, dict) and '$date' in date_value:
                # MongoDB date format
                from datetime import datetime as dt
                date_obj = dt.fromisoformat(date_value['$date'].replace('Z', '+00:00'))
                return date_obj.strftime('%d-%b-%Y')
            elif isinstance(date_value, str):
                try:
                    date_obj = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                    return date_obj.strftime('%d-%b-%Y')
                except:
                    return str(date_value)
            return 'N/A'
        
        # Format time
        def format_time(date_value):
            if isinstance(date_value, datetime):
                return date_value.strftime('%d-%b-%Y %H:%M')
            elif isinstance(date_value, dict) and '$date' in date_value:
                date_obj = datetime.fromisoformat(date_value['$date'].replace('Z', '+00:00'))
                return date_obj.strftime('%d-%b-%Y %H:%M')
            return 'N/A'
        
        # Get receipt details
        receipt_number = app['finalApproval']['receipt'].get('receiptNumber', 'N/A')
        reference_id = app.get('referenceId', 'N/A')
        applicant_name = app.get('applicantName', 'N/A')
        service_no = app.get('applicantId', 'N/A')
        leave_type = app.get('leave_type', 'N/A').title()
        directorate = app.get('directorate', 'N/A')
        number_of_days = app.get('numberOfDays', 'N/A')
        approver_name = app['finalApproval'].get('approverName', 'N/A')
        approval_date = app['finalApproval'].get('timestamp')
        comments = app['finalApproval'].get('comments', 'Final approval granted')
        
        details = [
            f"Receipt No: {receipt_number}",
            f"Reference ID: {reference_id}",
            "",
            f"Applicant: {applicant_name}",
            f"Service No: {service_no}",
            f"Leave Type: {leave_type}",
            f"Directorate: {directorate}",
            "",
            f"Application Date: {format_date(start_date)}",
            f"Effective Date: {format_date(effective_date)}",
            f"End Date: {format_date(end_date)}",
            f"Working Days: {number_of_days}",
            "",
            f"Final Approved By: {approver_name}",
            f"Approver Role: SO1-DOA",
            f"Approval Date: {format_time(approval_date)}",
            f"Comments: {comments}",
            "",
            "---",
            "This receipt confirms that the leave application has been",
            "officially approved and processed by the Directorate of",
            "Administration (DOA).",
            "",
            "Please present this receipt when required.",
        ]
        
        y = height - 150
        for line in details:
            c.drawString(50, y, line)
            y -= 20
        
        # Add official stamp/watermark
        c.setFont("Helvetica-Bold", 80)
        c.setFillColorRGB(0.9, 0.9, 0.9)  # Light gray
        c.saveState()
        c.translate(500, 500)
        c.rotate(45)
        c.drawString(-300, 0, "APPROVED")
        c.restoreState()
        
        c.save()
        
        buffer.seek(0)
        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        filename = f"receipt_{reference_id}.pdf"
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        print(f"Error downloading receipt: {e}")
        # Return error message instead of redirecting
        return f"Error generating receipt: {str(e)}", 500




@approver_dashboard.route('/email_receipt_self/<string:app_id>')
@login_required
def email_receipt_self(app_id):
    """Email receipt to the current user"""
    try:
        current_user = session.get('user')
        applications_coll = current_app.applications_collection
        app = applications_coll.find_one({"_id": ObjectId(app_id)})
        
        if not app:
            return jsonify({'success': False, 'message': 'Application not found'}), 404
        
        # Check if user is Chief Clerk involved in this application
        user_involved = False
        if "Chief Clerk" in current_user.get('roles', []):
            for step in app.get('approvalChain', []):
                if step['role'] == 'Chief Clerk' and step['approverId'] == current_user['service_number']:
                    user_involved = True
                    break
        
        if not user_involved and "SO1-DOA" not in current_user.get('roles', []):
            return jsonify({'success': False, 'message': 'Not authorized'}), 403
        
        # Send email
        if current_user.get('email'):
            send_chief_clerk_receipt_notification(
                current_user['email'],
                current_user['fullName'],
                app['finalApproval']['receipt']['receiptNumber'],
                app_id,
                app,
                current_user
            )
            return jsonify({'success': True, 'message': 'Receipt sent to your email'})
        else:
            return jsonify({'success': False, 'message': 'Email not found in your profile'}), 400
            
    except Exception as e:
        print(f"Error emailing receipt: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import os
from threading import Thread

def send_chief_clerk_receipt_notification(chief_clerk_email, chief_clerk_name, receipt_no, app_id, app, so1_doa_user):
    """
    Send immediate receipt notification to Chief Clerk
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = app.config['MAIL_USERNAME']
        msg['To'] = chief_clerk_email
        msg['Subject'] = f"🚨 FINAL APPROVAL RECEIPT - {receipt_no}"
        
        # Create email body with all details
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd;">
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                    <h2 style="color: #2c3e50; margin: 0;">📋 FINAL APPROVAL CONFIRMATION</h2>
                    <p style="color: #666; margin: 5px 0;">DSA Pass/Leave System - Official Receipt</p>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <div style="background-color: #e8f5e9; padding: 15px; border-radius: 5px; border-left: 4px solid #4caf50;">
                        <h3 style="color: #2e7d32; margin: 0 0 10px 0;">
                            ✅ Application FINALLY APPROVED by SO1-DOA
                        </h3>
                        <p style="margin: 0;">
                            <strong>Receipt Number:</strong> {receipt_no}<br>
                            <strong>Status:</strong> <span style="color: #4caf50; font-weight: bold;">ISSUED</span>
                        </p>
                    </div>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <h3 style="color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px;">
                        📄 Application Details
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Application ID:</strong></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">{app_id}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Applicant:</strong></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">{app['applicantName']} ({app['applicantId']})</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Type:</strong></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">{app['type'].title()}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Directorate:</strong></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">{app['directorate']}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Period:</strong></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">
                                {app['details']['startDate'].strftime('%d-%b-%Y')} to {app['details']['endDate'].strftime('%d-%b-%Y')}
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Days:</strong></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">{app['details']['numberOfDays']} days</td>
                        </tr>
                    </table>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <h3 style="color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px;">
                        👤 Approval Details
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Final Approved By:</strong></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">{so1_doa_user['fullName']}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Designation:</strong></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">{so1_doa_user.get('designation', 'SO1-DOA')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Approval Date & Time:</strong></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">{datetime.utcnow().strftime('%d-%b-%Y %H:%M UTC')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px;"><strong>Your Action:</strong></td>
                            <td style="padding: 8px;">
                                You forwarded this application on: 
                                {app['approvalChain'][-1].get('forwardedAt', '').strftime('%d-%b-%Y %H:%M') if isinstance(app['approvalChain'][-1].get('forwardedAt'), datetime.datetime) else 'N/A'}
                            </td>
                        </tr>
                    </table>
                </div>
                
                <div style="background-color: #f1f8ff; padding: 15px; border-radius: 5px; border-left: 4px solid #2196f3;">
                    <h4 style="color: #1565c0; margin: 0 0 10px 0;">📋 Administrative Action Required:</h4>
                    <ul style="margin: 0; padding-left: 20px;">
                        <li>File this receipt in official records</li>
                        <li>Update physical register if applicable</li>
                        <li>Notify relevant administrative staff</li>
                        <li>Process any associated paperwork</li>
                    </ul>
                </div>
                
                <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; color: #666;">
                    <p style="margin: 5px 0;">
                        <strong>Access in System:</strong> 
                        <a href="{request.host_url}dashboard_main" style="color: #2196f3;">
                            Go to Dashboard
                        </a>
                    </p>
                    <p style="margin: 5px 0; font-size: 12px;">
                        This is an auto-generated receipt. Valid only with official stamp.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Send email
        server = smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT'])
        server.starttls()
        server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        server.sendmail(app.config['MAIL_USERNAME'], chief_clerk_email, msg.as_string())
        server.quit()
        
        print(f"✓ Receipt sent to Chief Clerk: {chief_clerk_email}")
        return True
        
    except Exception as e:
        print(f"✗ Error sending to Chief Clerk {chief_clerk_email}: {e}")
        return False

def send_applicant_receipt_notification(applicant_email, applicant_name, receipt_no, app_id, app, so1_doa_user):
    """
    Send receipt notification to applicant
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = app.config['MAIL_USERNAME']
        msg['To'] = applicant_email
        msg['Subject'] = f"✅ Your {app['type'].title()} Approved - {receipt_no}"
        
        body = f"""
        Dear {applicant_name},
        
        GOOD NEWS! Your {app['type']} application has been **FINAL APPROVED**.
        
        📋 APPROVAL DETAILS:
        • Receipt Number: {receipt_no}
        • Application ID: {app_id}
        • Type: {app['type'].title()}
        • Directorate: {app['directorate']}
        • Period: {app['details']['startDate'].strftime('%d-%b-%Y')} to {app['details']['endDate'].strftime('%d-%b-%Y')}
        • Days: {app['details']['numberOfDays']}
        • Approved By: {so1_doa_user['fullName']} (SO1-DOA)
        • Approval Date: {datetime.utcnow().strftime('%d-%b-%Y %H:%M UTC')}
        
        This receipt serves as official confirmation. Please:
        1. Keep this email for your records
        2. Present it if required for verification
        3. Download the receipt from the application portal
        
        You can access your receipt here: {request.host_url}view_receipt/{app_id}
        
        Regards,
        DSA Pass/Leave System
        Directorate of Space Administration
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT'])
        server.starttls()
        server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        server.sendmail(app.config['MAIL_USERNAME'], applicant_email, msg.as_string())
        server.quit()
        
        print(f"✓ Receipt sent to Applicant: {applicant_email}")
        return True
        
    except Exception as e:
        print(f"✗ Error sending to Applicant {applicant_email}: {e}")
        return False