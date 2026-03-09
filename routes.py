from flask import render_template, flash, request, redirect, url_for, session, abort, send_from_directory, current_app
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

@app.route('/', methods=['GET','POST'])
def index():
    search = request.args.get('search')
    if search:
        students = StudentProfile.query.filter(
            (StudentProfile.student_name.contains(search)) |
            (StudentProfile.SP_id.contains(search))
        ).all()
        companies = CompanyAccount.query.filter(
            (CompanyAccount.organization_name.contains(search)) |
            (CompanyAccount.CA_id.contains(search))
        ).all()
    else:
        students = StudentProfile.query.all()
        companies = CompanyAccount.query.all()
    return render_template(
        "index.html",
        students=students,
        companies=companies
    )

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
    auto_close_drives()
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
    auto_close_drives()
    company = CompanyAccount.query.get(session["user_id"])
    jobs = JobDrive.query.filter_by(company_id=company.CA_id).all()
    total_jobs = len(jobs)
    active_jobs = sum(1 for j in jobs if j.drive_status == "Active")
    closed_jobs = sum(1 for j in jobs if j.drive_status == "Closed")
    applications = (JobApplication.query.join(JobDrive).filter(JobDrive.company_id == company.CA_id).all())
    total_applications = len(applications)
    shortlisted = sum(1 for a in applications if a.application_status in ("Shortlisted"))
    if not company.profile_completed:
        return redirect(url_for("company_update_profile"))
    return render_template("company/dashboard.html",
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        closed_jobs=closed_jobs,
        total_applications=total_applications,
        shortlisted=shortlisted)

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

@app.route("/company/drives")
@login_required("company")
def company_drives():
    company_id = session["user_id"]
    drives = (JobDrive.query.filter_by(company_id=company_id).order_by(JobDrive.posted_on.desc()).all())
    return render_template("company/drives.html", drives=drives)

@app.route("/company/drives/<string:drive_id>/applications")
@login_required("company")
def view_drive_applications(drive_id):
    company_id = session["user_id"]
    drive = JobDrive.query.filter_by(JD_id=drive_id,company_id=company_id).first_or_404()
    applications = (JobApplication.query.filter_by(drive_id=drive_id).order_by(JobApplication.applied_on.desc()).all())
    return render_template("company/applications.html",drive=drive,applications=applications)

@app.route("/company/application/<int:app_id>/<string:status>", methods=["POST"])
@login_required("company")
def update_application_status(app_id, status):
    allowed_status = ["Shortlisted", "Interview", "Rejected", "Placed"]
    if status not in allowed_status:
        abort(400)
    application = JobApplication.query.get_or_404(app_id)
    if application.drive.company_id != session["user_id"]:
        abort(403)
    application.application_status = status
    if status == "Placed":
        placement = Placement.query.filter_by(application_id=application.JA_id).first()
        if placement:
            placement.placement_status = "Placed"
        else:
            placement = Placement(
                student_id=application.student_id,
                company_id=application.drive.company_id,
                drive_id=application.drive_id,
                application_id=application.JA_id,
                package_offered=None,
                placement_status="Placed"
            )
            db.session.add(placement)
    db.session.commit()
    return redirect(url_for("view_drive_applications", drive_id=application.drive_id))

@app.route("/company/create_jobs", methods=["GET","POST"])
@login_required("company")
def create_job_drive():
    company = CompanyAccount.query.get(session["user_id"])
    if company.verification_status != "Approved":
        flash("Your company is not approved by admin yet.","danger")
        return redirect(url_for("company_dashboard"))
    if request.method == "POST":
        drive = JobDrive(
            company_id=company.CA_id,
            job_title=request.form["job_title"],
            job_type=request.form["job_type"],
            location=request.form["location"],
            role_description=request.form["role_description"],
            skills_required=request.form["skills_required"],
            eligibility_details=request.form["experience"],
            salary_package=request.form["salary_package"],
            vacancies=int(request.form["vacancies"]),
            last_date_to_apply=datetime.strptime(request.form["last_date_to_apply"],"%Y-%m-%d").date(),
            drive_status="Active"
        )
        db.session.add(drive)
        db.session.commit()
        flash("Job drive posted successfully","success")
        return redirect(url_for("company_dashboard"))
    return render_template("company/create_jobs.html")

