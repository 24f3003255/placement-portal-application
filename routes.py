from flask import render_template, flash, request, redirect, url_for, session, abort, send_from_directory
from datetime import datetime
from app import app
from models import db, AdminUser, StudentProfile, CompanyAccount, JobDrive, JobApplication, Placement
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from datetime import date
from werkzeug.utils import secure_filename
import os
import uuid

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    email = request.form.get('email_address')
    password = request.form.get('password')
    if not email or not password:
        flash("Invalid credentials", "error")
        return redirect(url_for('login'))

    role = None
    user = None
    user = AdminUser.query.filter_by(email_address=email).first()
    if user and check_password_hash(user.password, password):
        role = "admin"

    if not role:
        user = StudentProfile.query.filter_by(email_address=email).first()
        if user and check_password_hash(user.password, password):

            if user.account_status != "Enabled":
                flash("Student account disabled by admin", "error")
                return redirect(url_for("login"))
            role = "student"

    if not role:
        user = CompanyAccount.query.filter_by(company_email=email).first()
        if user and check_password_hash(user.password, password):
            if user.verification_status != "Approved":
                flash("Company account pending admin approval", "error")
                return redirect(url_for("login"))
            if user.company_status != "Active":
                flash("Account has been blacklisted", "error")
                return redirect(url_for("login"))
            role = "company"

    if not role:
        flash("Invalid credentials", "error")
        return redirect(url_for('login'))
    user.last_login = datetime.utcnow()
    db.session.commit()
    session.clear()

    if role == "admin":
        session["user_id"] = user.a_id
    elif role == "student":
        session["user_id"] = user.SP_id
    else:
        session["user_id"] = user.CA_id
    session["role"] = role
    return redirect(url_for(f'{role}_dashboard'))


@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/register', methods=['POST'])
def register_post():
    role = request.form.get('role')
    name = request.form.get('name')
    email = request.form.get('email_address')
    password = request.form.get('password')

    if not role or not name or not email or not password:
        flash("All fields are required", "error")
        return redirect(url_for('register'))

    if role == 'student':
        if StudentProfile.query.filter_by(email_address=email).first():
            flash("Email already registered", "error")
            return redirect(url_for('register'))
        user = StudentProfile(
            student_name=name,
            email_address=email,
            password=generate_password_hash(password)
        )

    elif role == 'company':
        if CompanyAccount.query.filter_by(company_email=email).first():
            flash("Email already registered", "error")
            return redirect(url_for('register'))
        user = CompanyAccount(
            organization_name=name,
            company_email=email,
            password=generate_password_hash(password)
        )

    else:
        flash("Invalid registration type", "error")
        return redirect(url_for('register'))
    db.session.add(user)
    db.session.commit()
    flash("Registration successful.", "success")
    return redirect(url_for('login'))


@app.route("/admin/dashboard")
@login_required("admin")
def admin_dashboard():
    today = date.today()
    
    total_students = StudentProfile.query.count()
    total_companies = CompanyAccount.query.count()
    total_applications = JobApplication.query.count()
    total_drives = JobDrive.query.count()

    upcoming_drives = JobDrive.query.filter(
        JobDrive.last_date_to_apply >= today
    ).count()

    past_drives = JobDrive.query.filter(
        JobDrive.last_date_to_apply < today
    ).count()

    return render_template(
        "admin/dashboard.html",
        total_students=total_students,
        total_companies=total_companies,
        upcoming_drives=upcoming_drives,
        past_drives=past_drives,
        total_drives=total_drives,
        total_applications=total_applications
    )

@app.route("/student/dashboard")
@login_required("student")
def student_dashboard():
    return render_template("student/dashboard.html")

@app.route("/company/dashboard")
@login_required("company")
def company_dashboard():
    return render_template("company/dashboard.html")

@app.route('/admin/companies/manage_companies')
@login_required("admin")
def manage_companies():
    search = request.args.get('q')
    query = CompanyAccount.query
    if search:
        query = query.filter(
            CompanyAccount.organization_name.ilike(f"%{search}%") |
            CompanyAccount.industry_sector.ilike(f"%{search}%") |
            CompanyAccount.CA_id.ilike(f"%{search}%")
        )   
    companies = query.all()
    return render_template(
        'admin/companies/manage_companies.html',
        companies=companies
    )

