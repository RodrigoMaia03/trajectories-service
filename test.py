from flask import render_template, request, jsonify, current_app
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
from datetime import datetime, timezone
from shapely.errors import ShapelyError
from functools import wraps
from flask.json.provider import DefaultJSONProvider
from app.utils import CustomJSONEncoder, create_trajectory_collection_mongodb, allowed_file
from smart_traject.smart_trajectories.convert import txt_to_csv, txt_to_csv_datetime
from smart_traject.smart_trajectories.processing import generate_trajectory_collection
from smart_traject.smart_trajectories.plot import (
    plot_trajectories_with_background, plot_trajectories_one_category_background, 
    plot_trajectories_with_stop_in_rectangle, plot_trajectories_with_limits, 
    plot_trajectories_with_start_finish, plot_trajectories_with_stopped, 
    plot_trajectories_in_monitored_area
)
from config import (INPUT_DATA_DIR, INPUT_DATA_DIR2, OUTPUT_DATA_DIR, OUTPUT_DATA_DIR2,
                    MONGODB_URI, DB_NAME, COLLECTION_TRAJ, COLLECTION_CAM
)

matplotlib.use('Agg')

class UTF8JSONProvider(DefaultJSONProvider):
    ensure_ascii = False

# Configura o MongoDB
client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
collection_traj = db[COLLECTION_TRAJ]
collection_cam = db[COLLECTION_CAM]

# Cria a aplicação Flask
app = create_app()
app.json = UTF8JSONProvider(app)
app.config.update(JSON_AS_ASCII=False, JSONIFY_PRETTYPRINT_REGULAR=True)

# API para carregar mensagens de erro
class ApiException(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

# Tratador de erros para exceções
@app.errorhandler(ApiException)
def handle_api_exception(err):
    # Captura uma exceção e a transforma em uma resposta JSON
    response = {"status": "error", "message": err.message}
    return jsonify(response), err.status_code

@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')

@app.route('/cam', methods=['GET'])
def camera():
    return render_template('cam.html')

@app.route('/convert', methods=['GET'])
def converter():
    return render_template('convert.html')

@app.route('/howtouse', methods=['GET'])
def howtouse():
    return render_template('howtouse.html')

@app.route('/register_camera', methods=['POST'])
def register_camera():
    try:
        if 'name' not in request.form or 'image' not in request.files:
            return jsonify({'status': 'error', 'message': 'Campos obrigatórios ausentes'}), 400

        name = request.form['name']
        image = request.files['image']

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
            "created_at": datetime.now(timezone.utc),
            "metadata": {"coordinate_system": "pixel", "resolution": "native"}
        }
        
        # Inserindo no MongoDb
        result = collection_cam.insert_one(camera_data)
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
        return jsonify({'status': 'error', 'message': 'Erro interno do servidor'}), 500

