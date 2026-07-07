import os


# os.system('pip install -r requirements.txt')

from app import app
app.run(debug=os.path.exists('DEBUG'), host='::', port=8100)

