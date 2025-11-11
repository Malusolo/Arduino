from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

# 1. Cria a instância do Flask
app = Flask(__name__)

# 2. Configuração do Banco de Dados MySQL
# (Mantive sua string de conexão)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:.de1ate5@localhost:3306/minha_api_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 3. Inicializa o SQLAlchemy
db = SQLAlchemy(app)

# 4. MUDANÇA: Define o "Modelo" (Schema) do Banco de Dados
class RegistroPonto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Coluna para identificar quem está batendo o ponto
    id_usuario = db.Column(db.String(100), nullable=False)
    
    # Coluna para a ENTRADA (preenchida na criação)
    data_entrada = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Coluna para a SAÍDA (pode ser nula até a pessoa sair)
    data_saida = db.Column(db.DateTime, nullable=True) 

    # Função extra para facilitar a conversão para JSON
    def to_dict(self):
        return {
            'id': self.id,
            'id_usuario': self.id_usuario,
            'data_entrada': self.data_entrada.isoformat(),
            # Retorna a data de saída ou None se ainda não foi registrada
            'data_saida': self.data_saida.isoformat() if self.data_saida else None
        }

# --- ROTAS DA API ---

@app.route('/')
def home():
    return "API de Relógio de Ponto no ar!"

# MUDANÇA: Rota para "Bater o Ponto de ENTRADA"
@app.route('/ponto/entrada', methods=['POST'])
def bater_ponto_entrada():
    data = request.json
    if not data or 'id_usuario' not in data:
        return jsonify({"mensagem": "Erro: 'id_usuario' é obrigatório."}), 400

    id_usuario = data['id_usuario']

    # 1. Verifica se este usuário já tem um ponto aberto (sem data_saida)
    registro_aberto = RegistroPonto.query.filter_by(id_usuario=id_usuario, data_saida=None).first()
    
    if registro_aberto:
        return jsonify({"mensagem": "Erro: Usuário já possui um ponto de entrada em aberto."}), 400

    # 2. Cria o novo registro de entrada
    novo_registro = RegistroPonto(id_usuario=id_usuario)
    
    try:
        db.session.add(novo_registro)
        db.session.commit()
        return jsonify(novo_registro.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"mensagem": f"Erro ao salvar no banco: {str(e)}"}), 500

# MUDANÇA: Rota para "Bater o Ponto de SAÍDA"
@app.route('/ponto/saida', methods=['POST'])
def bater_ponto_saida():
    data = request.json
    if not data or 'id_usuario' not in data:
        return jsonify({"mensagem": "Erro: 'id_usuario' é obrigatório."}), 400

    id_usuario = data['id_usuario']

    # 1. Encontra o último registro de ponto aberto (sem saída) deste usuário
    registro_aberto = RegistroPonto.query.filter_by(
        id_usuario=id_usuario, 
        data_saida=None
    ).order_by(RegistroPonto.data_entrada.desc()).first() # Pega o mais recente

    if not registro_aberto:
        return jsonify({"mensagem": "Erro: Nenhum ponto de entrada em aberto encontrado para este usuário."}), 404

    # 2. Atualiza a data de saída
    registro_aberto.data_saida = datetime.utcnow()
    
    try:
        db.session.commit()
        return jsonify(registro_aberto.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({"mensagem": f"Erro ao atualizar no banco: {str(e)}"}), 500

# Rota Bônus: Ver todos os registros de um usuário
@app.route('/ponto/usuario/<string:id_usuario>', methods=['GET'])
def get_registros_por_usuario(id_usuario):
    registros = RegistroPonto.query.filter_by(id_usuario=id_usuario).order_by(RegistroPonto.data_entrada.desc()).all()
    if not registros:
        return jsonify({"mensagem": "Nenhum registro encontrado para este usuário."}), 404
        
    return jsonify([r.to_dict() for r in registros])


# Rota: Totais de horas (dia, semana, mês e total) para um usuário
@app.route('/ponto/total/<string:id_usuario>', methods=['GET'])
def get_totais_por_usuario(id_usuario):
    """
    Retorna um JSON com o total de horas do dia, semana, mês e total acumulado
    para o usuário informado. Considera apenas registros com data_saida preenchida
    e calcula a parte do intervalo que cai em cada período (sobreposição).
    """
    now = datetime.utcnow()
    day_start = datetime(now.year, now.month, now.day)
    day_end = day_start + timedelta(days=1)

    week_start = day_start - timedelta(days=now.weekday())  # segunda-feira
    week_end = week_start + timedelta(days=7)

    month_start = datetime(now.year, now.month, 1)
    # calcula início do mês seguinte para determinar fim do mês
    if now.month == 12:
        month_end = datetime(now.year + 1, 1, 1)
    else:
        month_end = datetime(now.year, now.month + 1, 1)

    # Busca todos os registros do usuário que já tenham saída
    registros = RegistroPonto.query.filter(RegistroPonto.id_usuario == id_usuario, RegistroPonto.data_saida != None).all()

    # Inicializa acumuladores em segundos
    totals_sec = {
        'day': 0.0,
        'week': 0.0,
        'month': 0.0,
        'total': 0.0
    }

    def overlap_seconds(start_a, end_a, start_b, end_b):
        """Retorna segundos de sobreposição entre [start_a, end_a) e [start_b, end_b)."""
        latest_start = max(start_a, start_b)
        earliest_end = min(end_a, end_b)
        delta = (earliest_end - latest_start).total_seconds()
        return max(0.0, delta)

    for r in registros:
        s = r.data_entrada
        e = r.data_saida
        if not s or not e:
            continue

        # total do registro
        dur_sec = (e - s).total_seconds()
        totals_sec['total'] += dur_sec

        # adiciona a parte que cai no dia, semana e mês (fazendo cálculo de sobreposição)
        totals_sec['day'] += overlap_seconds(s, e, day_start, day_end)
        totals_sec['week'] += overlap_seconds(s, e, week_start, week_end)
        totals_sec['month'] += overlap_seconds(s, e, month_start, month_end)

    def secs_to_hours_float(sec):
        return round(sec / 3600.0, 2)

    def secs_to_hhmmss(sec):
        sec = int(sec)
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    result = {
        'id_usuario': id_usuario,
        'dia': {
            'segundos': int(totals_sec['day']),
            'horas': secs_to_hours_float(totals_sec['day']),
            'hhmmss': secs_to_hhmmss(totals_sec['day'])
        },
        'semana': {
            'segundos': int(totals_sec['week']),
            'horas': secs_to_hours_float(totals_sec['week']),
            'hhmmss': secs_to_hhmmss(totals_sec['week'])
        },
        'mes': {
            'segundos': int(totals_sec['month']),
            'horas': secs_to_hours_float(totals_sec['month']),
            'hhmmss': secs_to_hhmmss(totals_sec['month'])
        },
        'total': {
            'segundos': int(totals_sec['total']),
            'horas': secs_to_hours_float(totals_sec['total']),
            'hhmmss': secs_to_hhmmss(totals_sec['total'])
        }
    }

    return jsonify(result)

# 7. Roda o servidor
if __name__ == '__main__':
    with app.app_context():
        # Isso vai criar a nova tabela 'registro_ponto' (se ela não existir)
        db.create_all()
    app.run(debug=True, port=5000)