# Função auxiliar para processar upload de trajetórias
def _process_and_store_trajectory(txt_file, camera, conversion_func, csv_suffix, json_suffix, timestamp_formatter):
    # Processa um arquivo TXT, converte e salva no MongoDB
    try:
        # Salva o arquivo .txt
        txt_filename = secure_filename(txt_file.filename)
        txt_file_path = os.path.join(INPUT_DATA_DIR, txt_filename)
        txt_file.save(txt_file_path)

        # Define caminhos dos arquivos de saída
        base_filename = os.path.splitext(txt_filename)[0]
        csv_filename = f"{base_filename}{csv_suffix}"
        csv_file_path = os.path.join(OUTPUT_DATA_DIR, csv_filename)

        # Conversão para CSV
        conversion_func(txt_file_path, csv_file_path)
        
        # Geração da coleção de trajetórias
        traj_collection = generate_trajectory_collection(csv_file_path)
        
        mongo_docs = []
        for traj in traj_collection:
            trajectory_data = {
                "identifier": traj.id,
                "category": traj.df['category'].iloc[0],
                "start_time": traj.get_start_time(),
                "end_time": traj.get_end_time(),
                "geometry": traj.to_linestring().wkt,
                "background": camera,
                "points": [
                    {"timestamp": timestamp_formatter(row.name), "geometry": row.geometry.wkt}
                    for _, row in traj.df.iterrows()
                ]
            }
            mongo_docs.append(trajectory_data)
        
        # Insere no MongoDB
        docs_count = 0
        if mongo_docs:
            result = collection_traj.insert_many(mongo_docs)
            docs_count = len(result.inserted_ids)
        
        # Cria e salva o JSON
        json_filename = f"{base_filename}{json_suffix}"
        json_file_path = os.path.join(OUTPUT_DATA_DIR2, json_filename)
        with open(json_file_path, 'w') as f:
            json.dump(mongo_docs, f, cls=CustomJSONEncoder)
        
        return jsonify({
            'status': 'success',
            'message': f'Arquivo processado. {docs_count} trajetórias salvas com sucesso!'
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erro ao processar o arquivo: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erro ao processar o arquivo: {str(e)}'}), 500

@app.route('/upload_txt_to_csv', methods=['POST'])
def upload_txt_to_csv():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'Nenhum arquivo enviado'}), 400
    
    txt_file = request.files['file']
    if txt_file.filename == '':
        return jsonify({'status': 'error', 'message': 'Nome de arquivo vazio'}), 400

    camera = request.form.get('camera')
    if not collection_cam.find_one({'name': camera}):
        return jsonify({'status': 'error', 'message': f'Câmera {camera} não cadastrada'}), 404

    return _process_and_store_trajectory(txt_file, camera, txt_to_csv,
        '_converted.csv', '_converted.json', lambda ts: ts.isoformat())

@app.route('/upload_txt_to_csv_datetime', methods=['POST'])
def upload_txt_to_csv_datetime():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'Nenhum arquivo enviado'}), 400
    
    txt_file = request.files['file']
    if txt_file.filename == '':
        return jsonify({'status': 'error', 'message': 'Nome de arquivo vazio'}), 400

    camera = request.form.get('camera')
    if not collection_cam.find_one({'name': camera}):
        return jsonify({'status': 'error', 'message': f'Câmera {camera} não cadastrada'}), 404

    return _process_and_store_trajectory(txt_file, camera, txt_to_csv_datetime,
        '_converted_datetime.csv', '_converted_datetime.json', lambda ts: ts)

# Função auxiliar para rotas de plot
def _validate_common_plot_params():
    # Valida e extrai parâmetros comuns das rotas de plotagem
    camera = request.form.get('camera')
    if not camera:
        raise ApiException("Nome da câmera obrigatório", status_code=400)

    camera_data = collection_cam.find_one({'name': camera})
    if not camera_data:
        raise ApiException(f"Câmera '{camera}' não encontrada", status_code=404)

    image_path = camera_data.get('image_path')
    if not image_path or not os.path.isfile(image_path):
        raise ApiException(f"Imagem para a câmera '{camera}' não disponível", status_code=404)

    selected_date = request.form.get('selected_date')
    if not selected_date:
        raise ApiException("Parâmetro de seleção de data obrigatório", status_code=400)

    try:
        base_date = datetime.fromisoformat(selected_date)
        start_time = float(request.form.get('start_time', 0))
        end_time = float(request.form.get('end_time', 24))
    except (ValueError, TypeError):
        raise ApiException("Formato de data ou hora inválido", status_code=400)

    # Construção da query
    query = {"background": camera}
    hours_init = int(start_time)
    minutes_init = int((start_time - hours_init) * 60)
    query_date_start = base_date.replace(hour=hours_init, minute=minutes_init, tzinfo=timezone.utc)
    
    hours_end = int(end_time)
    minutes_end = int((end_time - hours_end) * 60)
    query_date_end = base_date.replace(hour=hours_end, minute=minutes_end, tzinfo=timezone.utc)
    
    query["start_time"] = {"$lte": query_date_end}
    query["end_time"] = {"$gte": query_date_start}

    try:
        plot_params = {
            'xsize': float(request.form.get('xsize', 10)), 'ysize': float(request.form.get('ysize', 10)),
            'xlim1': float(request.form.get('xlim1', 0)), 'xlim2': float(request.form.get('xlim2', 100)),
            'ylim1': float(request.form.get('ylim1', 0)), 'ylim2': float(request.form.get('ylim2', 100))
        }
        # Adiciona min/max para simplificar
        plot_params.update({
            'min_x': min(plot_params['xlim1'], plot_params['xlim2']),
            'max_x': max(plot_params['xlim1'], plot_params['xlim2']),
            'min_y': min(plot_params['ylim1'], plot_params['ylim2']),
            'max_y': max(plot_params['ylim1'], plot_params['ylim2'])
        })
    except (ValueError, TypeError):
        raise ApiException("Parâmetro numérico de plotagem inválido", status_code=400)

    return {"query": query, "image_path": image_path, "plot_params": plot_params}


