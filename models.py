from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import time
from werkzeug.security import generate_password_hash
db = SQLAlchemy()

class AdminUser(db.Model):
    __tablename__ = "admin_users"
    a_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email_address = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

class StudentProfile(db.Model):
    __tablename__ = "student_profiles"
    SP_id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(120), nullable=False)
    email_address = db.Column(db.String(150), unique=True, nullable=False)
    contact_number = db.Column(db.String(20))
    branch = db.Column(db.String(100))
    academic_year = db.Column(db.Integer)
    educational_qualifications = db.Column(db.Text)
    skills = db.Column(db.Text)
    cgpa = db.Column(db.Float)
    resume_file = db.Column(db.String(200), nullable=True)
    account_status = db.Column(db.String(20), default="Enabled")
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    applications = db.relationship("JobApplication",backref="student",lazy=True,cascade="all, delete")
    placements = db.relationship("Placement", backref="student", lazy=True)

def generate_company_id():
    return f"COM{int(time.time())}"

class CompanyAccount(db.Model):
    __tablename__ = "company_accounts"
    CA_id = db.Column(db.String(20), primary_key=True, default=generate_company_id)
    organization_name = db.Column(db.String(150), nullable=False)
    industry_sector = db.Column(db.String(100))
    company_email = db.Column(db.String(150), unique=True, nullable=False)
    hr_contact_name = db.Column(db.String(100))
    hr_contact_phone = db.Column(db.String(20))
    hr_contact_email = db.Column(db.String(150))
    company_website = db.Column(db.String(200))
    verification_status = db.Column(db.String(20), default="Pending")
    company_status = db.Column(db.String(20), default="Active")
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    profile_completed = db.Column(db.Boolean, default=False)
    drives = db.relationship("JobDrive",back_populates="company",cascade="all, delete")


def generate_job_drive_id():
    return f"JD{int(time.time())}"

class JobDrive(db.Model):
    __tablename__ = "job_drives"
    JD_id = db.Column(db.String(20), primary_key=True , default=generate_job_drive_id)
    company_id = db.Column(db.String(20), db.ForeignKey("company_accounts.CA_id"), nullable=False)
    company = db.relationship("CompanyAccount",back_populates="drives")
    job_title = db.Column(db.String(150), nullable=False)
    job_type = db.Column(db.String(50))
    location = db.Column(db.String(100))
    role_description = db.Column(db.Text)
    eligibility_details = db.Column(db.Text)
    skills_required = db.Column(db.Text)
    salary_package = db.Column(db.String(50))
    vacancies = db.Column(db.Integer, default=1)
    last_date_to_apply = db.Column(db.Date, nullable=False)
    drive_status_admin = db.Column(db.String(20), default="Disabled")
    drive_status = db.Column(db.String(20), default="Active")
    posted_on = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
    applications = db.relationship("JobApplication",backref="drive",lazy=True,cascade="all, delete")

class JobApplication(db.Model):
    __tablename__ = "job_applications"
    JA_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student_profiles.SP_id"), nullable=False)
    drive_id = db.Column(db.String(20), db.ForeignKey("job_drives.JD_id"), nullable=False)
    applied_on = db.Column(db.DateTime, default=datetime.utcnow)
    application_status = db.Column(db.String(20), default="Applied")
    applied_cgpa = db.Column(db.Float)
    applied_branch = db.Column(db.String(100))
    cover_letter = db.Column(db.Text)
    why_join = db.Column(db.Text)
    __table_args__ = (db.UniqueConstraint("student_id", "drive_id", name="uq_student_drive"),)

class Placement(db.Model):
    __tablename__ = "placements"
    PL_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student_profiles.SP_id"), nullable=False)
    company_id = db.Column(db.String(20),db.ForeignKey("company_accounts.CA_id"),nullable=False)
    drive_id = db.Column(db.String(20),db.ForeignKey("job_drives.JD_id"),nullable=False)
    application_id = db.Column(db.Integer,db.ForeignKey("job_applications.JA_id"),nullable=False,unique=True)
    package_offered = db.Column(db.String(50))
    offer_letter_link = db.Column(db.Text)
    placement_status = db.Column(db.String(20), default="Placed")
    joined_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def create_default_admin():
    admin = AdminUser.query.filter_by(email_address="admin@admin.com").first()
    if not admin:
        default_admin = AdminUser(full_name="Placement Admin",email_address="admin@admin.com",password=generate_password_hash("admin"))
        db.session.add(default_admin)
        db.session.commit()
        