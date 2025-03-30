from flask import render_template, request, send_file, redirect, url_for, jsonify, current_app
from werkzeug.utils import secure_filename
import os
import io
import json
import matplotlib
import tempfile
import base64
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from app import create_app
from pymongo import MongoClient
from shapely import wkt
from datetime import datetime
from shapely.errors import ShapelyError
from functools import wraps
from flask.json.provider import DefaultJSONProvider
from app.utils import JSONEncoder, create_trajectory_collection_mongodb
from smart_traj.smart_trajectories.convert import txt_to_csv, txt_to_csv_datetime
from smart_traj.smart_trajectories.processing import generate_trajectory_collection
from smart_traj.smart_trajectories.plot import plot_trajectories, plot_trajectories_categorized, plot_trajectories_one_category, plot_trajectories_with_background
from smart_traj.smart_trajectories.plot import plot_trajectories_one_category_background, plot_trajectories_with_limits, plot_trajectories_with_start_finish, plot_trajectories_with_stopped
from config import INPUT_DATA_DIR, OUTPUT_DATA_DIR, MONGODB_URI, DB_NAME, COLLECTION_NAME, OUTPUT_DATA_DIR2


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
collection = db[COLLECTION_NAME]

#Cria a aplicação Flask
app = create_app() 
app.json = UTF8JSONProvider(app)
app.config.update(JSON_AS_ASCII=False, JSONIFY_PRETTYPRINT_REGULAR=True)

@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')


@app.route('/upload_txt_to_csv', methods=['POST'])
def upload_txt_to_csv():
    if 'file' not in request.files:
        return redirect(url_for('home'))
    
    camera = request.form.get('camera')
    txt_file = request.files['file']
    
    if txt_file.filename == '':
        return redirect(url_for('home'))

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
                # "category": traj.category,
                "category": traj.df['category'].iloc[0],
                "start_time": traj.get_start_time().isoformat(),
                "end_time": traj.get_end_time().isoformat(),
                "geometry": traj.to_linestring().wkt,
                "background": camera,
                "points": [
                    {
                        #"timestamp": point[0].isoformat(),
                        #"geometry": Point(point[1], point[2]).wkt
                        "timestamp": row.name.isoformat(),
                        "geometry": row.geometry.wkt   
                    }
                    #for point in traj.points
                    for _, row in traj.df.iterrows()
                ]
            }
            mongo_docs.append(trajectory_data)
        
        # Insere no MongoDB
        if mongo_docs:
            collection.insert_many(mongo_docs)
        
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
        return redirect(url_for('home'))
    
    camera = request.form.get('camera')
    txt_file = request.files['file']
    
    if txt_file.filename == '':
        return redirect(url_for('home'))

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
                        #"timestamp": point[0].isoformat(),
                        #"geometry": Point(point[1], point[2]).wkt
                        "timestamp": row.name.isoformat(),
                        "geometry": row.geometry.wkt   
                    }
                    #for point in traj.points
                    for _, row in traj.df.iterrows()
                ]
            }
            mongo_docs.append(trajectory_data)
        
        # Insere no MongoDB
        if mongo_docs:
            collection.insert_many(mongo_docs)
        
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
        
@app.route('/plot_trajectories', methods=['GET'])
@handle_plot_errors
def get_trajectories_plot():
    # Recupera parâmetros da requisição
    camera = request.args.get('camera', '')
    selectedDate = request.args.get('selectedDate')
    if not selectedDate:
        raise ValueError("Parâmetro 'selectedDate' obrigatório")
    try:
        datetime.strptime(selectedDate, '%Y-%m-%d')
    except ValueError:
        raise ValueError("Formato de data inválido")
    
    startTime = request.args.get('startTime', type=float)
    endTime = request.args.get('endTime', type=float)
    
    query = {}
    
    if selectedDate:
        hours = int(startTime)
        minutes = int((startTime - hours) * 60)
        hours1 = int(endTime)
        minutes1 = int((endTime - hours1) * 60)
        query_date_start = f"{selectedDate}T{hours:02}:{minutes:02}:00"
        query_date_end = f"{selectedDate}T{hours1:02}:{minutes1:02}:00"
        query["start_time"] = {"$lte": query_date_end}
        query["end_time"] = {"$gte": query_date_start}

    if camera:
        query["background"] = camera
    
    try:
        # Cria a coleção diretamente do MongoDB
        traj_collection = create_trajectory_collection_mongodb(query)
        if len(traj_collection) == 0:
            return jsonify({
                'status': 'error',
                'message': 'Nenhuma trajetória encontrada com os filtros aplicados.'
            }), 404
        
        # Gera o plot
        buffer = io.BytesIO()
        plot_trajectories(
            traj_collection,
            xsize=request.args.get('xsize', 10, type=float),
            ysize=request.args.get('ysize', 10, type=float),
            xlim1=request.args.get('xlim1', 0, type=float),
            xlim2=request.args.get('xlim2', 100, type=float),
            ylim1=request.args.get('ylim1', 0, type=float),
            ylim2=request.args.get('ylim2', 100, type=float)
        )
        
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        plt.close()
        
        return send_file(buffer, mimetype='image/png')
    
    except Exception as e:
        response = jsonify({'status': 'error', 'message': f'Erro ao gerar trajetórias: {str(e)}'})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500
    

