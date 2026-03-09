from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from bson import ObjectId
from datetime import datetime




application_track = Blueprint('application_track', __name__)



@application_track.route('/track_application', methods=['GET', 'POST'])
def track_application():
    """Public tracking page (no login required)"""
    reference_id = request.form.get('reference_id') or request.args.get('reference_id')
    
    if not reference_id:
        return render_template('track_application.html', error="Please enter a Reference ID.")
    
    try:
        # Look up the application
        app = current_app.applications_collection.find_one({"referenceId": reference_id})
        
        if not app:
            return render_template('track_result.html',
                                   error="Application not found. Please check your Reference ID.",
                                   reference_id=reference_id)
        
        # Determine applicant type
        applicant_id = app.get("applicantId")
        is_civilian = False
        if applicant_id:
            staff_member = current_app.staff_collection.find_one({"_id": applicant_id})
            if staff_member:
                is_civilian = staff_member.get("type") == "civilian"
            else:
                is_civilian = "CIV" in applicant_id.upper() or applicant_id.startswith("DSA/CIV")
        
        # Approval chain
        approval_chain = app.get("approvalChain", [])
        final_approval = app.get("finalApproval", {})
        final_status = final_approval.get("status", "pending")
        
        # ==================== TIMELINE CALCULATION ====================
        timeline = []
        
        # Step 1: Application Submitted
        timeline.append({
            "title": "Step 1: Application Submitted",
            "date": app.get("createdAt"),
            "description": f"Reference ID: {reference_id}",
            "status": "completed",
            "icon": "ri-send-plane-line",
            "step_number": 1
        })
        
        # Define steps based on applicant type
        if is_civilian:
            approval_steps = ["Civilian Officer", "SSO", "Deputy_Director", "Director"]
            final_step_number = 6
        else:
            approval_steps = ["SSO", "Deputy_Director", "Director"]
            final_step_number = 5
        
        found_current = False
        
        for idx, role in enumerate(approval_steps, start=2):
            step = next((s for s in approval_chain if s.get("role") == role), None)
            if step:
                status = step.get("status", "pending")
                step_date = step.get("timestamp")
                desc = step.get("comments") or step.get("approverName") or "Waiting for approval"
                
                if status == "approved":
                    timeline.append({
                        "title": f"Step {idx}: Approved by {role.replace('_', ' ')}",
                        "date": step_date,
                        "description": desc,
                        "status": "completed",
                        "icon": "ri-check-line",
                        "step_number": idx
                    })
                elif status == "rejected":
                    timeline.append({
                        "title": f"Step {idx}: Rejected by {role.replace('_', ' ')}",
                        "date": step_date,
                        "description": desc,
                        "status": "rejected",
                        "icon": "ri-close-line",
                        "step_number": idx,
                        "current": True
                    })
                    found_current = True
                    break
                else:  # pending
                    if not found_current:
                        timeline.append({
                            "title": f"Step {idx}: Awaiting {role.replace('_', ' ')} Approval",
                            "date": datetime.utcnow(),
                            "description": desc,
                            "status": "pending",
                            "icon": "ri-time-line",
                            "step_number": idx,
                            "current": True
                        })
                        found_current = True
            else:
                # Role missing in chain
                if not found_current:
                    timeline.append({
                        "title": f"Step {idx}: {role.replace('_', ' ')} Not Assigned",
                        "date": datetime.utcnow(),
                        "description": "Approver not configured",
                        "status": "pending",
                        "icon": "ri-alert-line",
                        "step_number": idx,
                        "current": True
                    })
                    found_current = True
        
        # Chief Clerk forwarding
        chief_clerk = next((s for s in approval_chain if s.get("role") == "Chief Clerk"), None)
        if chief_clerk and chief_clerk.get("forward_status") == "forwarded":
            timeline.append({
                "title": "Forwarded to SO1-DOA",
                "date": chief_clerk.get("forwardedAt"),
                "description": f"Administrative forwarding by {chief_clerk.get('approverName', 'Chief Clerk')}",
                "status": "completed",
                "icon": "ri-send-plane-line",
                "step_number": None
            })
        
        # Final approval
        final_date = final_approval.get("timestamp")
        if final_status == "approved":
            timeline.append({
                "title": f"Step {final_step_number}: Final Approved by SO1-DOA",
                "date": final_date,
                "description": f"Receipt: {final_approval.get('receipt', {}).get('receiptNumber', 'N/A')}",
                "status": "completed",
                "icon": "ri-check-double-line",
                "step_number": final_step_number
            })
        elif final_status == "rejected":
            timeline.append({
                "title": f"Step {final_step_number}: Rejected by SO1-DOA",
                "date": final_date,
                "description": final_approval.get("comments", "Application rejected"),
                "status": "rejected",
                "icon": "ri-close-line",
                "step_number": final_step_number,
                "current": True
            })
        elif final_status == "pending" and chief_clerk and chief_clerk.get("forward_status") == "forwarded":
            timeline.append({
                "title": f"Step {final_step_number}: Awaiting SO1-DOA Final Approval",
                "date": datetime.utcnow(),
                "description": "Forwarded, waiting for final approval",
                "status": "pending",
                "icon": "ri-time-line",
                "step_number": final_step_number,
                "current": True
            })
        
        # Progress calculation
        completed_steps_count = sum(1 for step in timeline if step['status'] in ['completed', 'rejected'])
        total_steps_count = len(timeline)
        
        # Current step
        current_step = next((s for s in timeline if s.get("current")), None)
        
        # Sort timeline by step_number, None goes last
        timeline.sort(key=lambda x: x.get("step_number") or float('inf'))
        
        return render_template('track_result.html',
                               application=app,
                               reference_id=reference_id,
                               timeline=timeline,
                               current_step=current_step,
                               completed_steps=completed_steps_count,
                               total_steps=total_steps_count,
                               status=app.get("status", "pending"))
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return render_template('track_result.html',
                               error="Error tracking application. Please try again.",
                               reference_id=reference_id)


