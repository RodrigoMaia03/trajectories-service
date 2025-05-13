from flask import render_template, request, send_file, jsonify, current_app
from werkzeug.utils import secure_filename
import os
import io
import json
import matplotlib
import base64
import matplotlib.pyplot as plt
from app import create_app
from pymongo import MongoClient
from shapely import wkt
from datetime import datetime
from shapely.errors import ShapelyError
from functools import wraps
from flask.json.provider import DefaultJSONProvider
from app.utils import JSONEncoder, create_trajectory_collection_mongodb, allowed_file
from smart_traject.smart_trajectories.convert import txt_to_csv, txt_to_csv_datetime
from smart_traject.smart_trajectories.processing import generate_trajectory_collection
from smart_traject.smart_trajectories.plot import plot_trajectories_with_background, plot_trajectories_one_category_background, plot_trajectories_with_stop_in_rectangle
from smart_traject.smart_trajectories.plot import plot_trajectories_with_limits, plot_trajectories_with_start_finish, plot_trajectories_with_stopped, plot_trajectories_in_monitored_area
from config import INPUT_DATA_DIR, INPUT_DATA_DIR2, OUTPUT_DATA_DIR, OUTPUT_DATA_DIR2, MONGODB_URI, DB_NAME, COLLECTION_TRAJ, COLLECTION_CAM

matplotlib.use('Agg')

# Decorador para tratamento de erros nas rotas Flask
def handle_plot_errors(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            return jsonify({'status': 'error', 'message': str(e)}), 400
        except Exception as e:
            current_app.logger.error(f"Error in {f.__name__}: {str(e)}", exc_info=True)
            return jsonify({'status': 'error', 'message': 'Erro interno'}), 500
    return decorator

class UTF8JSONProvider(DefaultJSONProvider):
    ensure_ascii = False

# Configura o MongoDB
client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
collection_traj = db[COLLECTION_TRAJ]
collection_cam = db[COLLECTION_CAM]

#Cria a aplicação Flask
app = create_app() 
app.json = UTF8JSONProvider(app)
app.config.update(JSON_AS_ASCII=False, JSONIFY_PRETTYPRINT_REGULAR=True)

@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')

@app.route('/cam', methods=['GET'])
def camera():
    return render_template('cam.html')

@app.route('/convert', methods=['GET'] )
def converter():
    return render_template('convert.html')

@app.route('/howtouse', methods=['GET'] )
def howtouse():
    return render_template('howtouse.html')

@app.route('/register_camera', methods=['POST'])
def register_camera():
    try:
        name = request.form['name']
        image = request.files['image']
        
        # Verificação básica dos campos
        if 'name' not in request.form or 'image' not in request.files:
            return jsonify({'status': 'error', 'message': 'Campos obrigatórios ausentes'}), 400

        # Verificação de formato
        if not allowed_file(image.filename):
            return jsonify({'status': 'error', 'message': 'Apenas JPG, JPEG e PNG são permitidos'}), 400

        # Verificação de duplicatas
        if collection_cam.find_one({'name': name}):
            return jsonify({'status': 'error', 'message': f'Câmera {name} já existe'}), 409

        # Nome seguro com timestamp para evitar colisões
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{secure_filename(name)}_{timestamp}{os.path.splitext(image.filename)[1]}"
        image_path = os.path.join(INPUT_DATA_DIR2, filename)
        image.save(image_path)

        # Estrutura do Documento no MongoDB 
        camera_data = {
            "name": name,
            "image_path": image_path,
            "created_at": datetime.now(),
            "metadata": {
                "coordinate_system": "pixel",
                "resolution": "native"
            }
        }

        # Inserindo no MongoDb
        result = collection_cam.insert_one(camera_data)

        # Controle de transação e resposta
        if not result.inserted_id:
            return jsonify({'status': 'error', 'message': 'Erro ao inserir no banco'}), 500

        return jsonify({
            'status': 'success',
            'message': 'Câmera registrada',
            'camera_id': str(result.inserted_id),
            'image_path': image_path
        }), 201

    except Exception as e:
        current_app.logger.error(f"Erro no registro de câmera: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Erro interno'}), 500


@app.route('/upload_txt_to_csv', methods=['POST'])
def upload_txt_to_csv():
    if 'file' not in request.files:
        return jsonify({
            'status': 'error',
            'message': 'Nenhum arquivo enviado'
        }), 400
    
    camera = request.form.get('camera')
    txt_file = request.files['file']
    
    if txt_file.filename == '':
        return jsonify({
            'status': 'error',
            'message': 'Campo nome vazio'
        }), 400
    
    if not collection_cam.find_one({'name': camera}):
        return jsonify({
            'status': 'error',
            'message': f'Câmera {camera} não cadastrada'
        }), 400

    # Salva o arquivo .txt
    txt_filename = secure_filename(txt_file.filename)
    txt_file_path = os.path.join(INPUT_DATA_DIR, txt_filename)
    txt_file.save(txt_file_path)

    # Define caminhos dos arquivos
    csv_filename = os.path.splitext(txt_filename)[0] + '_converted.csv'
    csv_file_path = os.path.join(OUTPUT_DATA_DIR, csv_filename)
    
    try:
        # Conversão para CSV
        txt_to_csv(txt_file_path, csv_file_path)
        
        # Geração da coleção de trajetórias
        traj_collection = generate_trajectory_collection(csv_file_path)
        
        # Lista para armazenar documentos do MongoDB
        mongo_docs = []
        
        # Processa cada trajetória
        for traj in traj_collection:
            trajectory_data = {
                "identifier": traj.id,
                "category": traj.df['category'].iloc[0],
                "start_time": traj.get_start_time().isoformat(),
                "end_time": traj.get_end_time().isoformat(),
                "geometry": traj.to_linestring().wkt,
                "background": camera,
                "points": [
                    {
                        "timestamp": row.name.isoformat(),
                        "geometry": row.geometry.wkt   
                    }
                    for _, row in traj.df.iterrows()
                ]
            }
            mongo_docs.append(trajectory_data)
        
        # Insere no MongoDB
        if mongo_docs:
            collection_traj.insert_many(mongo_docs)
        
        # Cria e retorna o JSON
        json_filename = os.path.splitext(txt_filename)[0] + '_converted.json'
        json_file_path = os.path.join(OUTPUT_DATA_DIR2, json_filename)
        
        with open(json_file_path, 'w') as f:
            json.dump(mongo_docs, f, cls=JSONEncoder)
        
        return send_file(json_file_path, as_attachment=True)
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Erro ao processar o arquivo: {str(e)}'
        }), 500