@app.route('/plot_trajectories_categorized', methods=['GET'])
@handle_plot_errors
def get_categorized_plot():
    camera = request.args.get('camera', '')
    selectedDate = request.args.get('selectedDate')
    if not selectedDate:
        raise ValueError("Parâmetro 'selectedDate' obrigatório")
    try:
        datetime.strptime(selectedDate, '%Y-%m-%d')
    except ValueError:
        raise ValueError("Formato de data inválido")
    
    startTime = request.args.get('startTime', type=float)
    endTime = request.args.get('endTime', type=float)
    
    query = {}
    
    if selectedDate:
        hours = int(startTime)
        minutes = int((startTime - hours) * 60)
        hours1 = int(endTime)
        minutes1 = int((endTime - hours1) * 60)
        query_date_start = f"{selectedDate}T{hours:02}:{minutes:02}:00"
        query_date_end = f"{selectedDate}T{hours1:02}:{minutes1:02}:00"
        query["start_time"] = {"$lte": query_date_end}
        query["end_time"] = {"$gte": query_date_start}

    if camera:
        query["background"] = camera
    
    try:
        # Cria a coleção diretamente do MongoDB
        traj_collection = create_trajectory_collection_mongodb(query)
        if len(traj_collection) == 0:
            return jsonify({
                'status': 'error',
                'message': 'Nenhuma trajetória encontrada com os filtros aplicados.'
            }), 404
        
        # Gera o plot
        buffer = io.BytesIO()
        plot_trajectories_categorized(
            traj_collection,
            xsize=request.args.get('xsize', 10, type=float),
            ysize=request.args.get('ysize', 10, type=float),
            xlim1=request.args.get('xlim1', 0, type=float),
            xlim2=request.args.get('xlim2', 100, type=float),
            ylim1=request.args.get('ylim1', 0, type=float),
            ylim2=request.args.get('ylim2', 100, type=float)
        )
        
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        plt.close()
        
        return send_file(buffer, mimetype='image/png')
    
    except Exception as e:
        response = jsonify({'status': 'error', 'message': f'Erro ao gerar trajetórias: {str(e)}'})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500


