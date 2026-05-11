from flask import Flask
from pymongo import MongoClient
from config import Config
from gridfs import GridFS
from app.extensions import socketio

# BLUEPRINT
from app.routes.verify_service_number import verify_service_number_routes
from app.routes.welcome import welcome_routes
from app.routes.start_application import application_routes
from app.routes.application_success import application_success_routes
from app.routes.approver_dashboard import approver_dashboard    
from app.routes.auth import auth
from app.routes.application_track import application_track
from app.routes.parade_state import parade_state


# APP INSTANCE
app = Flask(__name__)
app.config.from_object(Config)
socketio.init_app(app)



# Add useful Python functions to Jinja2 environment
app.jinja_env.globals.update(
    enumerate=enumerate,
    len=len,
    range=range,
    str=str,
    int=int,
    list=list,
    zip=zip
)


# MONGO DB CONNECTION
# client = MongoClient(app.config['MONGO_URI'])
client = MongoClient(os.environ["MONGO_URI"])
db = client['dsa_pass_leave']


# Create GridFS instance
fs = GridFS(db, collection="attachments")
app.fs = fs

# database collections
staff_collection = db['staff']
directorates_collection = db['directorates']
applications_collection = db['applications']
leave_balances = db['leave_balances']
medical_records = db['medical_records']
notifications_collection = db['notifications']
daily_parade_states = db['daily_parade_states']


# attach to app for blueprints to access via current_app
app.staff_collection = staff_collection
app.directorates_collection = directorates_collection
app.applications_collection = applications_collection
app.leave_balances =  leave_balances
app.medical_records = medical_records
app.notifications_collection = notifications_collection
app.daily_parade_states = daily_parade_states

# VERIFY SERVICE NUMBER ROUTES
app.register_blueprint(verify_service_number_routes)

# REGISTER WELCOME ROUTES
app.register_blueprint(welcome_routes)

# REGISTER START APPLICATION ROUTES
app.register_blueprint(application_routes)

# REGISTER APPLICATION SUCCESS ROUTES
app.register_blueprint(application_success_routes)

# REGISTER APPROVER DASHBOARD ROUTES
app.register_blueprint(approver_dashboard)

# REGISTER AUTHENTICATION ROUTES
app.register_blueprint(auth)

# REGISTER APPLICATION TRACKING ROUTES
app.register_blueprint(application_track)

# REGISTER PARADE STATE ROUTES
app.register_blueprint(parade_state)






 











if __name__ == '__main__':
    socketio.run(app, debug=True, port=5009, host='0.0.0.0')