@app.route('/admin/companies/approve/<string:CA_id>' , methods=['POST'])
@login_required("admin")
def approve_company(CA_id):
    company = CompanyAccount.query.get_or_404(CA_id)
    company.verification_status = 'Approved'
    db.session.commit()
    flash("Company account has been approved.", "success")
    return redirect(url_for('manage_companies'))

@app.route('/admin/companies/reject/<string:CA_id>' , methods=['POST'])
@login_required("admin")
def reject_company(CA_id):  
    company = CompanyAccount.query.get_or_404(CA_id)
    company.verification_status = 'Rejected'
    db.session.commit()
    flash("Company account has been rejected.", "success")
    return redirect(url_for('manage_companies'))

@app.route("/logout")
@login_required()
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route('/admin/students/manage_students')
@login_required("admin")
def manage_students():
    search = request.args.get('q')
    query = StudentProfile.query
    if search:
        query = query.filter(
            StudentProfile.student_name.ilike(f"%{search}%") |
            StudentProfile.email_address.ilike(f"%{search}%") |
            (StudentProfile.SP_id == int(search) if search.isdigit() else False)
        )   
    students = query.all()
    return render_template('admin/students/manage_students.html', students=students)

@app.route('/admin/drives/manage_drives')
@login_required("admin")
def manage_drives():
    search = request.args.get('q', '').strip()
    today = date.today()
    query = JobDrive.query
    if search:
        query = query.filter(JobDrive.job_title.ilike(f"%{search}%") |JobDrive.role_description.ilike(f"%{search}%"))
    upcoming_drives = query.filter(JobDrive.last_date_to_apply >= today).all()
    past_drives = query.filter(JobDrive.last_date_to_apply < today).all()
    return render_template(
        'admin/drives/manage_drives.html',
        upcoming_drives=upcoming_drives,
        past_drives=past_drives
    )

@app.route('/admin/applications/manage_applications')
@login_required("admin")
def manage_applications():
    search = request.args.get('q')
    query = JobApplication.query
    if search:
        query = query.filter(
            JobApplication.student_id.ilike(f"%{search}%") |
            JobApplication.drive_id.ilike(f"%{search}%") |
            JobApplication.application_status.ilike(f"%{search}%")
        )
    applications = query.all()
    return render_template('admin/applications/manage_applications.html', applications=applications)

@app.route('/admin/students/enable/<int:SP_id>' , methods=['POST'])
@login_required("admin")
def enable_student(SP_id):
    student = StudentProfile.query.get_or_404(SP_id)
    student.account_status = 'Enabled'
    db.session.commit()
    flash("Student account has been enabled.", "success")
    return redirect(url_for('manage_students'))

@app.route('/admin/students/disable/<int:SP_id>' , methods=['POST'])
@login_required("admin")
def disable_student(SP_id):
    student = StudentProfile.query.get_or_404(SP_id)
    student.account_status = 'Disabled'
    db.session.commit()
    flash("Student account has been disabled.", "success")
    return redirect(url_for('manage_students'))

@app.route('/admin/companies/blacklist/<string:CA_id>', methods=['POST'])
@login_required("admin")
def blacklist_company(CA_id):
    company = CompanyAccount.query.get_or_404(CA_id)
    company.company_status = 'Blacklisted'
    db.session.commit()
    flash("Company account has been blacklisted.", "success")
    return redirect(url_for('manage_companies'))

@app.route('/admin/companies/activate/<string:CA_id>', methods=['POST'])
@login_required("admin")
def activate_company(CA_id):
    company = CompanyAccount.query.get_or_404(CA_id)
    company.company_status = 'Active'
    db.session.commit()
    flash("Company account has been activated.", "success")
    return redirect(url_for('manage_companies'))

@app.route('/admin/drives/enable/<string:JD_id>' , methods=['POST'])
@login_required("admin")
def enable_drive(JD_id):
    drive = JobDrive.query.get_or_404(JD_id)
    drive.drive_status_admin = 'Enabled'
    db.session.commit()
    flash("Drive has been enabled.", "success")
    return redirect(url_for('manage_drives'))

@app.route('/admin/drives/disable/<string:JD_id>' , methods=['POST'])
@login_required("admin")
def disable_drive(JD_id):
    drive = JobDrive.query.get_or_404(JD_id)
    drive.drive_status_admin = 'Disabled'
    db.session.commit()
    flash("Drive has been disabled.", "success")
    return redirect(url_for('manage_drives'))