# @application_track.route('/track_application', methods=['GET', 'POST'])
# def track_application():
#     """Public tracking page (no login required)"""

#     if request.method == 'POST' or request.args.get('reference_id'):

        
#         # Get reference_id from form (POST) or query string (GET)
#         reference_id = request.form.get('reference_id') or request.args.get('reference_id')
        
#         if not reference_id:
#             flash("Please enter a Reference ID.", "error")
#             return render_template('track_application.html')
        
#         try:
            
#             # Try to find the application
#             app = current_app.applications_collection.find_one({"referenceId": reference_id})

#             if not app:
#                 return render_template('track_result.html', 
#                                     error="Application not found. Please check your Reference ID.",
#                                     reference_id=reference_id)

#             # ==================== DETERMINE APPLICANT TYPE ====================
#             # Get applicant ID from application
#             applicant_id = app.get("applicantId")
#             is_civilian = False
            
#             if applicant_id:
#                 # Look up the staff member to get their type
#                 staff_member = current_app.staff_collection.find_one({"_id": applicant_id})
#                 if staff_member:
#                     is_civilian = staff_member.get("type") == "civilian"
#                 else:
#                     # Fallback: Check if service number contains "CIV"
#                     is_civilian = "CIV" in applicant_id.upper() or applicant_id.startswith("DSA/CIV")

#             # Get approval chain details
#             approval_chain = app.get("approvalChain", [])
            
#             # Calculate current position and status
#             current_step = None
#             completed_steps = []
#             pending_steps = []
            
#             for step in approval_chain:
#                 if step.get("status") == "approved":
#                     completed_steps.append(step)
#                 elif step.get("status") == "rejected":
#                     current_step = {"step": step, "status": "rejected"}
#                     break
#                 elif step.get("status") == "pending":
#                     if not current_step:
#                         current_step = {"step": step, "status": "pending"}
#                     pending_steps.append(step)
            
#             # Check if forwarded to SO1-DOA
#             chief_clerk_step = next((s for s in approval_chain if s.get("role") == "Chief Clerk"), None)
#             chief_clerk_forwarded = chief_clerk_step and chief_clerk_step.get("forward_status") == "forwarded"
            
#             # Check final approval
#             final_approval_status = app.get("finalApproval", {}).get("status", "pending")
#             if final_approval_status == "approved":
#                 current_step = {"step": {"role": "Completed", "status": "approved"}, "status": "completed"}
#             elif final_approval_status == "rejected":
#                 current_step = {"step": {"role": "Rejected", "status": "rejected"}, "status": "rejected"}
#             elif chief_clerk_forwarded and final_approval_status == "pending":
#                 current_step = {"step": {"role": "SO1-DOA", "status": "pending"}, "status": "pending"}

#             # ==================== PROGRESS CALCULATION ====================
#             # is_civilian = app.get("type") == "civilian"
            
#             # Count completed steps (excluding Chief Clerk)
#             completed_non_clerk_steps = [step for step in completed_steps if step.get("role") != "Chief Clerk"]
#             completed_non_clerk_count = len(completed_non_clerk_steps)
            
#             if is_civilian:
#                 # CIVILIAN: 6 steps total
#                 # Step 1: Application Submitted ✓ (always)
#                 # Step 2: Civilian Officer Approval
#                 # Step 3: SSO Approval
#                 # Step 4: Deputy Director Approval
#                 # Step 5: Director Approval
#                 # Step 6: SO1-DOA Final Approval
#                 total_steps = 6
                
