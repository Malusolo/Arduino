from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
# Importa 'timezone' e 'timedelta'
from datetime import datetime, timedelta, timezone
from flasgger import Swagger

# 1. Cria a instância do Flask
app = Flask(__name__)
swagger = Swagger(app)

# Define nosso fuso horário local (UTC-3)
BR_TZ = timezone(timedelta(hours=-3))

# 2. Configuração do Banco de Dados MySQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:.de1ate5@localhost:3306/minha_api_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 3. Inicializa o SQLAlchemy
db = SQLAlchemy(app)

# --- Modelos 'Usuario' e 'RegistroPonto' ---

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
    # Salva em UTC
    data_entrada = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    data_saida = db.Column(db.DateTime, nullable=True) 

    def to_dict(self):
        # Converte para o fuso local (BR_TZ) antes de mostrar
        entrada_local_iso = None
        if self.data_entrada:
            # Garante que seja tratado como UTC antes de converter
            entrada_utc = self.data_entrada.replace(tzinfo=timezone.utc)
            entrada_local_iso = entrada_utc.astimezone(BR_TZ).isoformat()
            
        saida_local_iso = None
        if self.data_saida:
            saida_utc = self.data_saida.replace(tzinfo=timezone.utc)
            saida_local_iso = saida_utc.astimezone(BR_TZ).isoformat()

        return {
            'id': self.id,
            'id_usuario': self.id_usuario,
            'nome_usuario': self.usuario.nome if self.usuario else "Desconhecido",
            'data_entrada': entrada_local_iso,
            'data_saida': saida_local_iso
        }

# --- ROTAS DA API ---

@app.route('/')
def home():
    """
    Rota principal da API de Ponto.
    ---
    responses:
      200:
        description: A API está no ar.
    """
    return "API de Relógio de Ponto v6 (Final - Offline Sync) no ar!"

