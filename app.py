import threading
import time
import subprocess
import random
from flask import Flask, render_template, request, jsonify
from datetime import datetime
from pymongo import MongoClient
from lista import tasks
import os
 
# Conexão com o MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['SGDB']
collection = db['orchestrator']
 
app = Flask(__name__)
 
def execute_task(task_name):
    print(f"Executando tarefa: {task_name}")
    for task in tasks:
        if task['name'] == task_name:
            try:
                start_time = datetime.now()
                task['status'] = 'Executando'
                task['execution_start_time'] = start_time.strftime("%H:%M:%S")
               
                executable_path = task['path']
                if executable_path.endswith('.exe'):
                    executable_path = executable_path[:-4]  # Remove .exe
 
                # Verifique se o arquivo existe
                if not os.path.isfile(executable_path + '.exe'):
                    print(f"Arquivo não encontrado: {executable_path}.exe")
                    task['status'] = 'Erro: Arquivo não encontrado'
                    return task
               
                # Executa o arquivo
                process = subprocess.run([executable_path + '.exe'],
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE,
                                         check=True)
                task['status'] = 'Concluída'
                print(process.stdout.decode())
 
            except subprocess.CalledProcessError as e:
                task['status'] = 'Erro'
                print(f"Erro na execução: {e.stderr.decode()}")
            except Exception as e:
                task['status'] = 'Erro'
                print(f"Erro inesperado: {str(e)}")
            break
    return task
 
def save_to_mongodb(task, start_time, end_time, execution_time):
    try:
        document = {
            'id_automacao': task['id'],
            'nome_automacao': task['name'],
            'status_final': task['status'],
            'horario_inicio_execucao': task['execution_start_time'],
            'horario_agendado': task.get('original_time', task['time']),
            'caminho_arquivo': task.get('path', ''),
            'horario_inicio': start_time.strftime("%d/%m/%Y -- %H:%M:%S"),
            'horario_fim': end_time.strftime("%d/%m/%Y -- %H:%M:%S")
        }
 
        hours, remainder = divmod(execution_time.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        document['tempo_de_execucao'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
 
        if task['status'] == 'Erro':
            document['erro'] = "Erro na execução da tarefa"
 
        collection.insert_one(document)
        print(f"Task '{task['name']}' saved to MongoDB.")
    except Exception as e:
        print(f"Error saving task to MongoDB: {e}")
 
def monitor_tasks():
    while True:
        current_time = datetime.now().strftime("%H:%M")
        for task in tasks:
            if task['time'] == current_time and task['status'] == 'Pendente':
                execute_task(task['name'])
        time.sleep(60)
 
@app.route('/')
def index():
    return render_template('index.html', tasks=tasks)
 
@app.route('/start_task', methods=['POST'])
def start_task():
    data = request.json
    task_name = data.get('task_name')
    if not task_name:
        return jsonify({"error": "task_name is required"}), 400
   
    task = execute_task(task_name)
    return jsonify({"task": task})
 
@app.route('/task_status', methods=['GET'])
def task_status():
    for task in tasks:
        latest_status = collection.find_one({'id_automacao': task['id']}, sort=[('horario_fim', -1)])
        if latest_status:
            task['status'] = latest_status['status_final']
            if task['status'] == 'Executando':
                task['time'] = task.get('execution_start_time', task['time'])
            else:
                horario_fim = latest_status.get('horario_fim', '')
                if horario_fim:
                    task['completion_time'] = horario_fim.split('--')[-1].strip()
                else:
                    task['completion_time'] = ''
    return jsonify(tasks)
 
@app.route('/add_task', methods=['POST'])
def add_task():
    global tasks
    data = request.json
    task_name = data.get('name')
    task_time = data.get('time')
    task_path = data.get('path')
   
    if not task_name or not task_time or not task_path:
        return jsonify({"success": False, "message": "Todos os campos são obrigatórios"}), 400
   
    # Remove a extensão .exe do caminho
    if task_path.endswith('.exe'):
        task_path = task_path[:-4]  # Remove .exe
 
    # Verificar se já existe uma tarefa com o mesmo nome ou horário
    for task in tasks:
        if task['name'] == task_name:
            return jsonify({"success": False, "message": "Já existe uma tarefa com este nome"}), 400
        if task['time'] == task_time:
            return jsonify({"success": False, "message": "Já existe uma tarefa agendada para este horário"}), 400
 
    new_task = {'id': len(tasks) + 1, 'name': task_name, 'time': task_time, 'path': task_path, 'status': 'Pendente'}
    tasks.append(new_task)
   
    # Adicionar a nova tarefa ao arquivo lista.py
    with open('lista.py', 'a') as file:
        file.write(f"\ntasks.append({{'id': {new_task['id']}, 'name': '{new_task['name']}', 'time': '{new_task['time']}', 'path': '{new_task['path']}', 'status': 'Pendente'}})")
 
    return jsonify({"success": True, "task": new_task})
 
if __name__ == '__main__':
    threading.Thread(target=monitor_tasks).start()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)