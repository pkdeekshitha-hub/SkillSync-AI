from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt

# Created here (not in app.py) so models.py and routes can import
# them without circular-import issues.
db = SQLAlchemy()
jwt = JWTManager()
bcrypt = Bcrypt()
