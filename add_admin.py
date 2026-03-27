#!/usr/bin/env python3
"""
Script para inicializar o banco de dados com um admin padrão.
Execute apenas uma vez para criar a tabela de admins e adicionar um usuário admin inicial.

Uso: python add_admin.py seu@email.com
"""
import sys
import os

# Adiciona o diretório atual ao path para importar api.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import app, db, Admin

def add_admin(email):
    """Adiciona um novo administrador ao banco."""
    with app.app_context():
        # Criar as tabelas se não existirem
        db.create_all()
        
        # Verifica se o admin já existe
        admin_existente = Admin.query.filter_by(email=email.lower()).first()
        if admin_existente:
            print(f"❌ Admin com email '{email}' já existe.")
            return False
        
        # Cria novo admin
        novo_admin = Admin(email=email.lower())
        db.session.add(novo_admin)
        
        try:
            db.session.commit()
            print(f"✅ Admin '{email}' criado com sucesso!")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"❌ Erro ao criar admin: {e}")
            return False

def list_admins():
    """Lista todos os administradores."""
    with app.app_context():
        admins = Admin.query.all()
        if not admins:
            print("Nenhum administrador cadastrado.")
            return
        
        print("\n📋 Admins cadastrados:")
        for admin in admins:
            print(f"  • {admin.email}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: python add_admin.py <email>")
        print("Exemplos:")
        print("  python add_admin.py admin@exemplo.com")
        print("\nOu listar admins:")
        print("  python add_admin.py --list")
        sys.exit(1)
    
    comando = sys.argv[1]
    
    if comando == '--list':
        list_admins()
    else:
        email = comando
        add_admin(email)
