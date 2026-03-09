from flask import request, render_template, redirect, flash, url_for, Blueprint, current_app, session
# from werkzeug.security import generate_password_hash



verify_service_number_routes = Blueprint('verify_service_number_routes', __name__)




@verify_service_number_routes.route('/apply_id', methods=['GET', 'POST'])
def apply_id():
    return render_template('apply_id.html')



@verify_service_number_routes.route('/service_number_verification', methods=['GET', 'POST'])
def service_number_verification():

    service_number = request.form.get('service_number', '').strip().upper()

    if not service_number:
        flash('Please provide a valid Service Number', 'error')
        return redirect(url_for('verify_service_number_routes.apply_id'))

    # Access collection (make sure this is set in your app factory)
    staff_coll = current_app.staff_collection
    staff = staff_coll.find_one({"service_number": service_number})
        
    if not staff:
        flash('Service number not found. Please check and try again.', 'error')
        return redirect(url_for('verify_service_number_routes.apply_id'))

    # Store minimal data in session (secure & temporary)
    session['applicant'] = {
        'service_number': service_number,
        'fullName': staff.get('fullName', ''),
        'type': staff.get('type', ''),
        'directorate': staff.get('directorate', ''),
        'rankOrGrade': staff.get('rankOrGrade', ''),
        'designation': staff.get('designation', ''),
        'email': staff.get('email', ''),
        'gender': staff.get('gender', '').lower()
        
        # Add more fields if needed
    }
        
    flash('Service number verified successfully.', 'success')
    
    return redirect(url_for('application_routes.application_form'))







# @user_auth.route('/register', methods=['GET', 'POST'])
# def register():
#     if request.method == 'POST':

#         email = request.form.get('email', "").strip().lower()
#         fname = request.form.get('fname', "").strip()
#         lname = request.form.get('lname', "").strip()
#         category = request.form.get('category', "").strip()
#         directorate = request.form.get('directorate', "").strip()
#         staffid = request.form.get('staffid', "").strip().upper()
#         password = request.form.get('password')
#         confirm_password = request.form.get('con_password')
#         role = category  # Default role assignment

#         # VALIDATIONS
#         if not fname or not lname:
#             flash("First and last names cannot be empty.", "error")
#             return redirect(url_for('user_reg_log_auth.register'))

#         if password != confirm_password:
#             flash("Passwords do not match.", "error")
#             return redirect(url_for('user_reg_log_auth.register'))

#         if directorate not in ['dcs', 'doa', 'deo', 'dnpt', 'dcyber', 'dlog']:
#             flash("Please select a valid directorate.", "error")
#             return redirect(url_for('user_reg_log_auth.register'))

#         if not email.endswith('@dsa.mil.ng'):
#             flash("Please use your official DSA email.", "error")
#             return redirect(url_for('user_reg_log_auth.register'))

#         if category not in ['civilian', 'personnel']:
#             flash("Please select a valid category.", "error")
#             return redirect(url_for('user_reg_log_auth.register'))

#         if category == 'personnel' and staffid.startswith('DSA/CIV/'):
#             flash("Invalid Service Number for Personnel category.", "error")
#             return redirect(url_for('user_reg_log_auth.register'))

#         if category == 'civilian' and staffid.startswith(('NA/', 'XF/')):
#             flash("Invalid Staff ID for civilian category.", "error")
#             return redirect(url_for('user_reg_log_auth.register'))


#         # CHECK IF EMAIL ALREADY EXISTS
#         users_collection = current_app.users_collection
#         existing_user = users_collection.find_one({"email": email})
#         if existing_user:
#             flash("Email already registered.", "error")
#             return redirect(url_for('user_reg_log_auth.register'))
        
#         if staffid:
#             existing_staffid = users_collection.find_one({"staff_id": staffid})
#             if existing_staffid:
#                 flash("Staff ID/Service Number already registered.", "error")
#                 return redirect(url_for('user_reg_log_auth.register'))

#         # HASH PASSWORD
#         hashed_pwd = generate_password_hash(password)

#         # INSERT INTO DB
#         new_user = {
#             "first_name": fname,
#             "last_name": lname,
#             "email": email,
#             "staff_id": staffid,
#             "category": category,
#             "directorate": directorate,
#             "password": hashed_pwd,
#             "role": role,
#             "created_at": datetime.utcnow()
#         }

#         users_collection.insert_one(new_user)
#         flash("Registration Successful", "sucess")
#         return redirect(url_for('user_reg_log_auth.login'))

#     return render_template('register.html')


# @user_auth.route('/login', methods=['GET', 'POST'])
# def login():
#     return render_template('login.html')



    