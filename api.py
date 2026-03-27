from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
# Importa 'timezone' e 'timedelta'
from datetime import datetime, timedelta, timezone
from flasgger import Swagger
import os

# 1. Cria a instância do Flask
app = Flask(__name__)
swagger = Swagger(app)

# Configuração de sessão
app.secret_key = os.environ.get('SECRET_KEY', 'sua-chave-secreta-super-segura-aqui-123')

# Define nosso fuso horário local (UTC-3)
BR_TZ = timezone(timedelta(hours=-3))

# 2. Configuração do Banco de Dados MySQL
# Tenta pegar a URL do sistema (Render), se não achar, usa a local
db_url = os.environ.get('DATABASE_URL', 'mysql+pymysql://root:.de1ate5@localhost:3306/minha_api_db')

# Corrige problema de prefixo do Render (se vier postgres:// muda para postgresql://, mas para mysql é direto)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
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
    # Salva em BR_TZ como datetime aware
    data_entrada = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.now(BR_TZ))
    data_saida = db.Column(db.DateTime(timezone=True), nullable=True) 

    def to_dict(self):
        # Converte para BR_TZ para exibição consistente
        try:
            if self.data_entrada:
                if self.data_entrada.tzinfo is None:
                    entrada_utc = self.data_entrada.replace(tzinfo=timezone.utc)
                else:
                    entrada_utc = self.data_entrada
                entrada_local = entrada_utc.astimezone(BR_TZ)
            else:
                entrada_local = None

            if self.data_saida:
                if self.data_saida.tzinfo is None:
                    saida_utc = self.data_saida.replace(tzinfo=timezone.utc)
                else:
                    saida_utc = self.data_saida
                saida_local = saida_utc.astimezone(BR_TZ)
            else:
                saida_local = None

            return {
                'id': self.id,
                'id_usuario': self.id_usuario,
                'nome_usuario': self.usuario.nome if self.usuario else "Desconhecido",
                'data_entrada': entrada_local.isoformat() if entrada_local else None,
                'data_saida': saida_local.isoformat() if saida_local else None
            }
        except Exception as e:
            # Fallback para formato simples
            return {
                'id': self.id,
                'id_usuario': self.id_usuario,
                'nome_usuario': self.usuario.nome if self.usuario else "Desconhecido",
                'data_entrada': str(self.data_entrada) if self.data_entrada else None,
                'data_saida': str(self.data_saida) if self.data_saida else None
            }

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    
    def to_dict(self):
        return {'id': self.id, 'email': self.email}

# --- ROTAS DA API ---

# --- ROTAS DE PÁGINA (Frontend - Dashboard) ---
@app.route('/')
def index():
    # Se não estiver autenticado, redireciona para o login
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # Rota principal carrega o Dashboard
    try:
        return render_template('index.html')
    except Exception as e:
        return f"Erro ao carregar a interface: {str(e)}", 500

@app.route('/login')
def login_page():
    # Se já estiver autenticado, redireciona para o dashboard
    if 'user_email' in session:
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    """
    Faz login de um admin usando email
    """
    data = request.json
    if not data or 'email' not in data:
        return jsonify({"mensagem": "Email é obrigatório"}), 400
    
    email = data['email'].strip().lower()
    admin = Admin.query.filter_by(email=email).first()
    
    if not admin:
        return jsonify({"mensagem": "Email não encontrado ou não é administrador"}), 401
    
    # Armazena o email na sessão
    session['user_email'] = email
    session['is_admin'] = True
    
    return jsonify({"mensagem": "Login realizado com sucesso"}), 200

@app.route('/api/login-visitante', methods=['POST'])
def api_login_visitante():
    """
    Faz login como visitante (sem autenticação)
    """
    session['user_email'] = 'visitante'
    session['is_admin'] = False
    
    return jsonify({"mensagem": "Acesso de visitante concedido"}), 200

@app.route('/api/logout', methods=['POST'])
def api_logout():
    """
    Faz logout do usuário
    """
    session.clear()
    return jsonify({"mensagem": "Logout realizado com sucesso"}), 200

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    """
    Verifica o status de autenticação do usuário
    """
    if 'user_email' not in session:
        return jsonify({"autenticado": False, "email": None, "is_admin": False}), 200
    
    return jsonify({
        "autenticado": True,
        "email": session.get('user_email'),
        "is_admin": session.get('is_admin', False)
    }), 200