@app.route('/registrar', methods=['POST'])
def registrar_usuario():
    """
    Registra um novo usuário.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            card_uid: { type: string }
            nome: { type: string }
    responses:
      201:
        description: Usuário registrado.
      400:
        description: Erro de validação.
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

# =================================================================
# ROTA DE ENTRADA (ATUALIZADA PARA TIMESTAMP OFFLINE)
# =================================================================
@app.route('/ponto/entrada', methods=['POST'])
def bater_ponto_entrada():
    """
    Registra um ponto de ENTRADA. Aceita timestamp offline.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            card_uid: { type: string, example: "DE284269" }
            timestamp: { type: integer, example: 1701234567, description: "Unix timestamp (opcional)" }
    responses:
      201:
        description: Entrada registrada.
      400:
        description: Já tem ponto aberto.
    """
    data = request.json
    if not data or 'card_uid' not in data:
        return jsonify({"mensagem": "Erro: 'card_uid' é obrigatório."}), 400
        
    card_uid = data['card_uid']
    usuario = Usuario.query.filter_by(card_uid=card_uid).first()
    if not usuario:
        return jsonify({"acao": "erro", "mensagem": "Cartão não cadastrado."}), 404
        
    registro_aberto = RegistroPonto.query.filter_by(id_usuario=usuario.id, data_saida=None).first()
    if registro_aberto:
        return jsonify({"acao": "erro", "mensagem": "Já possui ponto em aberto."}), 400
    
    # --- LÓGICA DE TIMESTAMP (OFFLINE) ---
    data_registro = datetime.utcnow() # Padrão: agora (online)

    if 'timestamp' in data and data['timestamp']:
        try:
            # O ESP envia um Inteiro (segundos desde 1970). 
            ts = int(data['timestamp'])
            # Convertemos para datetime UTC e removemos info de tz para o MySQL aceitar (naive)
            data_registro = datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)
            print(f"-> Registro Offline Detectado. Data convertida: {data_registro}")
        except ValueError:
            print("-> Erro ao converter timestamp. Usando horário atual.")
            pass # Mantém datetime.utcnow()

    # Cria o registro
    novo_registro = RegistroPonto(id_usuario=usuario.id, data_entrada=data_registro)

    try:
        db.session.add(novo_registro)
        db.session.commit()
        return jsonify(novo_registro.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"acao": "erro", "mensagem": f"Erro ao salvar no banco: {str(e)}"}), 500

# =================================================================
# ROTA DE SAÍDA (ATUALIZADA PARA TIMESTAMP OFFLINE)
# =================================================================
@app.route('/ponto/saida', methods=['POST'])
def bater_ponto_saida():
    """
    Registra um ponto de SAÍDA. Aceita timestamp offline.
    """
    data = request.json
    if not data or 'card_uid' not in data:
        return jsonify({"mensagem": "Erro: 'card_uid' é obrigatório."}), 400
        
    card_uid = data['card_uid']
    usuario = Usuario.query.filter_by(card_uid=card_uid).first()
    if not usuario:
        return jsonify({"acao": "erro", "mensagem": "Cartão não cadastrado."}), 404
        
    # Busca o último ponto aberto (o mais recente)
    registro_aberto = RegistroPonto.query.filter_by(
        id_usuario=usuario.id, 
        data_saida=None
    ).order_by(RegistroPonto.data_entrada.desc()).first()
    
    if not registro_aberto:
        return jsonify({"acao": "erro", "mensagem": "Nenhum ponto em aberto."}), 404
    
    # --- LÓGICA DE TIMESTAMP (OFFLINE) ---
    data_registro = datetime.utcnow()

    if 'timestamp' in data and data['timestamp']:
        try:
            ts = int(data['timestamp'])
            data_registro = datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)
            print(f"-> Registro Offline Saída Detectado. Data: {data_registro}")
            
            # Validação Extra: A saída não pode ser menor que a entrada
            if data_registro < registro_aberto.data_entrada:
                return jsonify({"acao": "erro", "mensagem": "Data de saída anterior à entrada! Verifique o relógio."}), 400
                
        except ValueError:
            pass

    registro_aberto.data_saida = data_registro

    try:
        db.session.commit()
        return jsonify(registro_aberto.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"acao": "erro", "mensagem": f"Erro ao atualizar no banco: {str(e)}"}), 500


@app.route('/ponto/total/<string:card_uid>', methods=['GET'])
def get_totais_por_usuario(card_uid):
    # ... (MANTENHA SUA LÓGICA DE TOTAIS AQUI IGUAL AO CÓDIGO ORIGINAL) ...
    # Estou omitindo para economizar espaço, pois não precisa mudar nada nela.
    # Se quiser que eu repita, me avise.
    return calcular_totais(card_uid=card_uid)

@app.route('/ponto/total/by-name/<string:nome>', methods=['GET'])
def get_totais_by_name(nome):
    # ... (MANTENHA SUA LÓGICA AQUI) ...
    return calcular_totais(nome=nome)

# Função auxiliar para não duplicar código (Opcional, apenas sugestão de organização)
def calcular_totais(card_uid=None, nome=None):
    if card_uid:
        usuario = Usuario.query.filter_by(card_uid=card_uid).first()
    else:
        usuario = Usuario.query.filter_by(nome=nome).first()
        
    if not usuario:
        return jsonify({"mensagem": "Usuário não encontrado."}), 404

    # Lógica de cálculo de data (baseada no fuso local BR_TZ)
    now_local = datetime.now(BR_TZ) 
    day_start_local = datetime(now_local.year, now_local.month, now_local.day, tzinfo=BR_TZ)
    day_end_local = day_start_local + timedelta(days=1)
    week_start_local = day_start_local - timedelta(days=now_local.weekday())
    week_end_local = week_start_local + timedelta(days=7)
    month_start_local = datetime(now_local.year, now_local.month, 1, tzinfo=BR_TZ)
    if now_local.month == 12:
        month_end_local = datetime(now_local.year + 1, 1, 1, tzinfo=BR_TZ)
    else:
        month_end_local = datetime(now_local.year, now_local.month + 1, 1, tzinfo=BR_TZ)
    
    # Busca registros no banco (que estão em UTC)
    registros = RegistroPonto.query.filter(
        RegistroPonto.id_usuario == usuario.id, 
        RegistroPonto.data_saida != None
    ).all()

    totals_sec = { 'day': 0.0, 'week': 0.0, 'month': 0.0, 'total': 0.0 }
    
    def overlap_seconds(start_a_aware, end_a_aware, start_b_aware, end_b_aware):
        latest_start = max(start_a_aware, start_b_aware)
        earliest_end = min(end_a_aware, end_b_aware)
        delta = (earliest_end - latest_start).total_seconds()
        return max(0.0, delta)

    for r in registros:
        s_utc_naive = r.data_entrada
        e_utc_naive = r.data_saida
        if not s_utc_naive or not e_utc_naive: continue
        
        s_utc_aware = s_utc_naive.replace(tzinfo=timezone.utc)
        e_utc_aware = e_utc_naive.replace(tzinfo=timezone.utc)

        dur_sec = (e_utc_aware - s_utc_aware).total_seconds()
        totals_sec['total'] += dur_sec
        
        totals_sec['day'] += overlap_seconds(s_utc_aware, e_utc_aware, day_start_local, day_end_local)
        totals_sec['week'] += overlap_seconds(s_utc_aware, e_utc_aware, week_start_local, week_end_local)
        totals_sec['month'] += overlap_seconds(s_utc_aware, e_utc_aware, month_start_local, month_end_local)
    
    def get_hms_from_seconds(sec_float):
        sec_total = int(sec_float)
        h = sec_total // 3600
        m = (sec_total % 3600) // 60
        s = sec_total % 60
        return h, m, s

    h_dia, m_dia, s_dia = get_hms_from_seconds(totals_sec['day'])
    h_sem, m_sem, s_sem = get_hms_from_seconds(totals_sec['week'])
    h_mes, m_mes, s_mes = get_hms_from_seconds(totals_sec['month'])
    h_tot, m_tot, s_tot = get_hms_from_seconds(totals_sec['total'])

    result = {
        'usuario': {
            'id_usuario': usuario.id,
            'nome_usuario': usuario.nome,
            'card_uid': usuario.card_uid
        },
        'periodos': {
            'dia': { 'horas': h_dia, 'minutos': m_dia, 'segundos': s_dia },
            'semana': { 'horas': h_sem, 'minutos': m_sem, 'segundos': s_sem },
            'mes': { 'horas': h_mes, 'minutos': m_mes, 'segundos': s_mes },
            'total': { 'horas': h_tot, 'minutos': m_tot, 'segundos': s_tot }
        }
    }
    return jsonify(result)

# 7. Roda o servidor
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # Host 0.0.0.0 permite que o ESP8266 acesse a API pela rede
    app.run(host='0.0.0.0', port=5000, debug=True)