@app.route("/company/drives/close/<string:JD_id>",methods=["POST"])
@login_required("company")
def close_drive(JD_id):
    drive = JobDrive.query.get_or_404(JD_id)
    if drive.company_id != session["user_id"]:
        abort(403)
    drive.drive_status = "Closed"
    db.session.commit()
    flash("Drive closed successfully","success")
    return redirect(url_for("company_drives"))

@app.route("/company/drives/activate/<string:JD_id>",methods=["POST"])
@login_required("company")
def activate_drive(JD_id):
    drive = JobDrive.query.get_or_404(JD_id)
    if drive.company_id != session["user_id"]:
        abort(403)
    drive.drive_status = "Active"
    db.session.commit()    
    flash("Drive activated successfully","success")
    return redirect(url_for("company_drives"))

@app.route("/student/update_profile", methods=["GET","POST"])
@login_required("student")
def student_update_profile():
    student= StudentProfile.query.get_or_404(session["user_id"])
    if request.method == "POST":
        student.student_name = request.form["student_name"]
        student.email_address = request.form["email_address"]
        student.contact_number = request.form["contact_number"]
        student.branch = request.form["branch"]
        student.academic_year = request.form["academic_year"]
        student.cgpa = float(request.form["cgpa"])
        resume_file = request.files.get("resume_file")
        if resume_file and resume_file.filename != "":
            if resume_file.filename.lower().endswith((".pdf", ".doc", ".docx")):
                filename = f"{uuid.uuid4()}_{secure_filename(resume_file.filename)}"
                resume_path = os.path.join("static/resumes", filename)
                os.makedirs("static/resumes", exist_ok=True)
                resume_file.save(resume_path)
                student.resume_file = filename
            else:
                flash("Only PDF or Word documents can be attached.", "danger")
        student.educational_qualifications = request.form["educational_qualifications"]
        student.skills = request.form["skills"]
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("student_update_profile"))
    return render_template("student/update_profile.html")

@app.route("/company/update_profile", methods=["GET", "POST"])
@login_required("company")
def company_update_profile():
    company = CompanyAccount.query.get(session["user_id"])
    if company.profile_completed:
        return redirect(url_for("company_dashboard"))
    if request.method == "POST":
        company.industry_sector = request.form["industry_sector"]
        company.hr_contact_name = request.form["hr_contact_name"]
        company.hr_contact_phone = request.form["hr_contact_phone"]
        company.hr_contact_email = request.form["hr_contact_email"]
        company.company_website = request.form["company_website"]
        company.profile_completed = True
        db.session.commit()
        flash("Profile updated successfully", "success")
        return redirect(url_for("company_dashboard"))
    return render_template("company/update_profile.html")

def auto_close_drives():
    JobDrive.query.filter(
        JobDrive.last_date_to_apply < date.today(),
        JobDrive.drive_status == "Active"
    ).update({"drive_status": "Closed"})
    db.session.commit()

from flask import render_template, session
from models import db, JobApplication, StudentProfile, JobDrive

@app.route("/company/shortlisted_applications")
@login_required()
def company_shortlisted_applications():
    company_id = session["user_id"]
    applications = (
        db.session.query(JobApplication, StudentProfile, JobDrive)
        .join(StudentProfile, JobApplication.student_id == StudentProfile.SP_id)
        .join(JobDrive, JobApplication.drive_id == JobDrive.JD_id)
        .filter(JobDrive.company_id == company_id)
        .filter(JobApplication.application_status == "Shortlisted")
        .order_by(JobApplication.applied_on.desc())
        .all()
    )
    return render_template(
        "company/shortlisted_applications.html",
        applications=applications
    )