@app.route('/plot_trajectories_one_category', methods=['GET'])
@handle_plot_errors
def get_trajectories_one_category():
    # Validação inicial
    category = request.args.get('category')
    camera = request.args.get('camera', '')
    if category is None:
        return jsonify({'status': 'error', 'message': 'Parâmetro "category" obrigatório'}), 400
    try:
        category = request.args.get('category', type=int)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Categoria deve ser um número'}), 400
    
    selectedDate = request.args.get('selectedDate')
    if not selectedDate:
        raise ValueError("Parâmetro 'selectedDate' obrigatório")
    try:
        datetime.strptime(selectedDate, '%Y-%m-%d')
    except ValueError:
        raise ValueError("Formato de data inválido")
    
    startTime = request.args.get('startTime', type=float)
    endTime = request.args.get('endTime', type=float)
    
    query = {}
    query["category"] = category
    
    if selectedDate:
        hours = int(startTime)
        minutes = int((startTime - hours) * 60)
        hours1 = int(endTime)
        minutes1 = int((endTime - hours1) * 60)
        query_date_start = f"{selectedDate}T{hours:02}:{minutes:02}:00"
        query_date_end = f"{selectedDate}T{hours1:02}:{minutes1:02}:00"
        query["start_time"] = {"$lte": query_date_end}
        query["end_time"] = {"$gte": query_date_start}
    if camera:
        query["background"] = camera
    
    try:
        # Cria a coleção diretamente do MongoDB
        traj_collection = create_trajectory_collection_mongodb(query)
        if len(traj_collection) == 0:
            return jsonify({
                'status': 'error',
                'message': 'Nenhuma trajetória encontrada com os filtros aplicados.'
            }), 404
        
        # Gera o plot
        buffer = io.BytesIO()
        plot_trajectories_one_category(
            traj_collection,
            category=category,
            xsize=request.args.get('xsize', 10, type=float),
            ysize=request.args.get('ysize', 10, type=float),
            xlim1=request.args.get('xlim1', 0, type=float),
            xlim2=request.args.get('xlim2', 100, type=float),
            ylim1=request.args.get('ylim1', 0, type=float),
            ylim2=request.args.get('ylim2', 100, type=float)
        )
        
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        plt.close()
        
        return send_file(buffer, mimetype='image/png')
    
    except Exception as e:
        response = jsonify({'status': 'error', 'message': f'Erro ao gerar trajetórias: {str(e)}'})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500

@app.route('/plot_with_background', methods=['POST'])
@handle_plot_errors
def plot_with_background():
    buffer = io.BytesIO()
    
    if 'background_image' not in request.files:
        return jsonify({'status': 'error', 'message': 'Nenhuma imagem enviada'}), 400
    background_file = request.files['background_image']
    if background_file.filename == '':
        return jsonify({'status': 'error', 'message': 'Arquivo não selecionado'}), 400
    
    with tempfile.TemporaryDirectory() as temp_dir:
        filename = secure_filename(background_file.filename)
        temp_path = os.path.join(temp_dir, filename)
        background_file.save(temp_path)
        
        if not os.path.isfile(temp_path):
            return jsonify({'status': 'error', 'message': 'Falha ao salvar imagem temporária'}), 500
        
        camera = request.form.get('camera', '')
        selectedDate = request.form.get('selected_date')
        
        if not selectedDate:
            return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400
        
        try:
            datetime.strptime(selectedDate, '%Y-%m-%d')
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400
        
        startTime = request.form.get('start_time', type=float)
        endTime = request.form.get('end_time', type=float)
        
        query = {}
        if selectedDate:
            hours = int(startTime)
            minutes = int((startTime - hours) * 60)
            hours1 = int(endTime)
            minutes1 = int((endTime - hours1) * 60)
            query_date_start = f"{selectedDate}T{hours:02}:{minutes:02}:00"
            query_date_end = f"{selectedDate}T{hours1:02}:{minutes1:02}:00"
            query["start_time"] = {"$lte": query_date_end}
            query["end_time"] = {"$gte": query_date_start}
        
        if camera:
            query["background"] = camera

        try:
            plot_params = {
                'xsize': float(request.form.get('xsize', 10)),
                'ysize': float(request.form.get('ysize', 10)),
                'xlim1': float(request.form.get('xlim1', 0)),
                'xlim2': float(request.form.get('xlim2', 100)),
                'ylim1': float(request.form.get('ylim1', 0)),
                'ylim2': float(request.form.get('ylim2', 100)),
                'min_x': float(request.form.get('min_x', 0)),
                'max_x': float(request.form.get('max_x', 100)),
                'min_y': float(request.form.get('min_y', 0)),
                'max_y': float(request.form.get('max_y', 100))
            } 
        except ValueError as e:
            return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400
        
        try:
            traj_collection = create_trajectory_collection_mongodb(query)
            if len(traj_collection) == 0:
                return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada'}), 404
            
            plot_trajectories_with_background(
                traj_collection, 
                temp_path,
                **plot_params)
            
            plt.savefig(buffer, format='png', bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return jsonify({
                "status": "success",
                "image": image_base64
            })
        
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}'}), 500


