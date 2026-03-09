// parade_socket.js

// Wait for socket to be defined (it's in the other file)
function initParadeSocket() {
    if (typeof socket === 'undefined' || typeof user === 'undefined') {
        console.log("Waiting for socket and user to be defined...");
        setTimeout(initParadeSocket, 100);
        return;
    }

    console.log("Parade Socket initializing...");

    // Remove any existing parade-specific listeners to avoid duplicates
    socket.off("new_notification", handleParadeNotification);
    
    // Add parade-specific listener
    socket.on("new_notification", handleParadeNotification);
}


// socket.on("new_notification", (data) => {
//     console.log("New parade notification:", data);
    
//     // Only show if it's a parade notification (optional)
//     if (data.type === 'parade') {
//         showParadeApprovalModal(data);
//     } else {
//         // Handle other notification types
//         if (typeof showPendingApprovalModal === 'function') {
//             showPendingApprovalModal(data);
//         }
//     }
// });

function handleParadeNotification(data) {
    console.log("New parade notification:", data);
    
    // Only show if it's a parade notification
    if (data.type === 'parade') {
        showParadeApprovalModal(data);
    }
}

function showParadeApprovalModal(data) {
    // Remove any existing modal first
    const existingModal = document.getElementById("paradeApprovalModal");
    if (existingModal) existingModal.remove();


    // Customize message based on action
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


    // Create modal HTML
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
                        <strong>Date:</strong> ${data.date || 'N/A'}
                    </p>
                    <p style="margin-bottom: 5px; color: #666; font-size: 13px;">
                        <strong>Batch:</strong> ${data.batch || 'N/A'}
                    </p>
                    <p style="margin-bottom: 0; color: #666; font-size: 13px;">
                        <strong>Directorate:</strong> ${data.directorate || 'N/A'}
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

   
    // Handle View button click
    document.getElementById("modalViewBtn").addEventListener("click", () => {
        if (data._id) {
            window.location.href = `/view_parade_state/${data._id}`;
        } else {
            window.location.href = "/parade_state/dashboard_parade_state";
        }
    });

    // Handle Continue button click
    document.getElementById("modalContinueBtn").addEventListener("click", () => {
        const modal = document.getElementById("paradeApprovalModal");
        if (modal) modal.remove();
        
        // Optionally refresh the page to show updated notifications
        window.location.reload();
    });
}

//Add a function to check for unread notifications on page load
document.addEventListener("DOMContentLoaded", function() {
    // Fetch unread parade notifications
    fetch('/get_unread_notifications')
        .then(response => response.json())
        .then(notifications => {
            if (notifications && notifications.length > 0) {
                // Show the most recent notification
                showParadeApprovalModal(notifications[0]);
            }
        })
        .catch(error => console.error('Error fetching notifications:', error));
});