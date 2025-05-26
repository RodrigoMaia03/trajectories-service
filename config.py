import os

# Configurações do aplicativo Flask
DEBUG = True
TESTING = False
# SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Configurações do MongoDB
MONGODB_URI = os.getenv("MONGO_URI", "mongodb://mongo_db:27017/")
DB_NAME = "smart-trajectories"
COLLECTION_TRAJ = "trajectories"
COLLECTION_CAM = "cameras"

# Configurações de diretórios
INPUT_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data', 'input_data', 'txt')
INPUT_DATA_DIR2 = os.path.join(os.path.dirname(__file__), 'data', 'input_data', 'img')
OUTPUT_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data', 'output_data', 'csv')
OUTPUT_DATA_DIR2 = os.path.join(os.path.dirname(__file__), 'data', 'output_data', 'json')

# Cria os diretórios se não existirem
os.makedirs(INPUT_DATA_DIR, exist_ok=True)
os.makedirs(INPUT_DATA_DIR2, exist_ok=True)
os.makedirs(OUTPUT_DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DATA_DIR2, exist_ok=True)