@app.route('/plot_one_category', methods=['POST'])  # Alterado para POST
@handle_plot_errors
def plot_one_category():
    buffer = io.BytesIO()
    
    # Validação do arquivo de imagem
    if 'background_image' not in request.files:
        return jsonify({'status': 'error', 'message': 'Nenhuma imagem enviada'}), 400
    
    background_file = request.files['background_image']
    if background_file.filename == '':
        return jsonify({'status': 'error', 'message': 'Arquivo não selecionado'}), 400
    
    # Cria diretório temporário seguro
    with tempfile.TemporaryDirectory() as temp_dir:
        # Salva a imagem temporariamente
        filename = secure_filename(background_file.filename)
        temp_path = os.path.join(temp_dir, filename)
        background_file.save(temp_path)
        
        # Verifica se é uma imagem válida
        if not os.path.isfile(temp_path):
            return jsonify({'status': 'error', 'message': 'Falha ao salvar imagem temporária'}), 500
        
        camera = request.form.get('camera', '')
        category = request.form.get('category')
        selectedDate = request.form.get('selected_date')

        try:
            category = request.form.get('category', type=int)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Categoria deve ser um número'}), 400

        if not selectedDate:
            return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400

        try:
            datetime.strptime(selectedDate, '%Y-%m-%d')
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400

        
        startTime = request.form.get('start_time', type=float)
        endTime = request.form.get('end_time', type=float)
        
        query = {}
        
        if selectedDate:
            hours = int(startTime)
            minutes = int((startTime - hours) * 60)
            hours1 = int(endTime)
            minutes1 = int((endTime - hours1) * 60)
            query_date_start = f"{selectedDate}T{hours:02}:{minutes:02}:00"
            query_date_end = f"{selectedDate}T{hours1:02}:{minutes1:02}:00"
            query["start_time"] = {"$lte": query_date_end}
            query["end_time"] = {"$gte": query_date_start}

        if camera:
            query["background"] = camera
            
        if category:
            query["category"] = category
            
        try:
            # Converte parâmetros numéricos
            plot_params = {
                'xsize': float(request.form.get('xsize', 10)),
                'ysize': float(request.form.get('ysize', 10)),
                'xlim1': float(request.form.get('xlim1', 0)),
                'xlim2': float(request.form.get('xlim2', 100)),
                'ylim1': float(request.form.get('ylim1', 0)),
                'ylim2': float(request.form.get('ylim2', 100)),
                'min_x': float(request.form.get('min_x', 0)),
                'max_x': float(request.form.get('max_x', 100)),
                'min_y': float(request.form.get('min_y', 0)),
                'max_y': float(request.form.get('max_y', 100))
            }
        except ValueError as e:
            return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400

        # Busca dados do MongoDB
        try:
            traj_collection = create_trajectory_collection_mongodb(query)
            if len(traj_collection) == 0:
                return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada'}), 404
            
            plot_trajectories_one_category_background(
                traj_collection=traj_collection,
                category=category,
                background_image_path=temp_path,
                **plot_params
            )
            
            plt.savefig(buffer, format='png', bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return jsonify({
                "status": "success",
                "image": image_base64
            })
        
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}'}), 500


