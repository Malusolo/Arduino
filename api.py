from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
# --- MUDANÇA: Importar o Swagger ---
from flasgger import Swagger

# 1. Cria a instância do Flask
app = Flask(__name__)

# --- MUDANÇA: Inicia o Swagger ---
# Isso vai criar a rota /apidocs automaticamente
swagger = Swagger(app)

# 2. Configuração do Banco de Dados MySQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:.de1ate5@localhost:3306/minha_api_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 3. Inicializa o SQLAlchemy
db = SQLAlchemy(app)

# --- Modelos 'Usuario' e 'RegistroPonto' (idênticos ao v2) ---

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    card_uid = db.Column(db.String(100), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    registros = db.relationship('RegistroPonto', back_populates='usuario', lazy=True)

    def to_dict(self):
        return {'id': self.id, 'card_uid': self.card_uid, 'nome': self.nome}

class RegistroPonto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    usuario = db.relationship('Usuario', back_populates='registros')
    data_entrada = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    data_saida = db.Column(db.DateTime, nullable=True) 

    def to_dict(self):
        return {
            'id': self.id,
            'id_usuario': self.id_usuario,
            'nome_usuario': self.usuario.nome if self.usuario else "Desconhecido",
            'data_entrada': self.data_entrada.isoformat(),
            'data_saida': self.data_saida.isoformat() if self.data_saida else None
        }

# --- ROTAS DA API ---

@app.route('/')
def home():
    """
    Rota principal da API de Ponto.
    Apenas exibe uma mensagem de boas-vindas.
    ---
    responses:
      200:
        description: A API está no ar.
        examples:
          text/plain: API de Relógio de Ponto v3 (com Swagger) no ar!
    """
    return "API de Relógio de Ponto v3 (com Swagger) no ar!"

@app.route('/registrar', methods=['POST'])
def registrar_usuario():
    """
    Registra um novo usuário (associando um cartão NFC a um nome).
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            card_uid:
              type: string
              description: O UID hexadecimal do cartão NFC.
              example: "DE284269"
            nome:
              type: string
              description: O nome completo do usuário.
              example: "Joao da Silva"
    responses:
      201:
        description: Usuário registrado com sucesso.
      400:
        description: Erro - Faltando 'card_uid' ou 'nome', ou o cartão/nome já está em uso.
    """
    data = request.json
    if not data or 'card_uid' not in data or 'nome' not in data:
        return jsonify({"mensagem": "Erro: 'card_uid' e 'nome' são obrigatórios."}), 400

    card_uid = data['card_uid']
    nome = data['nome']

    if Usuario.query.filter_by(card_uid=card_uid).first():
        return jsonify({"mensagem": f"Erro: Cartão {card_uid} já está cadastrado."}), 400
    if Usuario.query.filter_by(nome=nome).first():
        return jsonify({"mensagem": f"Erro: Nome '{nome}' já está em uso."}), 400

    novo_usuario = Usuario(card_uid=card_uid, nome=nome)
    
    try:
        db.session.add(novo_usuario)
        db.session.commit()
        return jsonify({"mensagem": f"Usuário {nome} registrado com o cartão {card_uid}."}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"mensagem": f"Erro ao salvar no banco: {str(e)}"}), 500


@app.route('/ponto/entrada', methods=['POST'])
def bater_ponto_entrada():
    """
    Registra um ponto de ENTRADA para um usuário.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            card_uid:
              type: string
              description: O UID do cartão do usuário.
              example: "DE284269"
    responses:
      201:
        description: Entrada registrada com sucesso.
        schema:
          type: object
          properties:
            acao: { type: string, example: "entrada" }
            nome: { type: string, example: "Joao da Silva" }
            data_entrada: { type: string, example: "2025-11-13T18:00:00Z" }
      400:
        description: Erro - Usuário já possui um ponto em aberto.
      404:
        description: Erro - Cartão não cadastrado.
    """
    data = request.json
    if not data or 'card_uid' not in data:
        return jsonify({"mensagem": "Erro: 'card_uid' é obrigatório."}), 400
    # ... (lógica da rota idêntica ao v2) ...
    card_uid = data['card_uid']
    usuario = Usuario.query.filter_by(card_uid=card_uid).first()
    if not usuario:
        return jsonify({"acao": "erro", "mensagem": "Cartão não cadastrado."}), 404
    registro_aberto = RegistroPonto.query.filter_by(id_usuario=usuario.id, data_saida=None).first()
    if registro_aberto:
        return jsonify({"acao": "erro", "mensagem": "Já possui ponto em aberto."}), 400
    novo_registro = RegistroPonto(id_usuario=usuario.id)
    try:
        db.session.add(novo_registro)
        db.session.commit()
        return jsonify({
            "acao": "entrada", 
            "nome": usuario.nome, 
            "data_entrada": novo_registro.data_entrada.isoformat()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"acao": "erro", "mensagem": f"Erro ao salvar no banco: {str(e)}"}), 500