def _generate_plot_response(plot_function, plot_specific_args):
    # Função para criar e retornar uma plotagem.
    buffer = io.BytesIO()
    
    # Gerar plotagem
    result = plot_function(**plot_specific_args)
    
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close()
    buffer.seek(0)
    
    return jsonify({"status": "success","image": base64.b64encode(buffer.getvalue()).decode('utf-8'),
        "metrics": {"summary": result}})
    

@app.route('/plot_with_background', methods=['POST'])
def plot_with_background():
    common_params = _validate_common_plot_params()
        
    traj_collection = create_trajectory_collection_mongodb(common_params['query'])
    if not traj_collection:
        raise ApiException('Nenhuma trajetória encontrada para o período', status_code=404)

    plot_args = {
        "traj_collection": traj_collection,
        "image_path": common_params['image_path'],
        **common_params['plot_params']
    }
    return _generate_plot_response(plot_trajectories_with_background, plot_args)


@app.route('/plot_one_category', methods=['POST'])
def plot_category():
    common_params = _validate_common_plot_params()
    category = request.form.get('category', type=int)

    if category is None:
        raise ApiException("Parâmetro de categoria é obrigatório e deve ser um número", status_code=400)
    common_params['query']['category'] = category

    traj_collection = create_trajectory_collection_mongodb(common_params['query'])
    if not traj_collection:
        raise ApiException("Nenhuma trajetória encontrada", status_code=404)

    plot_args = {
        "traj_collection": traj_collection,
        "category": category,
        "image_path": common_params['image_path'],
        **common_params['plot_params']
    }
    
    return _generate_plot_response(plot_trajectories_one_category_background, plot_args)


@app.route('/plot_with_limits', methods=['POST'])
def plot_limits():
    common_params = _validate_common_plot_params()
    category = request.form.get('category', type=int)
    reference_line_wkt = request.form.get('reference_line')
    
    if category is None or not reference_line_wkt:
        raise ApiException("Parâmetros de categoria e linha de referência são obrigatórios", 
                           status_code=400)
        
    try:
        reference_line = wkt.loads(reference_line_wkt)
    except ShapelyError:
        raise ApiException("Formato WKT inválido para linha de referência", status_code=400)
    
    common_params['query']['category'] = category

    traj_collection = create_trajectory_collection_mongodb(common_params['query'])
    if not traj_collection:
        raise ApiException('Nenhuma trajetória encontrada para os filtros aplicados', status_code=404)

    plot_args = {
        "traj_collection": traj_collection,
        "category": category,
        "image_path": common_params['image_path'],
        "reference_line": reference_line,
        **common_params['plot_params']
    }
    
    return _generate_plot_response(plot_trajectories_with_limits, plot_args)


@app.route('/plot_start_finish', methods=['POST'])
def plot_start_finish():
    common_params = _validate_common_plot_params()
    category = request.form.get('category', type=int)
    finish_line_wkt = request.form.get('finish_line')
    departure_line_wkt = request.form.get('departure_line')
    
    if category is None or not finish_line_wkt or not departure_line_wkt:
        raise ApiException("Parâmetros de categoria e linhas partida/chegada são obrigatórios", 
                         status_code=400)
        
    try:
        departure_line = wkt.loads(departure_line_wkt)
        arrival_line = wkt.loads(finish_line_wkt)
    except ShapelyError:
        raise ApiException("Formato WKT inválido para linha de referência", status_code=400)
            
    common_params['query']['category'] = category

    traj_collection = create_trajectory_collection_mongodb(common_params['query'])
    if not traj_collection:
        raise ApiException('Nenhuma trajetória encontrada para os filtros aplicados', status_code=404)

    plot_args = {
        "traj_collection": traj_collection,
        "category": category,
        "image_path": common_params['image_path'],
        "arrival_line": arrival_line,
        "departure_line": departure_line,
        **common_params['plot_params']
    }
    
    return _generate_plot_response(plot_trajectories_with_start_finish, plot_args)