#                 # Determine completed steps
#                 if app.get("status") == "issued":
#                     completed_count = 6  # All 6 steps completed
#                 elif app.get("status") == "rejected":
#                     completed_count = 1 + completed_non_clerk_count
#                 elif final_approval_status == "approved":
#                     completed_count = 6  # SO1-DOA approved
#                 elif chief_clerk_forwarded:
#                     completed_count = 5  # Steps 1-5 completed, waiting for SO1-DOA
#                 else:
#                     completed_count = 1 + completed_non_clerk_count
                
#                 completed_count = min(completed_count, 6)
                    
#             else:
#                 # MILITARY: 5 steps total (no Civilian Officer)
#                 # Step 1: Application Submitted ✓ (always)
#                 # Step 2: SSO Approval
#                 # Step 3: Deputy Director Approval
#                 # Step 4: Director Approval
#                 # Step 5: SO1-DOA Final Approval
#                 total_steps = 5
                
#                 if app.get("status") == "issued":
#                     completed_count = 5
#                 elif app.get("status") == "rejected":
#                     completed_count = 1 + completed_non_clerk_count
#                 elif final_approval_status == "approved":
#                     completed_count = 5
#                 elif chief_clerk_forwarded:
#                     completed_count = 4  # Steps 1-4 completed
#                 else:
#                     completed_count = 1 + completed_non_clerk_count
                
#                 completed_count = min(completed_count, 5)
            
#             # ==================== TIMELINE CALCULATION ====================
#             timeline = []
            
#             # Step 1: Always completed - Application Submitted
#             timeline.append({
#                 "title": "Step 1: Application Submitted",
#                 "date": app.get("createdAt"),
#                 "description": f"Reference ID: {reference_id}",
#                 "status": "completed",
#                 "icon": "ri-send-plane-line",
#                 "step_number": 1
#             })
            
#             # Define the steps based on application type
#             if is_civilian:
#                 approval_steps = [
#                     ("Civilian Officer", 2),
#                     ("SSO", 3),
#                     ("Deputy_Director", 4),
#                     ("Director", 5)
#                 ]
#                 final_step_number = 6
#             else:
#                 approval_steps = [
#                     ("SSO", 2),
#                     ("Deputy_Director", 3),
#                     ("Director", 4)
#                 ]
#                 final_step_number = 5
            
#             # Track current step for highlighting
#             found_current_step = False
            
#             # Add approval steps to timeline
#             for role, step_number in approval_steps:
#                 step_in_chain = next((s for s in approval_chain if s.get("role") == role), None)
                
#                 if step_in_chain:
#                     if step_in_chain.get("status") == "approved":
#                         timeline.append({
#                             "title": f"Step {step_number}: Approved by {role.replace('_', ' ')}",
#                             "date": step_in_chain.get("timestamp"),
#                             "description": f"{step_in_chain.get('approverName', '')}",
#                             "status": "completed",
#                             "icon": "ri-check-line",
#                             "step_number": step_number
#                         })
#                     elif step_in_chain.get("status") == "rejected":
#                         timeline.append({
#                             "title": f"Step {step_number}: Rejected by {role.replace('_', ' ')}",
#                             "date": step_in_chain.get("timestamp"),
#                             "description": step_in_chain.get('comments', 'Application rejected'),
#                             "status": "rejected",
#                             "icon": "ri-close-line",
#                             "step_number": step_number,
#                             "current": True
#                         })
#                         found_current_step = True
#                         break
#                     elif step_in_chain.get("status") == "pending" and not found_current_step:
#                         timeline.append({
#                             "title": f"Step {step_number}: Awaiting {role.replace('_', ' ')} Approval",
#                             "date": datetime.utcnow(),
#                             "description": "Waiting for approval",
#                             "status": "pending",
#                             "icon": "ri-time-line",
#                             "step_number": step_number,
#                             "current": True
#                         })
#                         found_current_step = True
#                         break
#                 else:
#                     # Step not found in chain (shouldn't happen but handle it)
#                     if not found_current_step:
#                         timeline.append({
#                             "title": f"Step {step_number}: {role.replace('_', ' ')} Not Assigned",
#                             "date": datetime.utcnow(),
#                             "description": "Approver not configured in system",
#                             "status": "pending",
#                             "icon": "ri-alert-line",
#                             "step_number": step_number,
#                             "current": not found_current_step
#                         })
#                         found_current_step = True
            
#             # Add Chief Clerk forwarding if applicable
#             if chief_clerk_step and chief_clerk_step.get("forward_status") == "forwarded":
#                 timeline.append({
#                     "title": "Forwarded to SO1-DOA",
#                     "date": chief_clerk_step.get("forwardedAt"),
#                     "description": f"Administrative forwarding by {chief_clerk_step.get('approverName', 'Chief Clerk')}",
#                     "status": "completed",
#                     "icon": "ri-send-plane-line",
#                     "step_number": None  # Not a numbered step
#                 })
            