@app.route('/ponto/saida', methods=['POST'])
def bater_ponto_saida():
    """
    Registra um ponto de SAÍDA para um usuário.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            card_uid:
              type: string
              description: O UID do cartão do usuário.
              example: "DE284269"
    responses:
      200:
        description: Saída registrada com sucesso.
        schema:
          type: object
          properties:
            acao: { type: string, example: "saida" }
            nome: { type: string, example: "Joao da Silva" }
            data_saida: { type: string, example: "2025-11-13T19:00:00Z" }
      404:
        description: Erro - Cartão não cadastrado ou nenhum ponto em aberto encontrado.
    """
    data = request.json
    if not data or 'card_uid' not in data:
        return jsonify({"mensagem": "Erro: 'card_uid' é obrigatório."}), 400
    # ... (lógica da rota idêntica ao v2) ...
    card_uid = data['card_uid']
    usuario = Usuario.query.filter_by(card_uid=card_uid).first()
    if not usuario:
        return jsonify({"acao": "erro", "mensagem": "Cartão não cadastrado."}), 404
    registro_aberto = RegistroPonto.query.filter_by(
        id_usuario=usuario.id, 
        data_saida=None
    ).order_by(RegistroPonto.data_entrada.desc()).first()
    if not registro_aberto:
        return jsonify({"acao": "erro", "mensagem": "Nenhum ponto em aberto."}), 404
    registro_aberto.data_saida = datetime.utcnow()
    try:
        db.session.commit()
        return jsonify({
            "acao": "saida", 
            "nome": usuario.nome,
            "data_entrada": registro_aberto.data_entrada.isoformat(),
            "data_saida": registro_aberto.data_saida.isoformat()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"acao": "erro", "mensagem": f"Erro ao atualizar no banco: {str(e)}"}), 500

@app.route('/ponto/total/<string:card_uid>', methods=['GET'])
def get_totais_por_usuario(card_uid):
    """
    Busca o total de horas trabalhadas (dia, semana, mês, total) para um usuário.
    ---
    parameters:
      - name: card_uid
        in: path
        type: string
        required: true
        description: O UID do cartão do usuário.
        example: "DE284269"
    responses:
      200:
        description: Retorna o objeto JSON com os totais de horas.
      404:
        description: Usuário não encontrado.
    """
    # ... (lógica da rota idêntica ao v2) ...
    usuario = Usuario.query.filter_by(card_uid=card_uid).first()
    if not usuario:
        return jsonify({"mensagem": "Usuário não encontrado."}), 404

    now = datetime.utcnow()
    day_start = datetime(now.year, now.month, now.day)
    day_end = day_start + timedelta(days=1)
    
    registros = RegistroPonto.query.filter(
        RegistroPonto.id_usuario == usuario.id, 
        RegistroPonto.data_saida != None
    ).all()

    totals_sec = { 'day': 0.0, 'week': 0.0, 'month': 0.0, 'total': 0.0 }
    
    def overlap_seconds(start_a, end_a, start_b, end_b):
        latest_start = max(start_a, start_b)
        earliest_end = min(end_a, end_b)
        delta = (earliest_end - latest_start).total_seconds()
        return max(0.0, delta)

    week_start = day_start - timedelta(days=now.weekday())
    week_end = week_start + timedelta(days=7)
    month_start = datetime(now.year, now.month, 1)
    if now.month == 12:
        month_end = datetime(now.year + 1, 1, 1)
    else:
        month_end = datetime(now.year, now.month + 1, 1)

    for r in registros:
        s = r.data_entrada
        e = r.data_saida
        if not s or not e: continue
        
        dur_sec = (e - s).total_seconds()
        totals_sec['total'] += dur_sec
        totals_sec['day'] += overlap_seconds(s, e, day_start, day_end)
        totals_sec['week'] += overlap_seconds(s, e, week_start, week_end)
        totals_sec['month'] += overlap_seconds(s, e, month_start, month_end)
    
    def secs_to_hours_float(sec): return round(sec / 3600.0, 2)
    def secs_to_hhmmss(sec):
        sec = int(sec); h = sec // 3600; m = (sec % 3600) // 60; s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    result = {
        'id_usuario': usuario.id,
        'nome_usuario': usuario.nome,
        'card_uid': usuario.card_uid,
        'dia': { 'segundos': int(totals_sec['day']), 'horas': secs_to_hours_float(totals_sec['day']), 'hhmmss': secs_to_hhmmss(totals_sec['day']) },
        'semana': { 'segundos': int(totals_sec['week']), 'horas': secs_to_hours_float(totals_sec['week']), 'hhmmss': secs_to_hhmmss(totals_sec['week']) },
        'mes': { 'segundos': int(totals_sec['month']), 'horas': secs_to_hours_float(totals_sec['month']), 'hhmmss': secs_to_hhmmss(totals_sec['month']) },
        'total': { 'segundos': int(totals_sec['total']), 'horas': secs_to_hours_float(totals_sec['total']), 'hhmmss': secs_to_hhmmss(totals_sec['total']) }
    }
    return jsonify(result)

# 7. Roda o servidor
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # Debug=True é útil, mas em produção mude para False
    app.run(host='0.0.0.0', port=5000, debug=True)