# Rota de Status (Antiga Home) - Mudei para /status para não conflitar com o Dashboard
@app.route('/status')
def home():
    """
    Rota de verificação da API.
    ---
    responses:
      200:
        description: A API está no ar.
    """
    return "API de Relógio de Ponto v6 (Final - Offline Sync) no ar!"

# --- ROTAS DE API (Dados) ---

@app.route('/api/usuarios', methods=['GET'])
def get_usuarios():
    users = Usuario.query.order_by(Usuario.nome).all()
    return jsonify([u.to_dict() for u in users])

# NOVA ROTA: USUÁRIOS COM PONTOS EM ABERTO
@app.route('/api/usuarios/pontos-abertos', methods=['GET'])
def get_usuarios_pontos_abertos():
    """
    Retorna usuários que têm pontos em aberto (registros sem data_saida)
    """
    # Busca todos os registros e filtra em Python
    todos_registros = RegistroPonto.query.all()
    registros_abertos = [r for r in todos_registros if r.data_saida is None]
    
    # Extrai IDs únicos de usuários
    user_ids = set(reg.id_usuario for reg in registros_abertos)
    
    # Busca usuários correspondentes
    usuarios_com_abertos = Usuario.query.filter(Usuario.id.in_(user_ids)).order_by(Usuario.nome).all()

    # Adiciona informações do registro aberto
    resultado = []
    for usuario in usuarios_com_abertos:
        registro_aberto = next((r for r in registros_abertos if int(r.id_usuario) == usuario.id), None)
        if registro_aberto:
            user_dict = usuario.to_dict()
            ponto_dict = registro_aberto.to_dict()
            user_dict['ponto_aberto'] = ponto_dict
            resultado.append(user_dict)

    return jsonify(resultado)


@app.route('/api/export/json', methods=['GET'])
def exportar_dados_json():
    """Permite ao administrador exportar todos usuários e registros em JSON."""
    if not session.get('is_admin'):
        return jsonify({'mensagem': 'Acesso negado'}), 403

    usuarios = [u.to_dict() for u in Usuario.query.order_by(Usuario.nome).all()]
    registros = []
    for r in RegistroPonto.query.order_by(RegistroPonto.data_entrada).all():
        registros.append({
            'id': r.id,
            'id_usuario': r.id_usuario,
            'nome_usuario': r.usuario.nome if r.usuario else 'Desconhecido',
            'card_uid': r.usuario.card_uid if r.usuario else None,
            'data_entrada': r.data_entrada.isoformat() if r.data_entrada else None,
            'data_saida': r.data_saida.isoformat() if r.data_saida else None
        })
    return jsonify({'usuarios': usuarios, 'registros': registros}), 200
    
    # Adiciona informações do registro aberto
    resultado = []
    for usuario in usuarios_com_abertos:
        registro_aberto = next((r for r in registros_abertos if int(r.id_usuario) == usuario.id), None)
        
        if registro_aberto:
            user_dict = usuario.to_dict()
            ponto_dict = registro_aberto.to_dict()
            user_dict['ponto_aberto'] = ponto_dict
            resultado.append(user_dict)
    
    return jsonify(resultado)

# NOVA ROTA: EXCLUIR USUÁRIO (CORRIGIDA)
@app.route('/api/usuarios/<int:id>', methods=['DELETE'])
def delete_usuario(id):
    """
    Exclui um usuário e seus registros.
    ---
    parameters:
      - name: id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Usuário excluído.
    """
    usuario = Usuario.query.get(id)
    if not usuario:
        return jsonify({"mensagem": "Usuário não encontrado"}), 404
    
    try:
        # CORREÇÃO: Apaga os registros iterativamente para garantir a consistência da sessão
        registros = RegistroPonto.query.filter_by(id_usuario=id).all()
        for reg in registros:
            db.session.delete(reg)
        
        # Agora deleta o usuário
        db.session.delete(usuario)
        db.session.commit()
        return jsonify({"mensagem": "Usuário excluído com sucesso"}), 200
    except Exception as e:
        db.session.rollback()
        print(f"ERRO AO EXCLUIR: {e}") # Log no terminal para debug
        return jsonify({"mensagem": f"Erro ao excluir: {str(e)}"}), 500

