import datetime
import os
from decimal import Decimal
from flask import Flask, request, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_cors import CORS
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from config import Config
from models import *
# from models import Base, Cases, Court, Payments, Users, Admin, Lawyer, Judge, Courtregistrar, Caseparticipant, t_courtaccess, Appeals, Courtroom, Documentcase, Casehistory, Bail, Hearings, Evidence, Witness

app = Flask(__name__, static_folder="../frontend/dist", static_url_path="/")
app.config.from_object(Config)

# Database setup
engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Session and CORS
Session(app)
CORS(app, supports_credentials=True, origins=["http://localhost:3000"])

# Login manager
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    db = SessionLocal()
    user = db.query(Users).get(int(user_id))
    db.close()
    return user

@app.route("/")
def serve():
    return app.send_static_file("index.html")

@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json()
    firstname = data.get("firstname")
    lastname = data.get("lastname")
    email = data.get("email")
    phoneno = data.get("phoneno")
    cnic = data.get("cnic")
    dob = data.get("dob")
    password = data.get("password")
    role = data.get("role", "user").strip().lower()  # Make role lowercase

    # Role mapping to ensure the correct capitalization in database
    role_mapping = {
        "courtregistrar": "CourtRegistrar",
        "caseparticipant": "CaseParticipant",
        "admin": "Admin",
        "lawyer": "Lawyer",
        "judge": "Judge"
    }

    role = role_mapping.get(role, role)  # Get the correct role or default to the input role

    valid_roles = ["Admin", "CourtRegistrar", "CaseParticipant", "Lawyer", "Judge"]
    if role not in valid_roles:
        return jsonify({"success": False, "message": "Invalid role"}), 400

    db = SessionLocal()
    try:
        existing = db.query(Users).filter_by(firstname=firstname).first()
        if existing:
            return jsonify({"success": False, "message": "Username already exists"}), 400

        hashed_pw = generate_password_hash(password)

        user = Users(
            firstname=firstname,
            lastname=lastname,
            email=email,
            phoneno=phoneno,
            cnic=cnic,
            dob=dob,
            password=hashed_pw,
            role=role
        )
        db.add(user)
        db.flush()
        db.commit()

        session['user_id'] = user.userid
        login_user(user)

    except Exception as e:
        db.rollback()
        print(f"Error occurred: {str(e)}")
        return jsonify({"message": "An error occurred during sign-up."}), 500
        
    finally:
        db.close()

    return jsonify({
        "success": True,
        "message": "Signup successful. Please complete your profile.",
        "user_id": user.userid
    }), 201

@app.route('/api/complete-profile', methods=['POST'])
def complete_profile():
    db = SessionLocal()
    try:
        data = request.get_json()
        print(f"Data received: {data}")

        user_id = data.get('user_id') or session.get('user_id')
        if not user_id:
            return jsonify({"message": "User not logged in or session expired."}), 401

        user = db.query(Users).get(user_id)
        if not user:
            return jsonify({"message": "User not found"}), 404

        profile_data = data.get('profile_data', {})
        print(f"Profile data: {profile_data}")

        print(f"User role: {user.role}")
        # Normalize role during profile completion
        role_mapping = {
            "courtregistrar": "CourtRegistrar",
            "caseparticipant": "CaseParticipant",
            "admin": "Admin",
            "lawyer": "Lawyer",
            "judge": "Judge"
        }
        role = user.role.lower()  # Normalize role to lowercase
        user.role = role_mapping.get(role, role)  # Update to correct role case if needed

        # The rest of the profile completion logic remains the same...
        if user.role == 'CaseParticipant':
            address = data.get('address')
            if address:
                client = Caseparticipant(userid=user.userid, address=address)
                db.add(client)
                db.commit()
                print(f"Inserted CaseParticipant: {client}")

        elif user.role == 'Lawyer':
            barlicenseno = data.get('barLicense')  
            experienceyears = data.get('experience')  
            specialization = data.get('specialization')

            if barlicenseno and experienceyears and specialization:
                print("All Lawyer fields present, inserting Lawyer...")
                try:
                    lawyer = Lawyer(
                        userid=user.userid,
                        barlicenseno=barlicenseno,
                        experienceyears=experienceyears,
                        specialization=specialization
                    )
                    db.add(lawyer)
                    db.commit()
                    print(f"Inserted Lawyer: {lawyer}")
                except Exception as e:
                    db.rollback()
                    print(f"Exception occurred while inserting Lawyer: {e}")
            else:
                print("One or more required Lawyer fields are missing.")

        elif user.role == 'Judge':
            position = data.get('position')
            specialization = data.get('specialization')
            experience = data.get('experience')
            if position and specialization and experience:
                judge = Judge(
                    userid=user.userid,
                    position=position,
                    specialization=specialization,
                    experience=experience
                )
                db.add(judge)
                db.commit()
                print(f"Inserted Judge: {judge}")

        elif user.role == 'CourtRegistrar':
            position = data.get('position')
            if position:
                registrar = Courtregistrar(userid=user.userid, position=position)
                db.add(registrar)
                db.commit()
                print(f"Inserted Court Registrar: {registrar}")

        login_user(user)
        return jsonify({"message": "Profile completed successfully"}), 200

    except Exception as e:
        error_message = str(e)
        print(f"Error occurred: {error_message}")
        db.rollback()
        return jsonify({"message": f"An error occurred while completing the profile: {error_message}"}), 500
    
    finally:
        db.close()


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    db = SessionLocal()
    try:
        user = db.query(Users).filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return jsonify({
                "success": True,
                "message": "Logged in",
                "email": user.email,
                "role": user.role
            }), 200
        return jsonify({"success": False, "message": "Invalid credentials"}), 401
    finally:
        db.close()