@app.route('/upload_txt_to_csv_datetime', methods=['POST'])
def upload_txt_to_csv_datetime():
    if 'file' not in request.files:
        return jsonify({
            'status': 'error',
            'message': 'Nenhum arquivo enviado'
        }), 400
    
    camera = request.form.get('camera')
    txt_file = request.files['file']
    
    if txt_file.filename == '':
        return jsonify({
            'status': 'error',
            'message': 'Campo nome vazio'
        }), 400
    
    if not collection_cam.find_one({'name': camera}):
        return jsonify({
            'status': 'error',
            'message': f'Câmera {camera} não cadastrada'
        }), 400

    # Salva o arquivo .txt
    txt_filename = secure_filename(txt_file.filename)
    txt_file_path = os.path.join(INPUT_DATA_DIR, txt_filename)
    txt_file.save(txt_file_path)

    # Define caminhos dos arquivos
    csv_filename = os.path.splitext(txt_filename)[0] + '_converted_datetime.csv'
    csv_file_path = os.path.join(OUTPUT_DATA_DIR, csv_filename)
    
    try:
        # Conversão para CSV com datetime
        txt_to_csv_datetime(txt_file_path, csv_file_path)
        
        # Geração da coleção de trajetórias
        traj_collection = generate_trajectory_collection(csv_file_path)
        
        # Lista para documentos do MongoDB
        mongo_docs = []
      
        # Processa cada trajetória
        for traj in traj_collection:
            trajectory_data = {
                "identifier": traj.id,
                "category": traj.df['category'].iloc[0],
                "start_time": traj.get_start_time().isoformat(),
                "end_time": traj.get_end_time().isoformat(),
                "geometry": traj.to_linestring().wkt,
                "background": camera,
                "points": [
                    {
                        "timestamp": row.name.isoformat(),
                        "geometry": row.geometry.wkt   
                    }
                    for _, row in traj.df.iterrows()
                ]
            }
            mongo_docs.append(trajectory_data)
        
        # Insere no MongoDB
        if mongo_docs:
            collection_traj.insert_many(mongo_docs)
        
        # Cria e retorna o JSON
        json_filename = os.path.splitext(txt_filename)[0] + '_converted_datetime.json'
        json_file_path = os.path.join(OUTPUT_DATA_DIR2, json_filename)
        
        with open(json_file_path, 'w') as f:
            json.dump(mongo_docs, f, cls=JSONEncoder)
        
        return send_file(
            json_file_path,
            as_attachment=True,
            download_name=json_filename
        )
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Erro ao processar o arquivo: {str(e)}'
        }), 500    