@app.route("/uploads/resumes/<filename>")
def view_resume(filename):
    resume_folder = os.path.join(current_app.root_path, "static", "resumes")
    file_path = os.path.join(resume_folder, filename)
    if not os.path.exists(file_path):
        abort(404)
    return send_from_directory(resume_folder, filename, as_attachment=False)

@app.route("/profile/student/<int:student_id>")
@login_required()
def view_student_profile(student_id):
    student = StudentProfile.query.get_or_404(student_id)
    return render_template(
        "view_student_profile.html",
        student=student
    )

@app.route("/student/show_drives")
@login_required("student")
def student_jobs():
    auto_close_drives()
    student_id = session["user_id"]
    applied_ids = {a.drive_id for a in JobApplication.query.filter_by(student_id=student_id).all()}
    search = request.args.get("q", "").strip()
    if search:
        jobs = (JobDrive.query.join(CompanyAccount).filter(JobDrive.drive_status == "Active",JobDrive.drive_status_admin == "Enabled", JobDrive.job_title.contains(search)).all())
    else:
        jobs = (JobDrive.query.join(CompanyAccount).filter(JobDrive.drive_status == "Active",JobDrive.drive_status_admin == "Enabled").all())
    return render_template(
        "student/show_drives.html",
        jobs=jobs,
        applied_ids=applied_ids,
        search=search
    )

@app.route("/student/jobs/<string:JD_id>/apply", methods=["GET","POST"])
@login_required("student")
def apply_job(JD_id):
    student_id = session["user_id"]
    if request.method == "GET":
        job = JobDrive.query.get_or_404(JD_id)
        if JobApplication.query.filter_by(student_id=student_id,drive_id=JD_id).first():
            flash("You have already applied for this job","warning")
            return redirect(url_for("student_applications_status"))
        return render_template("student/application.html",job=job)
    if request.method == "POST":
        cover_letter = request.form["cover_letter"]
        why_join = request.form["why_join"]
        application = JobApplication(
            student_id=student_id,
            drive_id=JD_id,
            cover_letter=cover_letter,
            why_join=why_join
        )
        db.session.add(application)
        db.session.commit()
        flash("Applied successfully!","success")
        return redirect(url_for("student_applications_status"))

@app.route("/student/applications_status")
@login_required("student")
def student_applications_status():
    student_id = session["user_id"]
    applications = (
        JobApplication.query
        .join(JobDrive)
        .join(CompanyAccount)
        .filter(JobApplication.student_id == student_id)
        .order_by(JobApplication.applied_on.desc())
        .all()
    )
    return render_template(
        "student/applications_status.html",
        applications=applications
    )

@app.route("/student/placement_history")
@login_required("student")
def placement_history():
    placements = Placement.query.filter_by(student_id=session["user_id"]).all()
    return render_template("student/placement_history.html", placements=placements)

@app.route("/student/placement_history")
@app.route("/student/placement_history")
@login_required("student")
def student_placement_history():
    student_id = session["user_id"]
    placements = (
        db.session.query(Placement, CompanyAccount, JobDrive)
        .join(CompanyAccount, Placement.company_id == CompanyAccount.CA_id)
        .join(JobDrive, Placement.drive_id == JobDrive.JD_id)
        .filter(Placement.student_id == student_id)
        .order_by(Placement.joined_date.desc())
        .all()
    )
    return render_template("student/placement_history.html", placements=placements)

@app.route("/company/update_package/<int:app_id>", methods=["POST"])
@login_required("company")
def update_package(app_id):
    application = JobApplication.query.get_or_404(app_id)
    if application.drive.company_id != session["user_id"]:
        abort(403)
    package = request.form["package"]
    if application.placement is None:
        placement = Placement(
            student_id=application.student_id,
            company_id=application.drive.company_id,
            drive_id=application.drive_id,
            application_id=application.JA_id,
            package_offered=package
        )
        db.session.add(placement)
    else:
        application.placement.package_offered = package
    db.session.commit()
    flash("Package updated successfully", "success")
    return redirect(url_for("view_drive_applications", drive_id=application.drive_id))