#             # Add final SO1-DOA step
#             if final_approval_status == "approved":
#                 timeline.append({
#                     "title": f"Step {final_step_number}: Final Approved by SO1-DOA",
#                     "date": app.get("finalApproval", {}).get("timestamp"),
#                     "description": f"Issued with receipt: {app.get('finalApproval', {}).get('receipt', {}).get('receiptNumber', 'N/A')}",
#                     "status": "completed",
#                     "icon": "ri-check-double-line",
#                     "step_number": final_step_number
#                 })
#             elif final_approval_status == "pending" and chief_clerk_forwarded and not found_current_step:
#                 timeline.append({
#                     "title": f"Step {final_step_number}: Awaiting SO1-DOA Final Approval",
#                     "date": datetime.utcnow(),
#                     "description": "Application forwarded, waiting for final approval",
#                     "status": "pending",
#                     "icon": "ri-time-line",
#                     "step_number": final_step_number,
#                     "current": True
#                 })
#             elif final_approval_status == "rejected":
#                 timeline.append({
#                     "title": f"Step {final_step_number}: Rejected by SO1-DOA",
#                     "date": app.get("finalApproval", {}).get("timestamp"),
#                     "description": app.get("finalApproval", {}).get("comments", "Application rejected"),
#                     "status": "rejected",
#                     "icon": "ri-close-line",
#                     "step_number": final_step_number,
#                     "current": True
#                 })
            
#             # If no current step was found and application is still pending, add generic current step
#             if not any(step.get("current") for step in timeline) and app.get("status") == "pending":
#                 # Find the first pending step
#                 first_pending = None
#                 for step in approval_chain:
#                     if step.get("status") == "pending":
#                         first_pending = step
#                         break
                
#                 if first_pending:
#                     step_num = None
#                     # Find step number for this role
#                     for role, num in approval_steps:
#                         if role == first_pending.get("role"):
#                             step_num = num
#                             break
                    
#                     if step_num:
#                         timeline.append({
#                             "title": f"Step {step_num}: Awaiting {first_pending.get('role', 'Approver')} Approval",
#                             "date": datetime.utcnow(),
#                             "description": "Processing application",
#                             "status": "pending",
#                             "icon": "ri-time-line",
#                             "step_number": step_num,
#                             "current": True
#                         })
            
#             # If issued, ensure we show completion
#             if app.get("status") == "issued":
#                 # Check if we already have the issued step
#                 if not any(step.get("title") == "Application Issued" for step in timeline):
#                     timeline.append({
#                         "title": "Application Issued",
#                         "date": app.get("finalApproval", {}).get("timestamp"),
#                         "description": f"Receipt: {app.get('finalApproval', {}).get('receipt', {}).get('receiptNumber', 'N/A')}",
#                         "status": "completed",
#                         "icon": "ri-check-double-line",
#                         "step_number": final_step_number
#                     })
            
#             # Sort timeline by step number (None steps go to end)
#             timeline.sort(key=lambda x: x.get("step_number") or float('inf'))
            
#             # ==================== RETURN WITH CORRECT VALUES ====================
#             return render_template('track_result.html',
#                                 application=app,
#                                 reference_id=reference_id,
#                                 timeline=timeline,
#                                 current_step=current_step,
#                                 completed_steps=completed_count,
#                                 total_steps=total_steps,
#                                 status=app.get("status", "pending"))
        
#         except Exception as e:
#             print(f"Tracking error: {e}")
#             import traceback
#             traceback.print_exc()
#             return render_template('track_result.html',
#                                 error="Error tracking application. Please try again.",
#                                 reference_id=reference_id)

#     return render_template('track_application.html')



def get_step_description(step):
    """Get description for current step"""
    status = step['status']
    role = step['step'].get('role', '')
    
    if status == "pending":
        if role == "SO1-DOA":
            return "Awaiting final approval from SO1-DOA"
        elif role == "Chief Clerk":
            return "Awaiting forwarding to SO1-DOA"
        elif role == "Civilian Officer":
            return "Awaiting Civilian Officer approval"
        elif role == "SSO":
            return "Awaiting SSO approval"
        elif role == "Deputy_Director":
            return "Awaiting Deputy Director approval"
        elif role == "Director":
            return "Awaiting Director approval"
        else:
            return f"Awaiting approval from {role}"
    elif status == "rejected":
        return "Application has been rejected"
    elif status == "completed":
        if role == "Completed":
            return "Application processing completed"
        return "Approval completed"
    return "Processing..."

def get_step_icon(status):
    """Get icon based on status"""
    icons = {
        "pending": "ri-time-line",
        "approved": "ri-check-line",
        "rejected": "ri-close-line",
        "completed": "ri-check-double-line"
    }
    return icons.get(status, "ri-time-line")