@app.route('/plot_with_background', methods=['POST'])
@handle_plot_errors
def plot_with_background():
    buffer = io.BytesIO()
    
    # Obter nome da câmera
    camera = request.form.get('camera')
    if not camera:
        return jsonify({'status': 'error', 'message': 'Nome da câmera obrigatório'}), 400

    # Buscar imagem da câmera no banco de dados
    camera_data = collection_cam.find_one({'name': camera})
    if not camera_data:
        return jsonify({'status': 'error', 'message': f'Câmera {camera} não encontrada'}), 404

    image_path = camera_data.get('image_path')
    if not image_path or not os.path.isfile(image_path):
        return jsonify({'status': 'error', 'message': 'Imagem da câmera não disponível'}), 404

    # Restante dos parâmetros
    selectedDate = request.form.get('selected_date')
    if not selectedDate:
        return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400

    try:
        datetime.strptime(selectedDate, '%Y-%m-%d')
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400

    # Construção da query
    query = {}
    
    try:
        startTime = float(request.form.get('start_time', 0))
        endTime = float(request.form.get('end_time', 24))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Valores de tempo inválidos'}), 400

    if selectedDate:
        hours_init = int(startTime)
        minutes_init = int((startTime - hours_init) * 60)
        hours_end = int(endTime)
        minutes_end = int((endTime - hours_end) * 60)
        query_date_start = f"{selectedDate}T{hours_init:02}:{minutes_init:02}:00"
        query_date_end = f"{selectedDate}T{hours_end:02}:{minutes_end:02}:00"
        query["start_time"] = {"$lte": query_date_end}
        query["end_time"] = {"$gte": query_date_start}
        
    if camera:
        query["background"] = camera


    # Parâmetros do plot
    try:
        plot_params = {
            'xsize': float(request.form.get('xsize', 10)),
            'ysize': float(request.form.get('ysize', 10)),
            'xlim1': float(request.form.get('xlim1', 0)),
            'xlim2': float(request.form.get('xlim2', 100)),
            'ylim1': float(request.form.get('ylim1', 0)),
            'ylim2': float(request.form.get('ylim2', 100)),
	        'min_x': min(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'max_x': max(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'min_y': min(float(request.form.get('ylim1')), float(request.form.get('ylim2'))),
            'max_y': max(float(request.form.get('ylim1')), float(request.form.get('ylim2')))
        }
    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400

    try:
        # Buscar trajetórias
        traj_collection = create_trajectory_collection_mongodb(query)
        
        if not traj_collection:
            return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada para o período'}), 404

        # Gerar plot com imagem do banco
        result = plot_trajectories_with_background(
            traj_collection,
            image_path,
            **plot_params
        )
        
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
        plt.close()
        buffer.seek(0)
        
        return jsonify({
            "status": "success",
            "image": base64.b64encode(buffer.getvalue()).decode('utf-8'),
            "metrics": {
                "summary": result
            }
        })

    except Exception as e:
        current_app.logger.error(f"Erro no plot: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}', 'metrics': None}), 500


@app.route('/plot_one_category', methods=['POST'])
@handle_plot_errors
def plot_one_category():
    buffer = io.BytesIO()
    
    # Obter nome da câmera
    camera = request.form.get('camera')
    if not camera:
        return jsonify({'status': 'error', 'message': 'Nome da câmera obrigatório'}), 400

    # Buscar imagem da câmera no banco de dados
    camera_data = collection_cam.find_one({'name': camera})
    if not camera_data:
        return jsonify({'status': 'error', 'message': f'Câmera {camera} não encontrada'}), 404

    image_path = camera_data.get('image_path')
    if not image_path or not os.path.isfile(image_path):
        return jsonify({'status': 'error', 'message': 'Imagem da câmera não disponível'}), 404

    # Restante dos parâmetros
    selectedDate = request.form.get('selected_date')
    if not selectedDate:
        return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400

    try:
        datetime.strptime(selectedDate, '%Y-%m-%d')
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400

    category = request.form.get('category')
    if not category:
        return jsonify({'status': 'error', 'message': "Parâmetro 'categoria' obrigatório"}), 400

    try:
        category = request.form.get('category', type=int)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Categoria deve ser um número'}), 400
        
    # Construção da query
    query = {}
    
    try:
        startTime = float(request.form.get('start_time', 0))
        endTime = float(request.form.get('end_time', 24))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Valores de tempo inválidos'}), 400

    if category:
        query["category"] = category

    if selectedDate:
        hours_init = int(startTime)
        minutes_init = int((startTime - hours_init) * 60)
        hours_end = int(endTime)
        minutes_end = int((endTime - hours_end) * 60)
        query_date_start = f"{selectedDate}T{hours_init:02}:{minutes_init:02}:00"
        query_date_end = f"{selectedDate}T{hours_end:02}:{minutes_end:02}:00"
        query["start_time"] = {"$lte": query_date_end}
        query["end_time"] = {"$gte": query_date_start}
        
    if camera:
        query["background"] = camera

    # Parâmetros do plot
    try:
        plot_params = {
            'xsize': float(request.form.get('xsize', 10)),
            'ysize': float(request.form.get('ysize', 10)),
            'xlim1': float(request.form.get('xlim1', 0)),
            'xlim2': float(request.form.get('xlim2', 100)),
            'ylim1': float(request.form.get('ylim1', 0)),
            'ylim2': float(request.form.get('ylim2', 100)),
	        'min_x': min(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'max_x': max(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'min_y': min(float(request.form.get('ylim1')), float(request.form.get('ylim2'))),
            'max_y': max(float(request.form.get('ylim1')), float(request.form.get('ylim2')))
        }
    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400

    try:
        # Buscar trajetórias
        traj_collection = create_trajectory_collection_mongodb(query)
        
        if not traj_collection:
            return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada para o período'}), 404

        # Gerar plot com imagem do banco
        result = plot_trajectories_one_category_background(
            traj_collection,
            category,
            image_path,
            **plot_params
        )
        
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
        plt.close()
        buffer.seek(0)
        
        return jsonify({
            "status": "success",
            "image": base64.b64encode(buffer.getvalue()).decode('utf-8'),
            "metrics": {
                "summary": result
            }
        })

    except Exception as e:
        current_app.logger.error(f"Erro no plot: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}', 'metrics': None}), 500


@app.route('/plot_with_limits', methods=['POST'])
@handle_plot_errors
def plot_with_limits():
    buffer = io.BytesIO()
    
    # Obter nome da câmera
    camera = request.form.get('camera')
    if not camera:
        return jsonify({'status': 'error', 'message': 'Nome da câmera obrigatório'}), 400

    # Buscar imagem da câmera no banco de dados
    camera_data = collection_cam.find_one({'name': camera})
    if not camera_data:
        return jsonify({'status': 'error', 'message': f'Câmera {camera} não encontrada'}), 404

    image_path = camera_data.get('image_path')
    if not image_path or not os.path.isfile(image_path):
        return jsonify({'status': 'error', 'message': 'Imagem da câmera não disponível'}), 404

    # Restante dos parâmetros
    selectedDate = request.form.get('selected_date')
    if not selectedDate:
        return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400

    try:
        datetime.strptime(selectedDate, '%Y-%m-%d')
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400

    category = request.form.get('category')
    if not category:
        return jsonify({'status': 'error', 'message': "Parâmetro 'categoria' obrigatório"}), 400

    try:
        category = request.form.get('category', type=int)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Categoria deve ser um número'}), 400
     
     # Validação WKT   
    reference_line = wkt.loads(request.form.get('reference_line', ''))
    if not reference_line:
        return jsonify({'status': 'error', 'message': "Parâmetro 'reference_line' obrigatório"}), 400
    
    try:
        reference_line = wkt.loads(request.form.get('reference_line', ''))
    except (ShapelyError, TypeError) as e:
        return jsonify({'status': 'error', 'message': f'Erro na geometria: {str(e)}'}), 400    
    
    # Construção da query
    query = {}
    
    try:
        startTime = float(request.form.get('start_time', 0))
        endTime = float(request.form.get('end_time', 24))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Valores de tempo inválidos'}), 400

    if category:
        query["category"] = category

    if selectedDate:
        hours_init = int(startTime)
        minutes_init = int((startTime - hours_init) * 60)
        hours_end = int(endTime)
        minutes_end = int((endTime - hours_end) * 60)
        query_date_start = f"{selectedDate}T{hours_init:02}:{minutes_init:02}:00"
        query_date_end = f"{selectedDate}T{hours_end:02}:{minutes_end:02}:00"
        query["start_time"] = {"$lte": query_date_end}
        query["end_time"] = {"$gte": query_date_start}
        
    if camera:
        query["background"] = camera

    # Parâmetros do plot
    try:
        plot_params = {
            'xsize': float(request.form.get('xsize', 10)),
            'ysize': float(request.form.get('ysize', 10)),
            'xlim1': float(request.form.get('xlim1', 0)),
            'xlim2': float(request.form.get('xlim2', 100)),
            'ylim1': float(request.form.get('ylim1', 0)),
            'ylim2': float(request.form.get('ylim2', 100)),
	        'min_x': min(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'max_x': max(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'min_y': min(float(request.form.get('ylim1')), float(request.form.get('ylim2'))),
            'max_y': max(float(request.form.get('ylim1')), float(request.form.get('ylim2')))
        }
    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400

    try:
        # Buscar trajetórias
        traj_collection = create_trajectory_collection_mongodb(query)
        
        if not traj_collection:
            return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada para o período'}), 404

        # Gerar plot com imagem do banco
        result = plot_trajectories_with_limits(
            traj_collection,
            category,
            image_path,
            reference_line,
            **plot_params
        )
        
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
        plt.close()
        buffer.seek(0)
        
        return jsonify({
            "status": "success",
            "image": base64.b64encode(buffer.getvalue()).decode('utf-8'),
            "metrics": {
                "summary": result
            }
        })

    except Exception as e:
        current_app.logger.error(f"Erro no plot: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}', 'metrics': None}), 500


@app.route('/plot_start_finish', methods=['POST'])
@handle_plot_errors
def plot_with_start_finish():
    buffer = io.BytesIO()
    
    # Obter nome da câmera
    camera = request.form.get('camera')
    if not camera:
        return jsonify({'status': 'error', 'message': 'Nome da câmera obrigatório'}), 400

    # Buscar imagem da câmera no banco de dados
    camera_data = collection_cam.find_one({'name': camera})
    if not camera_data:
        return jsonify({'status': 'error', 'message': f'Câmera {camera} não encontrada'}), 404

    image_path = camera_data.get('image_path')
    if not image_path or not os.path.isfile(image_path):
        return jsonify({'status': 'error', 'message': 'Imagem da câmera não disponível'}), 404

    # Restante dos parâmetros
    selectedDate = request.form.get('selected_date')
    if not selectedDate:
        return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400

    try:
        datetime.strptime(selectedDate, '%Y-%m-%d')
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400

    category = request.form.get('category')
    if not category:
        return jsonify({'status': 'error', 'message': "Parâmetro 'categoria' obrigatório"}), 400

    try:
        category = request.form.get('category', type=int)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Categoria deve ser um número'}), 400
     
     # Validação WKT   
    arrival_line = wkt.loads(request.form.get('finish_line', ''))
    departure_line = wkt.loads(request.form.get('departure_line', ''))
    if not (arrival_line or departure_line):
        return jsonify({'status': 'error', 'message': "Parâmetros WKT obrigatórios"}), 400
    
    try:
        arrival_line = wkt.loads(request.form.get('finish_line', ''))
        departure_line = wkt.loads(request.form.get('departure_line', ''))
    except (ShapelyError, TypeError) as e:
        return jsonify({'status': 'error', 'message': f'Erro na geometria: {str(e)}'}), 400 
    
    # Construção da query
    query = {}
    
    try:
        startTime = float(request.form.get('start_time', 0))
        endTime = float(request.form.get('end_time', 24))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Valores de tempo inválidos'}), 400

    if category:
        query["category"] = category

    if selectedDate:
        hours_init = int(startTime)
        minutes_init = int((startTime - hours_init) * 60)
        hours_end = int(endTime)
        minutes_end = int((endTime - hours_end) * 60)
        query_date_start = f"{selectedDate}T{hours_init:02}:{minutes_init:02}:00"
        query_date_end = f"{selectedDate}T{hours_end:02}:{minutes_end:02}:00"
        query["start_time"] = {"$lte": query_date_end}
        query["end_time"] = {"$gte": query_date_start}
        
    if camera:
        query["background"] = camera

    # Parâmetros do plot
    try:
        plot_params = {
            'xsize': float(request.form.get('xsize', 10)),
            'ysize': float(request.form.get('ysize', 10)),
            'xlim1': float(request.form.get('xlim1', 0)),
            'xlim2': float(request.form.get('xlim2', 100)),
            'ylim1': float(request.form.get('ylim1', 0)),
            'ylim2': float(request.form.get('ylim2', 100)),
	        'min_x': min(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'max_x': max(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'min_y': min(float(request.form.get('ylim1')), float(request.form.get('ylim2'))),
            'max_y': max(float(request.form.get('ylim1')), float(request.form.get('ylim2')))
        }
    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400

    try:
        # Buscar trajetórias
        traj_collection = create_trajectory_collection_mongodb(query)
        
        if not traj_collection:
            return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada para o período'}), 404

        # Gerar plot com imagem do banco
        result = plot_trajectories_with_start_finish(
            traj_collection,
            category,
            image_path,
            arrival_line,
            departure_line,
            **plot_params
        )
        
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
        plt.close()
        buffer.seek(0)
        
        return jsonify({
            "status": "success",
            "image": base64.b64encode(buffer.getvalue()).decode('utf-8'),
            "metrics": {
                "summary": result
            }
        })

    except Exception as e:
        current_app.logger.error(f"Erro no plot: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}', 'metrics': None}), 500


@app.route('/plot_with_stopped', methods=['POST'])
@handle_plot_errors
def plot_with_stopped():
    buffer = io.BytesIO()
    
    # Obter nome da câmera
    camera = request.form.get('camera')
    if not camera:
        return jsonify({'status': 'error', 'message': 'Nome da câmera obrigatório'}), 400

    # Buscar imagem da câmera no banco de dados
    camera_data = collection_cam.find_one({'name': camera})
    if not camera_data:
        return jsonify({'status': 'error', 'message': f'Câmera {camera} não encontrada'}), 404

    image_path = camera_data.get('image_path')
    if not image_path or not os.path.isfile(image_path):
        return jsonify({'status': 'error', 'message': 'Imagem da câmera não disponível'}), 404

    # Restante dos parâmetros
    selectedDate = request.form.get('selected_date')
    if not selectedDate:
        return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400

    try:
        datetime.strptime(selectedDate, '%Y-%m-%d')
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400

    category = request.form.get('category')
    if not category:
        return jsonify({'status': 'error', 'message': "Parâmetro 'categoria' obrigatório"}), 400

    try:
        category = request.form.get('category', type=int)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Categoria deve ser um número'}), 400
    
    try:
        stop_threshold = request.form.get('stop_threshold', type=int)
        min_duration = request.form.get('min_duration', type=int)
        noise_tolerance = request.form.get('noise_tolerance', type=int)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Parâmetros para identificação de paradas inválidos'}), 400
    
    # Construção da query
    query = {}
    
    try:
        startTime = float(request.form.get('start_time', 0))
        endTime = float(request.form.get('end_time', 24))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Valores de tempo inválidos'}), 400

    if category:
        query["category"] = category

    if selectedDate:
        hours_init = int(startTime)
        minutes_init = int((startTime - hours_init) * 60)
        hours_end = int(endTime)
        minutes_end = int((endTime - hours_end) * 60)
        query_date_start = f"{selectedDate}T{hours_init:02}:{minutes_init:02}:00"
        query_date_end = f"{selectedDate}T{hours_end:02}:{minutes_end:02}:00"
        query["start_time"] = {"$lte": query_date_end}
        query["end_time"] = {"$gte": query_date_start}
        
    if camera:
        query["background"] = camera

    # Parâmetros do plot
    try:
        plot_params = {
            'xsize': float(request.form.get('xsize', 10)),
            'ysize': float(request.form.get('ysize', 10)),
            'xlim1': float(request.form.get('xlim1', 0)),
            'xlim2': float(request.form.get('xlim2', 100)),
            'ylim1': float(request.form.get('ylim1', 0)),
            'ylim2': float(request.form.get('ylim2', 100)),
	        'min_x': min(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'max_x': max(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'min_y': min(float(request.form.get('ylim1')), float(request.form.get('ylim2'))),
            'max_y': max(float(request.form.get('ylim1')), float(request.form.get('ylim2')))
        }
    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400

    try:
        # Buscar trajetórias
        traj_collection = create_trajectory_collection_mongodb(query)
        
        if not traj_collection:
            return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada para o período'}), 404

        # Gerar plot com imagem do banco
        result = plot_trajectories_with_stopped(
            traj_collection,
            category,
            image_path,
            **plot_params,
            stop_threshold=stop_threshold,
            min_duration=min_duration,
            noise_tolerance=noise_tolerance
        )
        
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
        plt.close()
        buffer.seek(0)
        
        return jsonify({
            "status": "success",
            "image": base64.b64encode(buffer.getvalue()).decode('utf-8'),
            "metrics": {
                "summary": result
            }
        })

    except Exception as e:
        current_app.logger.error(f"Erro no plot: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}', 'metrics': None}), 500


@app.route('/plot_with_stop_rec', methods=['POST'])
@handle_plot_errors
def plot_with_stop_in_rectangle():
    buffer = io.BytesIO()
    
    # Obter nome da câmera
    camera = request.form.get('camera')
    if not camera:
        return jsonify({'status': 'error', 'message': 'Nome da câmera obrigatório'}), 400

    # Buscar imagem da câmera no banco de dados
    camera_data = collection_cam.find_one({'name': camera})
    if not camera_data:
        return jsonify({'status': 'error', 'message': f'Câmera {camera} não encontrada'}), 404

    image_path = camera_data.get('image_path')
    if not image_path or not os.path.isfile(image_path):
        return jsonify({'status': 'error', 'message': 'Imagem da câmera não disponível'}), 404

    # Restante dos parâmetros
    selectedDate = request.form.get('selected_date')
    if not selectedDate:
        return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400

    try:
        datetime.strptime(selectedDate, '%Y-%m-%d')
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400

    category = request.form.get('category')
    if not category:
        return jsonify({'status': 'error', 'message': "Parâmetro 'categoria' obrigatório"}), 400

    try:
        category = request.form.get('category', type=int)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Categoria deve ser um número'}), 400
    
    try:
        stop_threshold = request.form.get('stop_threshold', type=int)
        min_duration = request.form.get('min_duration', type=int)
        noise_tolerance = request.form.get('noise_tolerance', type=int)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Parâmetros para identificação de paradas inválidos'}), 400
        
    # Construção da query
    query = {}
    
    try:
        startTime = float(request.form.get('start_time', 0))
        endTime = float(request.form.get('end_time', 24))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Valores de tempo inválidos'}), 400

    if category:
        query["category"] = category

    if selectedDate:
        hours_init = int(startTime)
        minutes_init = int((startTime - hours_init) * 60)
        hours_end = int(endTime)
        minutes_end = int((endTime - hours_end) * 60)
        query_date_start = f"{selectedDate}T{hours_init:02}:{minutes_init:02}:00"
        query_date_end = f"{selectedDate}T{hours_end:02}:{minutes_end:02}:00"
        query["start_time"] = {"$lte": query_date_end}
        query["end_time"] = {"$gte": query_date_start}
        
    if camera:
        query["background"] = camera

    # Parâmetros do plot
    try:
        plot_params = {
            'xsize': float(request.form.get('xsize', 10)),
            'ysize': float(request.form.get('ysize', 10)),
            'xlim1': float(request.form.get('xlim1', 0)),
            'xlim2': float(request.form.get('xlim2', 100)),
            'ylim1': float(request.form.get('ylim1', 0)),
            'ylim2': float(request.form.get('ylim2', 100)),
	        'min_x': min(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'max_x': max(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'min_y': min(float(request.form.get('ylim1')), float(request.form.get('ylim2'))),
            'max_y': max(float(request.form.get('ylim1')), float(request.form.get('ylim2'))),
            'rect_min_x': float(request.form.get('rect_min_x', 0)),
            'rect_max_x': float(request.form.get('rect_max_x', 100)),
            'rect_min_y': float(request.form.get('rect_min_y', 0)),
            'rect_max_y': float(request.form.get('rect_max_y', 100))
        }
    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400

    try:
        # Buscar trajetórias
        traj_collection = create_trajectory_collection_mongodb(query)
        
        if not traj_collection:
            return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada para o período'}), 404

        # Gerar plot com imagem do banco
        result = plot_trajectories_with_stop_in_rectangle(
            traj_collection,
            category,
            image_path,
            **plot_params,
            stop_threshold=stop_threshold,
            min_duration=min_duration,
            noise_tolerance=noise_tolerance
        )
        
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
        plt.close()
        buffer.seek(0)
        
        return jsonify({
            "status": "success",
            "image": base64.b64encode(buffer.getvalue()).decode('utf-8'),
            "metrics": {
                "summary": result
            }
        })

    except Exception as e:
        current_app.logger.error(f"Erro no plot: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}', 'metrics': None}), 500

@app.route('/plot_monitored_area', methods=['POST'])
@handle_plot_errors
def plot_in_monitored_area():
    buffer = io.BytesIO()
    
    # Obter nome da câmera
    camera = request.form.get('camera')
    if not camera:
        return jsonify({'status': 'error', 'message': 'Nome da câmera obrigatório'}), 400

    # Buscar imagem da câmera no banco de dados
    camera_data = collection_cam.find_one({'name': camera})
    if not camera_data:
        return jsonify({'status': 'error', 'message': f'Câmera {camera} não encontrada'}), 404

    image_path = camera_data.get('image_path')
    if not image_path or not os.path.isfile(image_path):
        return jsonify({'status': 'error', 'message': 'Imagem da câmera não disponível'}), 404

    # Restante dos parâmetros
    selectedDate = request.form.get('selected_date')
    if not selectedDate:
        return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400

    try:
        datetime.strptime(selectedDate, '%Y-%m-%d')
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400

    category = request.form.get('category')
    if not category:
        return jsonify({'status': 'error', 'message': "Parâmetro 'categoria' obrigatório"}), 400

    try:
        category = request.form.get('category', type=int)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Categoria deve ser um número'}), 400
        
    # Construção da query
    query = {}
    
    try:
        startTime = float(request.form.get('start_time', 0))
        endTime = float(request.form.get('end_time', 24))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Valores de tempo inválidos'}), 400

    if category:
        query["category"] = category

    if selectedDate:
        hours_init = int(startTime)
        minutes_init = int((startTime - hours_init) * 60)
        hours_end = int(endTime)
        minutes_end = int((endTime - hours_end) * 60)
        query_date_start = f"{selectedDate}T{hours_init:02}:{minutes_init:02}:00"
        query_date_end = f"{selectedDate}T{hours_end:02}:{minutes_end:02}:00"
        query["start_time"] = {"$lte": query_date_end}
        query["end_time"] = {"$gte": query_date_start}
        
    if camera:
        query["background"] = camera

    # Parâmetros do plot
    try:
        plot_params = {
            'xsize': float(request.form.get('xsize', 10)),
            'ysize': float(request.form.get('ysize', 10)),
            'xlim1': float(request.form.get('xlim1', 0)),
            'xlim2': float(request.form.get('xlim2', 100)),
            'ylim1': float(request.form.get('ylim1', 0)),
            'ylim2': float(request.form.get('ylim2', 100)),
	        'min_x': min(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'max_x': max(float(request.form.get('xlim1')), float(request.form.get('xlim2'))),
            'min_y': min(float(request.form.get('ylim1')), float(request.form.get('ylim2'))),
            'max_y': max(float(request.form.get('ylim1')), float(request.form.get('ylim2'))),
            'rect_min_x': float(request.form.get('rect_min_x', 0)),
            'rect_max_x': float(request.form.get('rect_max_x', 100)),
            'rect_min_y': float(request.form.get('rect_min_y', 0)),
            'rect_max_y': float(request.form.get('rect_max_y', 100))
        }
    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400

    try:
        # Buscar trajetórias
        traj_collection = create_trajectory_collection_mongodb(query)
        
        if not traj_collection:
            return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada para o período'}), 404

        # Gerar plot com imagem do banco
        result = plot_trajectories_in_monitored_area(
            traj_collection,
            category,
            image_path,
            **plot_params
        )
        
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
        plt.close()
        buffer.seek(0)
        
        return jsonify({
            "status": "success",
            "image": base64.b64encode(buffer.getvalue()).decode('utf-8'),
            "metrics": {
                "summary": result
            }
        })

    except Exception as e:
        current_app.logger.error(f"Erro no plot: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}', 'metrics': None}), 500


if __name__ == "__main__":
    app.run(debug=True)