@app.route("/api/dashboard", methods=["GET"])
@login_required
def dashboard():
    db = SessionLocal()
    lawyer = db.query(Lawyer).filter_by(userid=current_user.userid).first()
    specialization = lawyer.specialization if lawyer else None
    barlicenseno = lawyer.barlicenseno if lawyer else None
    db.close()

    return jsonify({
        "success": True,
        "user": {
            "username": f"{current_user.firstname} {current_user.lastname}",
            "specialization": specialization,
            "barlicenseno": barlicenseno
        }
    })

@app.route("/api/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"success": True, "message": "Logged out"})

@app.route('/api/lawyerprofile', methods=['GET'])
def get_lawyer_profile():
    db = SessionLocal()
    user_id = current_user.userid  
    
    if not user_id:
        return jsonify(success=False, message="User ID is required."), 400

    lawyer = db.query(Lawyer).filter_by(userid=user_id).first()

    if not lawyer:
        return jsonify(success=False, message="Profile not found"), 404

    return jsonify(success=True, data={
        'firstName': current_user.firstname,
        'lastName': current_user.lastname,
        'email': current_user.email,
        'phone': current_user.phoneno,
        'specialization': lawyer.specialization,
        'cnic': current_user.cnic,
        'dob': current_user.dob.isoformat() if current_user.dob else '',
        'barLicense': lawyer.barlicenseno,
        'experience': lawyer.experienceyears
    })

@app.route('/api/lawyerprofile', methods=['PUT'])
def update_lawyer_profile():
    db = SessionLocal()
    user_id = current_user.userid

    if not user_id:
        return jsonify(success=False, message="User ID is required."), 400

    data = request.get_json()
    lawyer = db.query(Lawyer).filter_by(userid=user_id).first()

    if not lawyer:
        return jsonify(success=False, message="Profile not found"), 404

    try:
        lawyer.specialization = data.get('specialization', lawyer.specialization)
        lawyer.barlicenseno = data.get('barLicense', lawyer.barlicenseno)
        lawyer.experienceyears = data.get('experience', lawyer.experienceyears)

        db.commit()
        return jsonify(success=True, message="Profile updated successfully")

    except Exception as e:
        db.rollback()
        return jsonify(success=False, message=str(e)), 500
    

@app.route('/api/court', methods=['POST'])
@login_required
def add_court():
    db = SessionLocal()
    try:
        data = request.get_json()

        courtname = data.get('courtname')
        court_type = data.get('type')
        location = data.get('location')

        if not courtname or not court_type or not location:
            return jsonify({'status': 'error', 'message': 'All fields (courtname, type, location) are required'}), 400

        new_court = Court(courtname=courtname, type=court_type, location=location)
        db.add(new_court)
        db.flush()  

        
        if current_user.role == 'CourtRegistrar':
            registrar = db.query(Courtregistrar).filter_by(userid=current_user.userid).first()
            if registrar:
                registrar.courtid = new_court.courtid  # Associate court
                print(f"Linked court ID {new_court.courtid} to registrar {registrar.courtid}")
            else:
                return jsonify({'status': 'error', 'message': 'CourtRegistrar profile not found'}), 404

        db.commit()

        return jsonify({'status': 'success', 'message': 'Court added and linked to registrar', 'court_id': new_court.courtid}), 201

    except Exception as e:
        db.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/registrarprofile', methods=['GET'])
@login_required
def get_registrar_profile():
    db = SessionLocal()
    try:
        user_id = current_user.userid

        registrar = db.query(Courtregistrar).filter_by(userid=user_id).first()

        if not registrar:
            return jsonify(success=False, message="Registrar profile not found"), 404

        return jsonify(success=True, data={
            'firstName': current_user.firstname,
            'lastName': current_user.lastname,
            'email': current_user.email,
            'phone': current_user.phoneno,
            'cnic': current_user.cnic,
            'dob': current_user.dob.isoformat() if current_user.dob else '',
            'position': registrar.position,
            'courtid': registrar.courtid  
        }), 200

    except Exception as e:
        return jsonify(success=False, message=str(e)), 500

    finally:
        db.close()

@app.route('/api/court', methods=['GET'])
@login_required
def get_court_for_registrar():
    db = SessionLocal()
    try:
        registrar = db.query(Courtregistrar).filter_by(userid=current_user.userid).first()
        if not registrar:
            return jsonify(success=False, message="Registrar profile not found"), 404

        if not registrar.courtid:
            return jsonify(success=False, message="Registrar is not assigned to any court"), 404

        court = db.query(Court).get(registrar.courtid)
        if not court:
            return jsonify(success=False, message="Court not found"), 404

        return jsonify(success=True, data={
            'courtname': court.courtname,
            'type': court.type,
            'location': court.location
        }), 200

    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        db.close()
        
        
@app.route('/api/payments', methods=['GET'])
@login_required
def get_lawyer_payments():
    db = SessionLocal()
    try:
        #fetch lawyer using userid
        lawyer = db.query(Lawyer).filter_by(userid=current_user.userid).first()
        if not lawyer:
            return jsonify({'status': 'error', 'message': 'Lawyer profile not found'}), 404

        #fetch payments linked to lawyerid
        payments = (
            db.query(Payments)
            .filter_by(lawyerid=lawyer.lawyerid)
            .join(Cases, Payments.caseid == Cases.caseid)
            .with_entities(
                Payments.paymentdate,
                Cases.title.label("casename"),
                Payments.purpose,
                Payments.balance,
                Payments.mode
            )
            .all()
        )

        
        result = [
            {
                "paymentdate": str(p.paymentdate),
                "casename": p.casename,
                "purpose": p.purpose,
                "balance": float(p.balance),
                "mode": p.mode
            }
            for p in payments
        ]

        return jsonify({'status': 'success', 'payments': result}), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        db.close()
        
@app.route('/api/payments', methods=['POST'])
@login_required
def create_payment():
    db = SessionLocal()
    try:
        data = request.get_json()

        casename = data.get('casename')
        purpose = data.get('purpose')
        balance = data.get('balance')
        mode = data.get('mode')
        paymentdate = data.get('paymentdate') or datetime.date.today()
        paymenttype = data.get('paymenttype')  # Get paymenttype from request

        if not all([casename, purpose, balance, mode, paymenttype]):
            return jsonify({'message': 'Missing required fields'}), 400  # Ensure paymenttype is also validated

        # 1. Get lawyer
        lawyer = db.query(Lawyer).filter_by(userid=current_user.userid).first()
        if not lawyer:
            return jsonify({'message': 'Lawyer not found'}), 404

        # 2. Get case by title
        case = db.query(Cases).filter_by(title=casename).first()
        if not case:
            return jsonify({'message': 'Case not found'}), 404

        # 3. Get courtid via courtaccess
        access_entry = db.query(t_courtaccess).filter(t_courtaccess.c.caseid == case.caseid).first()
        if not access_entry:
            return jsonify({'message': 'Court access entry not found'}), 404

        courtid = access_entry.courtid

        # 4. Create and save payment
        new_payment = Payments(
            mode=mode,
            purpose=purpose,
            balance=Decimal(balance),
            paymentdate=paymentdate,
            lawyerid=lawyer.lawyerid,
            caseid=case.caseid,
            courtid=courtid,
            paymenttype=paymenttype  # Add paymenttype
        )

        db.add(new_payment)
        db.commit()

        return jsonify({
            'message': 'Payment recorded successfully',
            'payment': {
                'paymentdate': str(paymentdate),
                'casename': casename,
                'purpose': purpose,
                'balance': float(balance),
                'mode': mode,
                'paymenttype': paymenttype  # Include paymenttype in the response
            }
        }), 201

    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        

# api made by kaif

#CourtRoom API
@app.route('/api/courtrooms', methods=['POST'])
@login_required
# @log_action(action_type = "CREATE", entity_type = "Courtrooms")
def create_courtroom():
    db = SessionLocal()
    try:
        data = request.get_json()
        courtroom = Courtroom(
            number=data.get('number'),
            name=data.get('name'),
            capacity=data.get('capacity'),
            type=data.get('type'),
            status=data.get('status', 'Available')
        )
        db.add(courtroom)
        db.commit()
        return jsonify({'message': 'Courtroom created successfully'}), 201
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/courtrooms', methods=['GET'])
@login_required
def get_courtrooms():
    db = SessionLocal()
    try:
        courtrooms = db.query(Courtroom).all()
        result = [
            {
                'number': r.number,
                'name': r.name,
                'capacity': r.capacity,
                'type': r.type,
                'status': r.status
            }
            for r in courtrooms
        ]
        return jsonify({'courtrooms': result}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

# cases api
@app.route('/api/cases', methods=['POST'])
@login_required
# @log_action(action_type = "CREATE", entity_type = "Cases")
def create_case():
    db = SessionLocal()
    try:
        data = request.get_json()
        title = data.get('title')
        description = data.get('description')
        casetype = data.get('casetype')
        filingdate = data.get('filingdate') or datetime.date.today()
        status = data.get('status', 'Open')

        if not title or not casetype:
            return jsonify({'message': 'Title and case type are required'}), 400

        new_case = Cases(
            title=title,
            description=description,
            casetype=casetype,
            filingdate=filingdate,
            status=status
        )
        db.add(new_case)
        db.commit()

        return jsonify({'message': 'Case created successfully', 'case_id': new_case.caseid}), 201
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        
@app.route('/api/cases', methods=['GET'])
@login_required
def get_cases():
    db = SessionLocal()
    try:
        query_params = request.args
        status = query_params.get('status')
        casetype = query_params.get('casetype')
        title = query_params.get('title')

        query = db.query(Cases)

        if status:
            query = query.filter(Cases.status == status)
        if casetype:
            query = query.filter(Cases.casetype == casetype)
        if title:
            query = query.filter(Cases.title.ilike(f'%{title}%'))

        cases = query.all()
        result = [
            {
                'caseid': c.caseid,
                'title': c.title,
                'description': c.description,
                'casetype': c.casetype,
                'filingdate': c.filingdate.isoformat() if c.filingdate else None,
                'status': c.status
            }
            for c in cases
        ]

        return jsonify({'cases': result}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/cases/<int:case_id>', methods=['PUT'])
@login_required
# @log_action(action_type = "UPDATE", entity_type = "Cases")
def update_case(case_id):
    db = SessionLocal()
    try:
        data = request.get_json()
        case = db.query(Cases).get(case_id)

        if not case:
            return jsonify({'message': 'Case not found'}), 404

        case.title = data.get('title', case.title)
        case.description = data.get('description', case.description)
        case.casetype = data.get('casetype', case.casetype)
        case.status = data.get('status', case.status)

        db.commit()
        return jsonify({'message': 'Case updated successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/cases/<int:case_id>', methods=['DELETE'])
@login_required
# @log_action(action_type = "DELETE", entity_type = "Cases")
def delete_case(case_id):
    db = SessionLocal()
    try:
        case = db.query(Cases).get(case_id)

        if not case:
            return jsonify({'message': 'Case not found'}), 404

        db.delete(case)
        db.commit()
        return jsonify({'message': 'Case deleted successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        
@app.route('/api/cases/<int:case_id>/assign', methods=['POST'])
@login_required
# @log_action(action_type = "CREATE", entity_type = "Assignments")
def assign_case(case_id):
    db = SessionLocal()
    try:
        data = request.get_json()
        assignee_id = data.get('assignee_id')
        role = data.get('role')  # 'lawyer' or 'judge'

        case = db.query(Cases).get(case_id)
        if not case:
            return jsonify({'message': 'Case not found'}), 404

        if role == 'lawyer':
            lawyer = db.query(Lawyer).get(assignee_id)
            if not lawyer:
                return jsonify({'message': 'Lawyer not found'}), 404
            case.lawyer.append(lawyer)
        elif role == 'judge':
            judge = db.query(Judge).get(assignee_id)
            if not judge:
                return jsonify({'message': 'Judge not found'}), 404
            case.judge.append(judge)
        else:
            return jsonify({'message': 'Invalid role'}), 400

        db.commit()
        return jsonify({'message': 'Case assigned successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        

# Appeals API
@app.route('/api/appeals', methods=['POST'])
@login_required
# @log_action(action_type = "CREATE", entity_type = "Appeals")
def create_appeal():
    db = SessionLocal()
    try:
        data = request.get_json()
        appeal = Appeals(
            appealnumber=data.get('appealNumber'),
            originalcaseid=data.get('originalCaseId'),
            appellant=data.get('appellant'),
            respondent=data.get('respondent'),
            datefiled=data.get('dateFiled'),
            status=data.get('status', 'Under Review')
        )
        db.add(appeal)
        db.commit()
        return jsonify({'message': 'Appeal created successfully'}), 201
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/appeals', methods=['GET'])
@login_required
def get_appeals():
    db = SessionLocal()
    try:
        appeals = db.query(Appeals).all()
        result = [
            {
                'appealNumber': a.appealnumber,
                'originalCaseId': a.originalcaseid,
                'appellant': a.appellant,
                'respondent': a.respondent,
                'dateFiled': a.datefiled.isoformat(),
                'status': a.status
            }
            for a in appeals
        ]
        return jsonify({'appeals': result}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

#Hearings API
@app.route('/api/hearings', methods=['POST'])
@login_required
# @log_action(action_type = "CREATE", entity_type = "Hearings")
def schedule_hearing():
    db = SessionLocal()
    try:
        data = request.get_json()
        hearing = Hearings(
            caseid=data.get('caseid'),
            hearingdate=data.get('hearingdate'),
            hearingtime=data.get('hearingtime'),
            courtroomid=data.get('courtroomid')
        )
        db.add(hearing)
        db.commit()
        return jsonify({'message': 'Hearing scheduled successfully'}), 201
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/hearings/<int:case_id>', methods=['GET'])
@login_required
def get_hearings(case_id):
    db = SessionLocal()
    try:
        hearings = db.query(Hearings).filter_by(caseid=case_id).all()
        result = [
            {
                'hearingid': h.hearingid,
                'hearingdate': h.hearingdate.isoformat(),
                'hearingtime': h.hearingtime,
                'courtroomid': h.courtroomid
            }
            for h in hearings
        ]
        return jsonify({'hearings': result}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/hearings/<int:hearing_id>', methods=['PUT'])
@login_required
# @log_action(action_type = "UPDATE", entity_type = "Hearings")
def update_hearing(hearing_id):
    db = SessionLocal()
    try:
        data = request.get_json()
        hearing = db.query(Hearings).get(hearing_id)

        if not hearing:
            return jsonify({'message': 'Hearing not found'}), 404

        hearing.hearingdate = data.get('hearingdate', hearing.hearingdate)
        hearing.hearingtime = data.get('hearingtime', hearing.hearingtime)
        hearing.courtroomid = data.get('courtroomid', hearing.courtroomid)

        db.commit()
        return jsonify({'message': 'Hearing updated successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

# Bails API
@app.route('/api/bails', methods=['POST'])
@login_required
# @log_action(action_type = "CREATE", entity_type = "Bails")
def create_bail():
    db = SessionLocal()
    try:
        data = request.get_json()
        case_id = data.get('case_id')
        amount = data.get('amount')
        bail_date = data.get('bail_date') or datetime.date.today()
        status = data.get('status', 'Pending')

        if not case_id or not amount:
            return jsonify({'message': 'Case ID and amount are required'}), 400

        # Check if the case exists
        case = db.query(Cases).get(case_id)
        if not case:
            return jsonify({'message': 'Case not found'}), 404

        # Create a new bail record
        new_bail = Bail(
            caseid=case_id,
            amount=Decimal(amount),
            baildate=bail_date,
            status=status
        )
        db.add(new_bail)
        db.commit()

        return jsonify({'message': 'Bail created successfully', 'bail_id': new_bail.bailid}), 201
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/bails/<int:bail_id>', methods=['GET'])
@login_required
def get_bail(bail_id):
    db = SessionLocal()
    try:
        bail = db.query(Bail).get(bail_id)
        if not bail:
            return jsonify({'message': 'Bail not found'}), 404

        return jsonify({
            'bail_id': bail.bailid,
            'case_id': bail.caseid,
            'amount': float(bail.amount),
            'bail_date': bail.baildate.isoformat(),
            'status': bail.status
        }), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/cases/<int:case_id>/bails', methods=['GET'])
@login_required
def get_bails_for_case(case_id):
    db = SessionLocal()
    try:
        bails = db.query(Bail).filter_by(caseid=case_id).all()
        result = [
            {
                'bail_id': b.bailid,
                'amount': float(b.amount),
                'bail_date': b.baildate.isoformat(),
                'status': b.status
            }
            for b in bails
        ]
        return jsonify({'bails': result}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        
@app.route('/api/bails/<int:bail_id>', methods=['PUT'])
@login_required
# @log_action(action_type = "UPDATE", entity_type = "Bails")
def update_bail(bail_id):
    db = SessionLocal()
    try:
        data = request.get_json()
        bail = db.query(Bail).get(bail_id)

        if not bail:
            return jsonify({'message': 'Bail not found'}), 404

        bail.amount = data.get('amount', bail.amount)
        bail.status = data.get('status', bail.status)
        bail.baildate = data.get('bail_date', bail.baildate)

        db.commit()
        return jsonify({'message': 'Bail updated successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        
@app.route('/api/bails/<int:bail_id>', methods=['DELETE'])
@login_required
# @log_action(action_type = "DELETE", entity_type = "Bails")
def delete_bail(bail_id):
    db = SessionLocal()
    try:
        bail = db.query(Bail).get(bail_id)
        if not bail:
            return jsonify({'message': 'Bail not found'}), 404

        db.delete(bail)
        db.commit()
        return jsonify({'message': 'Bail deleted successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

# Surety API
@app.route('/api/surety', methods=['POST'])
@login_required
# @log_action(action_type = "CREATE", entity_type = "Surety")
def create_surety():
    db = SessionLocal()
    try:
        data = request.get_json()
        surety = Surety(
            name=data.get('name'),
            cnic=data.get('cnic'),
            address=data.get('address'),
            relationship=data.get('relationship'),
            bailid=data.get('bailid')
        )
        db.add(surety)
        db.commit()
        return jsonify({'message': 'Surety created successfully'}), 201
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/surety/<int:surety_id>', methods=['GET'])
@login_required
def get_surety(surety_id):
    db = SessionLocal()
    try:
        surety = db.query(Surety).get(surety_id)
        if not surety:
            return jsonify({'message': 'Surety not found'}), 404

        return jsonify({
            'surety_id': surety.suretyid,
            'name': surety.name,
            'cnic': surety.cnic,
            'address': surety.address,
            'relationship': surety.relationship,
            'bailid': surety.bailid
        }), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/surety/<int:surety_id>', methods=['PUT'])
@login_required
# @log_action(action_type = "UPDATE", entity_type = "Surety")
def update_surety(surety_id):
    db = SessionLocal()
    try:
        data = request.get_json()
        surety = db.query(Surety).get(surety_id)

        if not surety:
            return jsonify({'message': 'Surety not found'}), 404

        surety.name = data.get('name', surety.name)
        surety.cnic = data.get('cnic', surety.cnic)
        surety.address = data.get('address', surety.address)
        surety.relationship = data.get('relationship', surety.relationship)

        db.commit()
        return jsonify({'message': 'Surety updated successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/surety/<int:surety_id>', methods=['DELETE'])
@login_required
# @log_action(action_type = "DELETE", entity_type = "Surety")
def delete_surety(surety_id):
    db = SessionLocal()
    try:
        surety = db.query(Surety).get(surety_id)
        if not surety:
            return jsonify({'message': 'Surety not found'}), 404

        db.delete(surety)
        db.commit()
        return jsonify({'message': 'Surety deleted successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

# CaseHistory API
@app.route('/api/cases/<int:case_id>/history', methods=['GET'])
@login_required
def get_case_history(case_id):
    db = SessionLocal()
    try:
        history = db.query(Casehistory).filter_by(caseid=case_id).all()
        result = [
            {
                'actiondate': h.actiondate.isoformat(),
                'actiontaken': h.actiontaken,
                'remarks': h.remarks
            }
            for h in history
        ]
        return jsonify({'history': result}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        

@app.route('/api/cases/<int:case_id>/history', methods=['POST'])
@login_required
# @log_action(action_type = "CREATE", entity_type = "CaseHistory")
def add_case_history(case_id):
    db = SessionLocal()
    try:
        data = request.get_json()
        action_taken = data.get('actiontaken')
        remarks = data.get('remarks')

        if not action_taken:
            return jsonify({'message': 'Action taken is required'}), 400

        # Check if the case exists
        case = db.query(Cases).get(case_id)
        if not case:
            return jsonify({'message': 'Case not found'}), 404

        # Add a new history entry
        new_history = Casehistory(
            caseid=case_id,
            actiondate=datetime.date.today(),
            actiontaken=action_taken,
            remarks=remarks
        )
        db.add(new_history)
        db.commit()

        return jsonify({'message': 'Case history added successfully'}), 201
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        
@app.route('/api/cases/history/<int:history_id>', methods=['PUT'])
@login_required
# @log_action(action_type = "UPDATE", entity_type = "CaseHistory")
def update_case_history(history_id):
    db = SessionLocal()
    try:
        data = request.get_json()
        history = db.query(Casehistory).get(history_id)

        if not history:
            return jsonify({'message': 'History entry not found'}), 404

        history.actiontaken = data.get('actiontaken', history.actiontaken)
        history.remarks = data.get('remarks', history.remarks)
        history.updatedat = datetime.datetime.utcnow()

        db.commit()
        return jsonify({'message': 'Case history updated successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        
@app.route('/api/cases/history/<int:history_id>', methods=['DELETE'])
@login_required
# @log_action(action_type = "DELETE", entity_type = "CaseHistory")
def delete_case_history(history_id):
    db = SessionLocal()
    try:
        history = db.query(Casehistory).get(history_id)

        if not history:
            return jsonify({'message': 'History entry not found'}), 404

        db.delete(history)
        db.commit()
        return jsonify({'message': 'Case history deleted successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        
#Evidence API
@app.route('/api/cases/<int:case_id>/evidence', methods=['POST'])
@login_required
# @log_action(action_type = "CREATE", entity_type = "Evidence")
def add_evidence(case_id):
    db = SessionLocal()
    try:
        data = request.get_json()
        evidencetype = data.get('evidencetype')
        description = data.get('description')
        filepath = data.get('filepath')  # Path to the uploaded file
        submitteddate = data.get('submitteddate') or datetime.date.today()

        if not evidencetype or not description:
            return jsonify({'message': 'Evidence type and description are required'}), 400

        # Check if the case exists
        case = db.query(Cases).get(case_id)
        if not case:
            return jsonify({'message': 'Case not found'}), 404

        # Add evidence
        new_evidence = Evidence(
            caseid=case_id,
            evidencetype=evidencetype,
            description=description,
            filepath=filepath,
            submitteddate=submitteddate
        )
        db.add(new_evidence)
        db.commit()

        return jsonify({'message': 'Evidence added successfully', 'evidence_id': new_evidence.evidenceid}), 201
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/cases/<int:case_id>/evidence', methods=['GET'])
@login_required
def get_evidence_for_case(case_id):
    db = SessionLocal()
    try:
        evidence = db.query(Evidence).filter_by(caseid=case_id).all()
        result = [
            {
                'evidence_id': e.evidenceid,
                'evidencetype': e.evidencetype,
                'description': e.description,
                'filepath': e.filepath,
                'submitteddate': e.submitteddate.isoformat()
            }
            for e in evidence
        ]
        return jsonify({'evidence': result}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        
@app.route('/api/evidence/<int:evidence_id>', methods=['PUT'])
@login_required
# @log_action(action_type = "UPDATE", entity_type = "Evidence")
def update_evidence(evidence_id):
    db = SessionLocal()
    try:
        data = request.get_json()
        evidence = db.query(Evidence).get(evidence_id)

        if not evidence:
            return jsonify({'message': 'Evidence not found'}), 404

        evidence.evidencetype = data.get('evidencetype', evidence.evidencetype)
        evidence.description = data.get('description', evidence.description)
        evidence.filepath = data.get('filepath', evidence.filepath)
        evidence.submitteddate = data.get('submitteddate', evidence.submitteddate)

        db.commit()
        return jsonify({'message': 'Evidence updated successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/evidence/<int:evidence_id>', methods=['DELETE'])
@login_required
# @log_action(action_type = "DELETE", entity_type = "Evidence")
def delete_evidence(evidence_id):
    db = SessionLocal()
    try:
        evidence = db.query(Evidence).get(evidence_id)
        if not evidence:
            return jsonify({'message': 'Evidence not found'}), 404

        db.delete(evidence)
        db.commit()
        return jsonify({'message': 'Evidence deleted successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        
#Witness API
@app.route('/api/cases/<int:case_id>/witnesses', methods=['POST'])
@login_required
# @log_action(action_type = "CREATE", entity_type = "Witnesses")
def add_witness(case_id):
    db = SessionLocal()
    try:
        data = request.get_json()
        firstname = data.get('firstname')
        lastname = data.get('lastname')
        cnic = data.get('cnic')
        phone = data.get('phone')
        email = data.get('email')
        address = data.get('address')
        statement = data.get('statement')
        statementdate = data.get('statementdate') or datetime.date.today()

        if not firstname or not lastname:
            return jsonify({'message': 'First name and last name are required'}), 400

        # Check if the case exists
        case = db.query(Cases).get(case_id)
        if not case:
            return jsonify({'message': 'Case not found'}), 404

        # Add witness
        new_witness = Witnesses(
            firstname=firstname,
            lastname=lastname,
            cnic=cnic,
            phone=phone,
            email=email,
            address=address,
            pasthistory=statement
        )
        db.add(new_witness)
        db.flush()

        # Link witness to the case
        witness_case = Witnesscase(
            caseid=case_id,
            witnessid=new_witness.witnessid,
            statement=statement,
            statementdate=statementdate
        )
        db.add(witness_case)
        db.commit()

        return jsonify({'message': 'Witness added successfully', 'witness_id': new_witness.witnessid}), 201
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        
@app.route('/api/cases/<int:case_id>/witnesses', methods=['GET'])
@login_required
def get_witnesses_for_case(case_id):
    db = SessionLocal()
    try:
        witnesses = (
            db.query(Witnesscase)
            .filter_by(caseid=case_id)
            .join(Witnesses, Witnesscase.witnessid == Witnesses.witnessid)
            .all()
        )
        result = [
            {
                'witness_id': w.witnessid,
                'firstname': w.firstname,
                'lastname': w.lastname,
                'cnic': w.cnic,
                'phone': w.phone,
                'email': w.email,
                'address': w.address,
                'statement': w.statement,
                'statementdate': w.statementdate.isoformat()
            }
            for w in witnesses
        ]
        return jsonify({'witnesses': result}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/witnesses/<int:witness_id>', methods=['PUT'])
@login_required
# @log_action(action_type = "UPDATE", entity_type = "Witnesses")
def update_witness(witness_id):
    db = SessionLocal()
    try:
        data = request.get_json()
        witness = db.query(Witnesses).get(witness_id)

        if not witness:
            return jsonify({'message': 'Witness not found'}), 404

        witness.firstname = data.get('firstname', witness.firstname)
        witness.lastname = data.get('lastname', witness.lastname)
        witness.cnic = data.get('cnic', witness.cnic)
        witness.phone = data.get('phone', witness.phone)
        witness.email = data.get('email', witness.email)
        witness.address = data.get('address', witness.address)
        witness.statement = data.get('statement', witness.statement)
        witness.statementdate = data.get('statementdate', witness.statementdate)

        db.commit()
        return jsonify({'message': 'Witness updated successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/witnesses/<int:witness_id>', methods=['DELETE'])
@login_required
# @log_action(action_type = "DELETE", entity_type = "Witnesses")
def delete_witness(witness_id):
    db = SessionLocal()
    try:
        witness = db.query(Witnesses).get(witness_id)
        if not witness:
            return jsonify({'message': 'Witness not found'}), 404

        db.delete(witness)
        db.commit()
        return jsonify({'message': 'Witness deleted successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()
        
# CaseDocument API
@app.route('/api/cases/<int:case_id>/documents', methods=['POST'])
@login_required
# @log_action(action_type = "CREATE (upload a doc)", entity_type = "Documents")
def upload_case_document(case_id):
    db = SessionLocal()
    try:
        file = request.files['file']
        filename = secure_filename(file.filename)
        filepath = os.path.join('uploads', filename)
        file.save(filepath)

        document = Documentcase(
            caseid=case_id,
            documenttitle=filename,
            filepath=filepath,
            submissiondate=datetime.date.today()
        )
        db.add(document)
        db.commit()
        return jsonify({'message': 'Document uploaded successfully', 'document_id': document.documentid}), 201
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/cases/<int:case_id>/documents', methods=['GET'])
@login_required
def get_case_documents(case_id):
    db = SessionLocal()
    try:
        documents = db.query(Documentcase).filter_by(caseid=case_id).all()
        result = [
            {
                'document_id': d.documentid,
                'documenttitle': d.documenttitle,
                'filepath': d.filepath,
                'submissiondate': d.submissiondate.isoformat()
            }
            for d in documents
        ]
        return jsonify({'documents': result}), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/documents/<int:document_id>', methods=['DELETE'])
@login_required
# @log_action(action_type = "DELETE", entity_type = "Documents")
def delete_case_document(document_id):
    db = SessionLocal()
    try:
        document = db.query(Documentcase).get(document_id)
        if not document:
            return jsonify({'message': 'Document not found'}), 404

        db.delete(document)
        db.commit()
        return jsonify({'message': 'Document deleted successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'message': str(e)}), 500
    finally:
        db.close()


if __name__ == "__main__":
    app.run(debug=True)
