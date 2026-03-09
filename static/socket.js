// socket.js - Combined socket handling for all notification types
const socket = io();
const user = window.CURRENT_USER;

socket.on("connect", () => {
    console.log("Socket connected ✅");

    if (user && user.service_number) {
        const safeId = user.service_number.replace(/\//g, "_");
        socket.emit("join_rooms", { service_number: safeId, roles: user.roles });
    }
});

socket.on("disconnect", () => {
    console.log("Socket disconnected ❌");
});

// Handle all notifications
socket.on("new_notification", (data) => {
    console.log("New notification:", data);
    
    if (data.type === 'parade') {
        showParadeApprovalModal(data);
    } else {
        showPendingApprovalModal(data);
    }
});

// Leave/Pass notification modal (unchanged)
function showPendingApprovalModal(data) {
    const existingModal = document.getElementById("pendingApprovalModal");
    if (existingModal) existingModal.remove();

    // Use data from payload directly
    const dateDisplay = data.date || new Date().toISOString().split('T')[0];
    const leaveTypeDisplay = data.leave_type || 'N/A';
    const directorateDisplay = data.directorate || 'N/A';
    const referenceId = data.referenceId || 'N/A';

    const modalHtml = `
        <div id="pendingApprovalModal" style="
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.6);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
        ">
            <div style="
                background: #fff;
                padding: 30px 25px;
                border-radius: 10px;
                max-width: 400px;
                width: 90%;
                text-align: center;
                box-shadow: 0 4px 12px rgba(0,0,0,0.2);
                font-family: 'Inter', Arial, sans-serif;
                border-left: 5px solid #ffc107;
            ">
                <div style="margin-bottom: 15px;">
                    <span style="
                        background: #ffc107;
                        color: #000;
                        padding: 5px 15px;
                        border-radius: 20px;
                        font-size: 12px;
                        font-weight: bold;
                    ">📋 LEAVE & PASS</span>
                </div>

                <h3 style="margin-bottom: 10px; color: #333;">Pending Approval</h3>
                <p style="margin-bottom: 5px; color: #666; font-size: 13px;">
                    <strong>Ref:</strong> ${referenceId}
                </p>
                <p style="margin-bottom: 20px; color: #555; font-size: 14px;">
                    ${data.message}
                </p>

                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; text-align: left;">
                    <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 8px; font-size: 13px;">
                        <span style="color: #666;">📅 Date Submitted:</span>
                        <span style="color: #333; font-weight: 500;">${dateDisplay}</span>
                        
                        <span style="color: #666;">📋 Leave Type:</span>
                        <span style="color: #333; font-weight: 500; text-transform: capitalize;">${leaveTypeDisplay}</span>
                        
                        <span style="color: #666;">🏢 Directorate:</span>
                        <span style="color: #333; font-weight: 500;">${directorateDisplay}</span>
                        
                        <span style="color: #666;">👤 From:</span>
                        <span style="color: #333; font-weight: 500;">${data.triggeredBy || 'System'}</span>
                    </div>
                </div>

                <div style="display: flex; gap: 10px; justify-content: center;">
                    <button id="modalViewLeaveBtn" style="
                        padding: 12px 20px;
                        background: linear-gradient(135deg, #28a745, #20c997);
                        color: white;
                        border: none;
                        border-radius: 8px;
                        cursor: pointer;
                        font-size: 14px;
                        font-weight: 600;
                        flex: 1;
                        transition: transform 0.2s;
                    " onmouseover="this.style.transform='translateY(-2px)'" 
                       onmouseout="this.style.transform='translateY(0)'">
                        👁️ View Details
                    </button>
                    <button id="modalContinueBtn" style="
                        padding: 12px 20px;
                        background: linear-gradient(135deg, #6c757d, #5a6268);
                        color: white;
                        border: none;
                        border-radius: 8px;
                        cursor: pointer;
                        font-size: 14px;
                        font-weight: 600;
                        flex: 1;
                        transition: transform 0.2s;
                    " onmouseover="this.style.transform='translateY(-2px)'" 
                       onmouseout="this.style.transform='translateY(0)'">
                        ⏰ Later
                    </button>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML("beforeend", modalHtml);

    // View Details button
    document.getElementById("modalViewLeaveBtn").addEventListener("click", () => {
        if (data._id) {
            window.location.href = `/view/${data._id}`;
        } else {
            window.location.href = "/approver_dashboard/dashboard_main";
        }
    });

    // Continue/Later button
    document.getElementById("modalContinueBtn").addEventListener("click", () => {
        document.getElementById("pendingApprovalModal")?.remove();
    });
}




// Parade notification modal - UPDATED
function showParadeApprovalModal(data) {
    const existingModal = document.getElementById("paradeApprovalModal");
    if (existingModal) existingModal.remove();

    let title = "Pending Approval";
    let buttonColor = "#ffc107";
    let borderColor = "#ffc107";
    
    if (data.action === 'submitted') {
        title = "New Parade State Submitted";
        buttonColor = "#17a2b8";
        borderColor = "#17a2b8";
    } else if (data.action === 'documentation') {
        title = "Documentation Required";
        buttonColor = "#6c757d";
        borderColor = "#6c757d";
    }

    // Extract date from message if not provided directly
    let dateDisplay = data.date || 'N/A';
    let batchDisplay = data.batch || 'N/A';
    let directorateDisplay = data.directorate || 'N/A';
    
    // Try to parse from message if not available in data
    if (dateDisplay === 'N/A' && data.message) {
        const dateMatch = data.message.match(/\d{4}-\d{2}-\d{2}/);
        if (dateMatch) {
            dateDisplay = dateMatch[0];
        }
        
        const batchMatch = data.message.match(/Batch ([A-B])/);
        if (batchMatch) {
            batchDisplay = batchMatch[1];
        }
    }

    const modalHtml = `
        <div id="paradeApprovalModal" style="
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.6);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
        ">
            <div style="
                background: #fff;
                padding: 30px 25px;
                border-radius: 10px;
                max-width: 450px;
                width: 90%;
                text-align: center;
                box-shadow: 0 4px 12px rgba(0,0,0,0.2);
                font-family: Arial, sans-serif;
                border-left: 5px solid ${borderColor};
            ">
                <div style="margin-bottom: 15px;">
                    <span style="
                        background: ${borderColor};
                        color: #000;
                        padding: 5px 10px;
                        border-radius: 20px;
                        font-size: 12px;
                        font-weight: bold;
                    ">PARADE STATE</span>
                </div>
                <h3 style="margin-bottom: 15px; color: #333;">${title}</h3>
                <p style="margin-bottom: 10px; color: #555; font-size: 14px;">
                    ${data.message}
                </p>
                <div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin-bottom: 15px;">
                    <p style="margin-bottom: 5px; color: #666; font-size: 13px;">
                        <strong>Date:</strong> ${dateDisplay}
                    </p>
                    <p style="margin-bottom: 5px; color: #666; font-size: 13px;">
                        <strong>Batch:</strong> ${batchDisplay}
                    </p>
                    <p style="margin-bottom: 0; color: #666; font-size: 13px;">
                        <strong>Directorate:</strong> ${directorateDisplay}
                    </p>
                </div>
                <p style="margin-bottom: 25px; color: #777; font-size: 12px;">
                    From: ${data.triggeredBy || 'System'}
                </p>
                <div style="display: flex; gap: 10px; justify-content: center;">
                    <button id="modalViewBtn" style="
                        padding: 10px 20px;
                        background-color: #28a745;
                        color: #fff;
                        border: none;
                        border-radius: 5px;
                        cursor: pointer;
                        font-size: 14px;
                        flex: 1;
                    ">View Parade State</button>
                    <button id="modalContinueBtn" style="
                        padding: 10px 20px;
                        background-color: ${buttonColor};
                        color: #000;
                        border: none;
                        border-radius: 5px;
                        cursor: pointer;
                        font-size: 14px;
                        flex: 1;
                    ">Continue</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML("beforeend", modalHtml);

    // Handle View button click - mark as read then navigate
    document.getElementById("modalViewBtn").addEventListener("click", () => {
        // Mark notification as read first
        if (data.notification_id) {
            fetch(`/mark_notification_read/${data.notification_id}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => response.json())
            .then(result => {
                console.log('Notification marked as read:', result);
            })
            .catch(error => console.error('Error marking notification as read:', error))
            .finally(() => {
                // Navigate after marking as read
                if (data._id) {
                    window.location.href = `/view_parade_state/${data._id}`;
                } else {
                    window.location.href = "/parade_state/dashboard_parade_state";
                }
            });
        } else {
            // No notification_id, just navigate
            if (data._id) {
                window.location.href = `/view_parade_state/${data._id}`;
            } else {
                window.location.href = "/parade_state/dashboard_parade_state";
            }
        }
    });

    // Handle Continue button click - mark as read then reload
    document.getElementById("modalContinueBtn").addEventListener("click", () => {
        // Mark notification as read first
        if (data.notification_id) {
            fetch(`/mark_notification_read/${data.notification_id}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => response.json())
            .then(result => {
                console.log('Notification marked as read:', result);
            })
            .catch(error => console.error('Error marking notification as read:', error))
            .finally(() => {
                // Remove modal and reload
                document.getElementById("paradeApprovalModal")?.remove();
                window.location.reload();
            });
        } else {
            // No notification_id, just remove modal and reload
            document.getElementById("paradeApprovalModal")?.remove();
            window.location.reload();
        }
    });
}

// Fetch unread notifications on page load - UPDATED to check localStorage to avoid showing the same notification repeatedly
document.addEventListener("DOMContentLoaded", function() {
    // Check if we just came from a notification action
    const justHandledNotification = sessionStorage.getItem('notificationHandled');
    if (justHandledNotification) {
        sessionStorage.removeItem('notificationHandled');
        return;
    }
    
    fetch('/get_unread_notifications')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(notifications => {
            console.log('Fetched notifications:', notifications);
            if (notifications && notifications.length > 0) {
                // Filter for parade notifications only
                const paradeNotifications = notifications.filter(n => n.type === 'parade_approval_required' || n.type === 'parade');
                if (paradeNotifications.length > 0) {
                    showParadeApprovalModal(paradeNotifications[0]);
                }
            }
        })
        .catch(error => console.error('Error fetching notifications:', error));
});