@app.route('/api/historico', methods=['GET'])
def get_historico():
    data_str = request.args.get('data')
    query = RegistroPonto.query
    
    if data_str:
        try:
            data_filtro = datetime.strptime(data_str, '%Y-%m-%d').date()
            # Calcula o início e fim do dia local
            start_local = datetime.combine(data_filtro, datetime.min.time(), tzinfo=BR_TZ)
            end_local = start_local + timedelta(days=1)
            query = query.filter(RegistroPonto.data_entrada >= start_local, RegistroPonto.data_entrada < end_local)
        except:
            pass 

    registros = query.order_by(RegistroPonto.data_entrada.desc()).all()
    
    lista = []
    for reg in registros:
        # Já está em BR_TZ, usa diretamente
        entrada_local = reg.data_entrada
        saida_local = reg.data_saida
        duracao_str = ""
        if reg.data_saida:
            delta = reg.data_saida - reg.data_entrada
            total_seconds = int(delta.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            duracao_str = f"{hours}h {minutes}m"

        lista.append({
            "card_uid": reg.usuario.card_uid if reg.usuario else "???",
            "usuario_nome": reg.usuario.nome if reg.usuario else "Desconhecido",
            "entrada": entrada_local.isoformat() if entrada_local else None,
            "saida": saida_local.isoformat() if saida_local else None,
            "duracao": duracao_str
        })
    
    return jsonify(lista)

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
    
    data_registro = datetime.now(BR_TZ)
    if 'timestamp' in data and data['timestamp']:
        try:
            ts = int(data['timestamp'])
            data_registro = datetime.fromtimestamp(ts, tz=BR_TZ)
        except ValueError:
            pass

    novo_registro = RegistroPonto(id_usuario=usuario.id, data_entrada=data_registro)
    try:
        db.session.add(novo_registro)
        db.session.commit()
        return jsonify(novo_registro.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"acao": "erro", "mensagem": f"Erro ao salvar no banco: {str(e)}"}), 500

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
        
    registro_aberto = RegistroPonto.query.filter_by(
        id_usuario=usuario.id, 
        data_saida=None
    ).order_by(RegistroPonto.data_entrada.desc()).first()
    
    if not registro_aberto:
        return jsonify({"acao": "erro", "mensagem": "Nenhum ponto em aberto."}), 404
    
    # Garante que entrada e saída são aware (mesmo timezone) antes de comparar
    entrada = registro_aberto.data_entrada
    if entrada.tzinfo is None:
        entrada = entrada.replace(tzinfo=BR_TZ)
    else:
        entrada = entrada.astimezone(BR_TZ)

    data_registro = datetime.now(BR_TZ)
    if 'timestamp' in data and data['timestamp']:
        try:
            ts = int(data['timestamp'])
            data_registro = datetime.fromtimestamp(ts, tz=BR_TZ)
        except ValueError:
            pass

    if data_registro < entrada:
        return jsonify({"acao": "erro", "mensagem": "Data de saída anterior à entrada!"}), 400

    registro_aberto.data_saida = data_registro
    try:
        db.session.commit()
        return jsonify(registro_aberto.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"acao": "erro", "mensagem": f"Erro ao atualizar no banco: {str(e)}"}), 500
ultimo_cartao_lido = None

@app.route('/api/capturar-nfc', methods=['POST'])
def capturar_nfc():
    global ultimo_cartao_lido
    data = request.json
    if data and 'card_uid' in data:
        ultimo_cartao_lido = data['card_uid']
        return jsonify({"status": "recebido"}), 200
    return jsonify({"status": "erro"}), 400

@app.route('/api/get-ultimo-cartao', methods=['GET'])
def get_ultimo_cartao():
    global ultimo_cartao_lido
    temp = ultimo_cartao_lido
    ultimo_cartao_lido = None # Limpa após a leitura
    return jsonify({"card_uid": temp})

@app.route('/ponto/total/<string:card_uid>', methods=['GET'])
def get_totais_por_usuario(card_uid):
    return calcular_totais(card_uid=card_uid)

@app.route('/ponto/total/by-name/<string:nome>', methods=['GET'])
def get_totais_by_name(nome):
    return calcular_totais(nome=nome)

