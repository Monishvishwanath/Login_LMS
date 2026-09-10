# requirements are:
fastapi>=0.100.0
uvicorn>=0.22.0
jinja2>=3.1.0
pandas>=2.0.0
openpyxl>=3.1.0
python-multipart>=0.0.6
bcrypt==4.0.1
sqlalchemy>=2.0.0
pydantic>=2.0.0

# installations:
pip install fastapi uvicorn pandas openpyxl jinja2 python-multipart "bcrypt==4.0.1"

# Initialize the Database:
python init_db.py

# Run the Application:
uvicorn main:app --reload

# Open your browser and navigate to http://127.0.0.1:8000

# Default Credentials:
Manager Account: admin / admin123
Employee Account: john / john123
