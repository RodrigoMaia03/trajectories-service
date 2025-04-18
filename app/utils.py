import json
import pandas as pd
from bson import ObjectId
import geopandas as gpd
import movingpandas as mpd
from pymongo import MongoClient
from shapely.geometry import Point
from config import MONGODB_URI, DB_NAME, COLLECTION_TRAJ, COLLECTION_CAM

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
collection_traj = db[COLLECTION_TRAJ]

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return json.JSONEncoder.default(self, o)  


def fetch_trajectory_data_from_mongodb(query={}):
    # Busca dados do MongoDB e estrutura no formato equivalente ao CSV.
    data = []
    for doc in collection_traj.find(query):
        identifier = doc['identifier']
        category = doc['category']
        
        for point in doc['points']:
            # Converte timestamp ISO para epoch seconds (com decimal)
            timestamp = pd.to_datetime(point['timestamp']).timestamp()
            
            # Extrai x e y da geometria "POINT (x y)"
            geom_str = point['geometry'].split('(')[1].split(')')[0]
            x, y = map(float, geom_str.strip().split())
            
            data.append({
                'identifier': identifier,
                'category': category,
                'timestamp': timestamp,
                'x': x,
                'y': y
            })
    
    return pd.DataFrame(data)


def create_trajectory_collection_mongodb(query={}):
    # Cria um objeto TrajectoryCollection diretamente do MongoDB.
    df = fetch_trajectory_data_from_mongodb(query)
    
    # Cria geometrias Point e prepara GeoDataFrame
    df['geometry'] = df.apply(lambda row: Point(row.x, row.y), axis=1)
    df = df.drop(['x', 'y'], axis=1)
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
    
    # Converte timestamp e define como índice
    gdf['timestamp'] = pd.to_datetime(gdf['timestamp'], unit='s')
    gdf.set_index('timestamp', inplace=True)
    
    # Agrupa por identificador para criar trajetórias
    return mpd.TrajectoryCollection(gdf, 'identifier')


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}