@app.route('/plot_with_limits', methods=['POST'])
@handle_plot_errors
def plot_with_limits():
    buffer = io.BytesIO()
    
    # Validação do upload
    if 'background_image' not in request.files:
        return jsonify({'status': 'error', 'message': 'Imagem de fundo obrigatória'}), 400
    
    background_file = request.files['background_image']
    if background_file.filename == '':
        return jsonify({'status': 'error', 'message': 'Arquivo inválido'}), 400

    with tempfile.TemporaryDirectory() as temp_dir:
        # Processamento da imagem
        filename = secure_filename(background_file.filename)
        temp_path = os.path.join(temp_dir, filename)
        background_file.save(temp_path)  
        
        # Validação WKT
        try:
            reference_line = wkt.loads(request.form.get('reference_line', ''))
        except (ShapelyError, TypeError) as e:
            return jsonify({'status': 'error', 'message': f'Erro na geometria: {str(e)}'}), 400
        
        camera = request.form.get('camera', '')
        category = request.form.get('category')
        selectedDate = request.form.get('selected_date')
        
        try:
            category = request.form.get('category', type=int)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Categoria deve ser um número'}), 400
        
        if not selectedDate:
            return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400

        try:
            datetime.strptime(selectedDate, '%Y-%m-%d')
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400
        
        startTime = request.form.get('start_time', type=float)
        endTime = request.form.get('end_time', type=float)
        
        query = {}
        
        if selectedDate:
            hours = int(startTime)
            minutes = int((startTime - hours) * 60)
            hours1 = int(endTime)
            minutes1 = int((endTime - hours1) * 60)
            query_date_start = f"{selectedDate}T{hours:02}:{minutes:02}:00"
            query_date_end = f"{selectedDate}T{hours1:02}:{minutes1:02}:00"
            query["start_time"] = {"$lte": query_date_end}
            query["end_time"] = {"$gte": query_date_start}

        if camera:
            query["background"] = camera
            
        if category:
            query["category"] = category
            
        try:
            # Converte parâmetros numéricos
            plot_params = {
                'xsize': float(request.form.get('xsize', 10)),
                'ysize': float(request.form.get('ysize', 10)),
                'xlim1': float(request.form.get('xlim1', 0)),
                'xlim2': float(request.form.get('xlim2', 100)),
                'ylim1': float(request.form.get('ylim1', 0)),
                'ylim2': float(request.form.get('ylim2', 100)),
                'min_x': float(request.form.get('min_x', 0)),
                'max_x': float(request.form.get('max_x', 100)),
                'min_y': float(request.form.get('min_y', 0)),
                'max_y': float(request.form.get('max_y', 100))
            }
        except ValueError as e:
            return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400
        
        # Busca dados do MongoDB
        try:
            traj_collection = create_trajectory_collection_mongodb(query)
            if len(traj_collection) == 0:
                return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada'}), 404
            
            plot_trajectories_with_limits(
                traj_collection=traj_collection,
                category=category,
                background_image_path=temp_path,
                reference_line=reference_line,
                **plot_params
            )
            
            plt.savefig(buffer, format='png', bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return jsonify({
                "status": "success",
                "image": image_base64
            })
        
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}'}), 500


@app.route('/plot_start_finish', methods=['POST'])
@handle_plot_errors
def plot_with_start_finish():
    buffer = io.BytesIO()
    
    # Validação do upload
    if 'background_image' not in request.files:
        return jsonify({'status': 'error', 'message': 'Imagem de fundo obrigatória'}), 400
    
    background_file = request.files['background_image']
    if background_file.filename == '':
        return jsonify({'status': 'error', 'message': 'Arquivo inválido'}), 400
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Processamento da imagem
        filename = secure_filename(background_file.filename)
        temp_path = os.path.join(temp_dir, filename)
        background_file.save(temp_path)  
        
        # Validação WKT
        try:
            arrival_line = wkt.loads(request.form.get('finish_line', ''))
            departure_line = wkt.loads(request.form.get('departure_line', ''))
        except (ShapelyError, TypeError) as e:
            return jsonify({'status': 'error', 'message': f'Erro na geometria: {str(e)}'}), 400
    
        camera = request.form.get('camera', '')
        category = request.form.get('category')
        selectedDate = request.form.get('selected_date')
        
        try:
            category = request.form.get('category', type=int)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Categoria deve ser um número'}), 400
        
        if not selectedDate:
            return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400

        try:
            datetime.strptime(selectedDate, '%Y-%m-%d')
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400
        
        startTime = request.form.get('start_time', type=float)
        endTime = request.form.get('end_time', type=float)
        
        query = {}
        
        if selectedDate:
            hours = int(startTime)
            minutes = int((startTime - hours) * 60)
            hours1 = int(endTime)
            minutes1 = int((endTime - hours1) * 60)
            query_date_start = f"{selectedDate}T{hours:02}:{minutes:02}:00"
            query_date_end = f"{selectedDate}T{hours1:02}:{minutes1:02}:00"
            query["start_time"] = {"$lte": query_date_end}
            query["end_time"] = {"$gte": query_date_start}

        if camera:
            query["background"] = camera
            
        if category:
            query["category"] = category
            
        try:
            # Converte parâmetros numéricos
            plot_params = {
                'xsize': float(request.form.get('xsize', 10)),
                'ysize': float(request.form.get('ysize', 10)),
                'xlim1': float(request.form.get('xlim1', 0)),
                'xlim2': float(request.form.get('xlim2', 100)),
                'ylim1': float(request.form.get('ylim1', 0)),
                'ylim2': float(request.form.get('ylim2', 100)),
                'min_x': float(request.form.get('min_x', 0)),
                'max_x': float(request.form.get('max_x', 100)),
                'min_y': float(request.form.get('min_y', 0)),
                'max_y': float(request.form.get('max_y', 100))
            }
        except ValueError as e:
            return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400
        
        # Busca dados do MongoDB
        try:
            traj_collection = create_trajectory_collection_mongodb(query)
            if len(traj_collection) == 0:
                return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada'}), 404
            
            plot_trajectories_with_start_finish(
                traj_collection=traj_collection,
                category=category,
                background_image_path=temp_path,
                arrival_line=arrival_line,
                departure_line=departure_line,
                **plot_params
            )
            
            plt.savefig(buffer, format='png', bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return jsonify({
                "status": "success",
                "image": image_base64
            })
        
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}'}), 500