@app.route('/plot_with_stopped', methods=['POST'])
def plot_with_stopped():
    common_params = _validate_common_plot_params()

    try:
        category = int(request.form['category'])
        stop_threshold = int(request.form['stop_threshold'])
        min_duration = int(request.form['min_duration'])
        noise_tolerance = int(request.form['noise_tolerance'])
    except (KeyError, ValueError, TypeError):
        raise ApiException(
            "Parâmetros de categoria e características de parada são obrigatórios e devem ser números inteiros.",
            status_code=400)

    common_params['query']['category'] = category

    traj_collection = create_trajectory_collection_mongodb(common_params['query'])
    if not traj_collection:
        raise ApiException('Nenhuma trajetória encontrada para os filtros aplicados', status_code=404)

    plot_args = {
        "traj_collection": traj_collection,
        "category": category,
        "image_path": common_params['image_path'],
        "stop_threshold": stop_threshold,
        "min_duration": min_duration,
        "noise_tolerance": noise_tolerance,
        **common_params['plot_params']
    }

    return _generate_plot_response(plot_trajectories_with_stopped, plot_args)


@app.route('/plot_with_stop_rec', methods=['POST'])
def plot_with_stop_in_rectangle():
    common_params = _validate_common_plot_params()

    try:
        category = int(request.form['category'])
        stop_threshold = int(request.form['stop_threshold'])
        min_duration = int(request.form['min_duration'])
        noise_tolerance = int(request.form['noise_tolerance'])

        rect_params = {
            'rect_min_x': float(request.form['rect_min_x']),
            'rect_max_x': float(request.form['rect_max_x']),
            'rect_min_y': float(request.form['rect_min_y']),
            'rect_max_y': float(request.form['rect_max_y'])
        }
    except (KeyError, ValueError, TypeError):
        raise ApiException(
            "Parâmetros de categoria e coordenadas do retângulo são obrigatórios e devem ser números.",
            status_code=400)

    common_params['query']['category'] = category
    common_params['plot_params'].update(rect_params)

    traj_collection = create_trajectory_collection_mongodb(common_params['query'])
    if not traj_collection:
        raise ApiException('Nenhuma trajetória encontrada para os filtros aplicados', status_code=404)

    plot_args = {
        "traj_collection": traj_collection,
        "category": category,
        "image_path": common_params['image_path'],
        "stop_threshold": stop_threshold,
        "min_duration": min_duration,
        "noise_tolerance": noise_tolerance,
        **common_params['plot_params']
    }
    
    return _generate_plot_response(plot_trajectories_with_stop_in_rectangle, plot_args)


@app.route('/plot_monitored_area', methods=['POST'])
def plot_monitored_area():
    common_params = _validate_common_plot_params()

    try:
        category = int(request.form['category'])
        rect_params = {
            'rect_min_x': float(request.form['rect_min_x']),
            'rect_max_x': float(request.form['rect_max_x']),
            'rect_min_y': float(request.form['rect_min_y']),
            'rect_max_y': float(request.form['rect_max_y'])
        }
    except (KeyError, ValueError, TypeError):
        raise ApiException(
            "Parâmetros de categoria e coordenadas do retângulo são obrigatórios e devem ser números.",
            status_code=400
        )

    common_params['query']['category'] = category
    common_params['plot_params'].update(rect_params)

    traj_collection = create_trajectory_collection_mongodb(common_params['query'])
    if not traj_collection:
        raise ApiException('Nenhuma trajetória encontrada para os filtros aplicados', status_code=404)

    plot_args = {
        "traj_collection": traj_collection,
        "category": category,
        "image_path": common_params['image_path'],
        **common_params['plot_params']
    }

    return _generate_plot_response(plot_trajectories_in_monitored_area, plot_args)


if __name__ == "__main__":
    app.run(debug=True)