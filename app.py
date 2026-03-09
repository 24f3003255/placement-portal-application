from flask import Flask, session
from config import Config
from models import db, create_default_admin

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

@app.context_processor
def inject_user_roles():
    role = session.get("role")
    return dict(
        admin=role == "admin",
        student=role == "student",
        company=role == "company"
    )

import routes

with app.app_context():
    db.create_all()
    create_default_admin()
    
if __name__ == "__main__":
    app.run(debug=True)