@app.route('/plot_with_stopped', methods=['POST'])
@handle_plot_errors
def plot_with_stopped():
    buffer = io.BytesIO()
    
    # Validação do upload
    if 'background_image' not in request.files:
        return jsonify({'status': 'error', 'message': 'Imagem de fundo obrigatória'}), 400
    
    background_file = request.files['background_image']
    if background_file.filename == '':
        return jsonify({'status': 'error', 'message': 'Arquivo inválido'}), 400
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Processamento da imagem
        filename = secure_filename(background_file.filename)
        temp_path = os.path.join(temp_dir, filename)
        background_file.save(temp_path)  
    
        camera = request.form.get('camera', '')
        category = request.form.get('category')
        selectedDate = request.form.get('selected_date')
        
        try:
            category = request.form.get('category', type=int)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Categoria deve ser um número'}), 400
        
        if not selectedDate:
            return jsonify({'status': 'error', 'message': "Parâmetro 'selectedDate' obrigatório"}), 400

        try:
            datetime.strptime(selectedDate, '%Y-%m-%d')
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Formato de data inválido'}), 400
        
        startTime = request.form.get('start_time', type=float)
        endTime = request.form.get('end_time', type=float)
        
        query = {}
        
        if selectedDate:
            hours = int(startTime)
            minutes = int((startTime - hours) * 60)
            hours1 = int(endTime)
            minutes1 = int((endTime - hours1) * 60)
            query_date_start = f"{selectedDate}T{hours:02}:{minutes:02}:00"
            query_date_end = f"{selectedDate}T{hours1:02}:{minutes1:02}:00"
            query["start_time"] = {"$lte": query_date_end}
            query["end_time"] = {"$gte": query_date_start}

        if camera:
            query["background"] = camera
            
        if category:
            query["category"] = category
            
        try:
            # Converte parâmetros numéricos
            plot_params = {
                'xsize': float(request.form.get('xsize', 10)),
                'ysize': float(request.form.get('ysize', 10)),
                'xlim1': float(request.form.get('xlim1', 0)),
                'xlim2': float(request.form.get('xlim2', 100)),
                'ylim1': float(request.form.get('ylim1', 0)),
                'ylim2': float(request.form.get('ylim2', 100)),
                'min_x': float(request.form.get('min_x', 0)),
                'max_x': float(request.form.get('max_x', 100)),
                'min_y': float(request.form.get('min_y', 0)),
                'max_y': float(request.form.get('max_y', 100))
            }
        except ValueError as e:
            return jsonify({'status': 'error', 'message': f'Parâmetro numérico inválido: {str(e)}'}), 400
        
        # Busca dados do MongoDB
        try:
            traj_collection = create_trajectory_collection_mongodb(query)
            if len(traj_collection) == 0:
                return jsonify({'status': 'error', 'message': 'Nenhuma trajetória encontrada'}), 404
            
            plot_trajectories_with_stopped(
                traj_collection=traj_collection,
                category=category,
                background_image_path=temp_path,
                **plot_params
            )
            
            plt.savefig(buffer, format='png', bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return jsonify({
                "status": "success",
                "image": image_base64
            })
        
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Erro ao gerar plot: {str(e)}'}), 500

if __name__ == "__main__":
    app.run(debug=True)