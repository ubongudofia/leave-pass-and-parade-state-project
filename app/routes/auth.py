from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.security import check_password_hash
from datetime import datetime

auth = Blueprint('auth', __name__)


def get_sidebar_permissions(roles):
    permissions = {
        "leave_pass": False,
        "parade_state": False
    }

    if "Admin Officer" in roles:
        permissions["parade_state"] = True

    if any(r in roles for r in ["Civilian Officer", "Deputy_Director", "Chief Clerk"]):
        permissions["leave_pass"] = True
        permissions["parade_state"] = True

    if any(r in roles for r in ["SSO", "Director", "SO1-DOA"]):
        permissions["leave_pass"] = True

    if "DOA-RSM" in roles:
        permissions["parade_state"] = True

    return permissions

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        service_number = request.form.get('service_number', '').strip().upper()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        if not service_number or not password:
            flash("Service number and password are required.", "error")
            return redirect(url_for('auth.login'))

        staff_coll = current_app.staff_collection

        # user['_id'] = str(user['_id'])
        user = staff_coll.find_one({"service_number": service_number})

        if not user:
            flash("Service number not found.", "error")
            return redirect(url_for('auth.login'))

        if not user.get('isActive', True):
            flash("Your account is inactive. Contact the administrator.", "error")
            return redirect(url_for('auth.login'))

        if 'password' not in user or not check_password_hash(user['password'], password):
            flash("Incorrect password.", "error")
            return redirect(url_for('auth.login'))

        # Successful login
        session.permanent = remember  # if remember is checked, session lasts longer
        session['user'] = {
            'service_number': service_number,
            'fullName': user['fullName'],
            'rankOrGrade': user['rankOrGrade'],
            'designation': user['designation'],
            'directorate': user['directorate'],
            'type': user['type'],
            'roles': user.get('roles', []),
            'isActive': user.get('isActive', True),
            'permissions': get_sidebar_permissions(user.get('roles', []))  # 👈 ADD THIS
        }

        # Update last login
        staff_coll.update_one(
            {"service_number": service_number},
            {"$set": {"lastLogin": datetime.utcnow()}}
        )

        flash("Login successful!", "success")

        # Role-based redirect
        if "SO1-DOA" in session['user']['roles']:
            return redirect(url_for('approver_dashboard.dashboard_main'))
        
        if "DOA-RSM" in session['user']['roles']:
            return redirect(url_for('parade_state.dashboard_parade_state'))
        
        if "Admin Officer" in session['user']['roles']:
            return redirect(url_for('parade_state.dashboard_parade_state'))

        if any(r in session['user']['roles'] for r in ["Director", "Deputy_Director", "SSO", "Civilian Officer", "Chief Clerk"]):
            return redirect(url_for('approver_dashboard.dashboard_main'))

        return redirect(url_for('application_routes.application_form'))

    return render_template('login.html')


@auth.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('auth.login'))