# rota administrativa chamada pelo Arduino às 18:30 local para evitar pontos abertos
# ela fecha qualquer registro sem saída atribuindo 16:00 do dia da entrada
@app.route('/fechar-abertos', methods=['POST'])
def fechar_abertos():
    """Ecxeuta o ‘fechamento automático’ de pontos em aberto.
    Ao ser invocada (p.ex. pelo Arduino às 18:30) percorre todos os registros
    ainda sem data_saida e define data_saida para 16:00 da mesma data da
    entrada, como se o usuário tivesse esquecido de bater o ponto.

    Retorna JSON com o número de registros ajustados.
    """
    registros_abertos = RegistroPonto.query.filter_by(data_saida=None).all()
    count = 0
    for reg in registros_abertos:
        if not reg.data_entrada:
            continue
        entrada_dt = reg.data_entrada
        # extrai a data local
        dia = entrada_dt.date()
        fechamento_local = datetime(dia.year, dia.month, dia.day, 16, 0, tzinfo=BR_TZ)
        # não retroceder se a entrada ocorreu após 16h
        if fechamento_local < entrada_dt:
            fechamento_local = entrada_dt
        reg.data_saida = fechamento_local
        count += 1
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'mensagem': f'Erro ao fechar registros: {str(e)}'}), 500

    return jsonify({'mensagem': f'{count} registros fechados', 'count': count})

# ROTA PARA EDITAR NOME DO USUÁRIO
@app.route('/api/usuarios/<int:id>', methods=['PUT'])
def editar_usuario(id):
    usuario = Usuario.query.get(id)
    if not usuario:
        return jsonify({"mensagem": "Usuário não encontrado"}), 404
    
    data = request.json
    if 'nome' in data:
        usuario.nome = data['nome']
    
    try:
        db.session.commit()
        return jsonify({"mensagem": "Usuário atualizado com sucesso"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"mensagem": f"Erro: {str(e)}"}), 500

# ROTA PARA EDITAR HORÁRIOS DE UM PONTO
@app.route('/api/historico/<int:id>', methods=['PUT'])
def editar_ponto(id):
    registro = RegistroPonto.query.get(id)
    if not registro:
        return jsonify({"mensagem": "Registro não encontrado"}), 404
    
    data = request.json
    try:
        if 'entrada' in data:
            # Converte string ISO para objeto datetime aware BR
            dt = datetime.fromisoformat(data['entrada'].replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BR_TZ)
            registro.data_entrada = dt.astimezone(BR_TZ)
        if 'saida' in data:
            dt = datetime.fromisoformat(data['saida'].replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BR_TZ)
            registro.data_saida = dt.astimezone(BR_TZ)
        
        db.session.commit()
        return jsonify({"mensagem": "Ponto corrigido!"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"mensagem": str(e)}), 500

def calcular_totais(card_uid=None, nome=None):
    try:
        if card_uid:
            usuario = Usuario.query.filter_by(card_uid=card_uid).first()
        else:
            usuario = Usuario.query.filter_by(nome=nome).first()

        if not usuario:
            return jsonify({"mensagem": "Usuário não encontrado."}), 404

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

        registros = RegistroPonto.query.filter(
            RegistroPonto.id_usuario == usuario.id,
            RegistroPonto.data_saida != None
        ).all()

        totals_sec = {'day': 0.0, 'week': 0.0, 'month': 0.0, 'total': 0.0}

        def overlap_seconds(start_a_aware, end_a_aware, start_b_aware, end_b_aware):
            latest_start = max(start_a_aware, start_b_aware)
            earliest_end = min(end_a_aware, end_b_aware)
            delta = (earliest_end - latest_start).total_seconds()
            return max(0.0, delta)

        def to_br_tz(dt):
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BR_TZ)
            return dt.astimezone(BR_TZ)

        for r in registros:
            s_local = to_br_tz(r.data_entrada)
            e_local = to_br_tz(r.data_saida)
            if not s_local or not e_local:
                continue

            # Já está agora convertido para BR_TZ
            dur_sec = (e_local - s_local).total_seconds()
            if dur_sec < 0:
                continue

            totals_sec['total'] += dur_sec
            totals_sec['day'] += overlap_seconds(s_local, e_local, day_start_local, day_end_local)
            totals_sec['week'] += overlap_seconds(s_local, e_local, week_start_local, week_end_local)
            totals_sec['month'] += overlap_seconds(s_local, e_local, month_start_local, month_end_local)

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
            'usuario': {'id_usuario': usuario.id, 'nome_usuario': usuario.nome, 'card_uid': usuario.card_uid},
            'periodos': {
                'dia': {'horas': h_dia, 'minutos': m_dia, 'segundos': s_dia},
                'semana': {'horas': h_sem, 'minutos': m_sem, 'segundos': s_sem},
                'mes': {'horas': h_mes, 'minutos': m_mes, 'segundos': s_mes},
                'total': {'horas': h_tot, 'minutos': m_tot, 'segundos': s_tot}
            }
        }

        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'mensagem': f'Erro interno ao calcular totais: {str(e)}'}), 500

# 7. Roda o servidor
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
