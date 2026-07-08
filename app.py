"""
Doar+ - Plataforma de doação de itens
--------------------------------------
Backend Flask com SQLite. Recria as telas do protótipo Stitch:
Home, Feed, Detalhes da Doação, Publicar Doação, Login, Cadastro,
Recuperar Senha, Perfil, Recompensas e Painel Admin.

Este é um projeto de ESTUDO: senhas são armazenadas com hash (boa prática),
mas não há envio real de e-mail de recuperação, nem verificação de identidade.
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "chave-secreta-para-estudo-troque-em-producao"

DB_PATH = os.path.join(os.path.dirname(__file__), "doarmais.db")

CATEGORIAS = ["Móveis", "Eletrônicos", "Roupas", "Brinquedos", "Alimentos", "Livros", "Outros"]
CONDICOES = ["Novo", "Seminovo", "Usado"]
PONTOS_TAMANHO = {"Pequeno": 100, "Médio": 200, "Grande": 500, "Extraordinário": 1000}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            city TEXT DEFAULT 'Não informado',
            points INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            condition TEXT NOT NULL,
            size TEXT NOT NULL,
            description TEXT,
            city TEXT,
            points INTEGER NOT NULL,
            status TEXT DEFAULT 'pendente',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            cost_points INTEGER NOT NULL,
            category TEXT NOT NULL
        )
    """)
    # popula recompensas padrão se a tabela estiver vazia
    if conn.execute("SELECT COUNT(*) as c FROM rewards").fetchone()["c"] == 0:
        conn.executemany(
            "INSERT INTO rewards (name, description, cost_points, category) VALUES (?, ?, ?, ?)",
            [
                ("Vale-compras R$50", "Válido em toda rede de parceiros sustentáveis.", 500, "Cupons"),
                ("Ecobag Doar+", "Algodão 100% orgânico e produção ética local.", 350, "Produtos"),
                ("Garrafa Térmica", "Aço inox, mantém temperatura por até 12h.", 800, "Produtos"),
                ("Café da Manhã", "Voucher para 2 pessoas no Café Harmonia.", 600, "Parceiros"),
                ("Badge de Herói", "Certificado digital e destaque no seu perfil.", 200, "Exclusivo"),
            ]
        )
    conn.commit()
    conn.close()


def calcular_pontos(size, condition):
    pontos = PONTOS_TAMANHO.get(size, 100)
    if condition in ("Novo", "Seminovo"):
        pontos += 50
    return pontos


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Você precisa entrar na sua conta para continuar.")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session or not session.get("is_admin"):
            flash("Acesso restrito ao painel administrativo.")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return wrapper


def usuario_atual():
    if "user_id" not in session:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return user


@app.context_processor
def inject_user():
    return {"current_user": usuario_atual()}


# ---------- HOME ----------
@app.route("/")
def home():
    conn = get_db()
    total_pessoas = conn.execute("SELECT COUNT(DISTINCT user_id) as c FROM items").fetchone()["c"]
    total_itens = conn.execute("SELECT COUNT(*) as c FROM items WHERE status='aprovado'").fetchone()["c"]
    total_pontos = conn.execute("SELECT COALESCE(SUM(points),0) as s FROM items WHERE status='aprovado'").fetchone()["s"]
    destaques = conn.execute(
        "SELECT items.*, users.name as doador FROM items JOIN users ON items.user_id = users.id "
        "WHERE items.status='aprovado' ORDER BY items.id DESC LIMIT 4"
    ).fetchall()
    conn.close()
    return render_template(
        "home.html",
        total_pessoas=total_pessoas,
        total_itens=total_itens,
        total_pontos=total_pontos,
        destaques=destaques,
    )


# ---------- FEED ----------
@app.route("/feed")
def feed():
    categoria = request.args.get("categoria", "")
    conn = get_db()
    if categoria and categoria in CATEGORIAS:
        itens = conn.execute(
            "SELECT items.*, users.name as doador FROM items JOIN users ON items.user_id = users.id "
            "WHERE items.status='aprovado' AND items.category = ? ORDER BY items.id DESC",
            (categoria,)
        ).fetchall()
    else:
        itens = conn.execute(
            "SELECT items.*, users.name as doador FROM items JOIN users ON items.user_id = users.id "
            "WHERE items.status='aprovado' ORDER BY items.id DESC"
        ).fetchall()
    conn.close()
    return render_template("feed.html", itens=itens, categorias=CATEGORIAS, categoria_ativa=categoria)


# ---------- DETALHES DO ITEM ----------
@app.route("/doacao/<int:item_id>")
def item_detail(item_id):
    conn = get_db()
    item = conn.execute(
        "SELECT items.*, users.name as doador, users.city as doador_cidade "
        "FROM items JOIN users ON items.user_id = users.id WHERE items.id = ?",
        (item_id,)
    ).fetchone()
    conn.close()
    if item is None:
        flash("Essa doação não existe ou foi removida.")
        return redirect(url_for("feed"))
    return render_template("item_detail.html", item=item)


@app.route("/doacao/<int:item_id>/interesse", methods=["POST"])
@login_required
def registrar_interesse(item_id):
    flash("Interesse enviado! O doador foi notificado por e-mail.")
    return redirect(url_for("item_detail", item_id=item_id))


# ---------- PUBLICAR DOAÇÃO ----------
@app.route("/publicar", methods=["GET", "POST"])
@login_required
def publicar():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        condition = request.form.get("condition", "")
        size = request.form.get("size", "Pequeno")
        description = request.form.get("description", "").strip()

        if not name or category not in CATEGORIAS or condition not in CONDICOES:
            flash("Preencha todos os campos obrigatórios corretamente.")
            return render_template("publish.html", categorias=CATEGORIAS, condicoes=CONDICOES, pontos_tamanho=PONTOS_TAMANHO)

        pontos = calcular_pontos(size, condition)
        user = usuario_atual()

        conn = get_db()
        conn.execute(
            "INSERT INTO items (user_id, name, category, condition, size, description, city, points, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pendente', ?)",
            (user["id"], name, category, condition, size, description, user["city"], pontos, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        flash("Doação publicada! Ela passará por uma revisão rápida antes de aparecer no feed.")
        return redirect(url_for("perfil"))

    return render_template("publish.html", categorias=CATEGORIAS, condicoes=CONDICOES, pontos_tamanho=PONTOS_TAMANHO)


# ---------- AUTENTICAÇÃO ----------
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 6:
            flash("Preencha nome, e-mail e uma senha com pelo menos 6 caracteres.")
            return render_template("signup.html")

        conn = get_db()
        existente = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existente:
            conn.close()
            flash("Já existe uma conta com esse e-mail.")
            return render_template("signup.html")

        conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), datetime.now().isoformat())
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        session["user_id"] = user["id"]
        session["is_admin"] = bool(user["is_admin"])
        flash(f"Bem-vindo(a), {name}! Sua conta foi criada.")
        return redirect(url_for("home"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("E-mail ou senha incorretos.")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["is_admin"] = bool(user["is_admin"])
        flash(f"Bem-vindo(a) de volta, {user['name']}!")
        proxima = request.args.get("next") or url_for("home")
        return redirect(proxima)

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu da sua conta.")
    return redirect(url_for("home"))


@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    enviado = False
    if request.method == "POST":
        # Projeto de estudo: não envia e-mail de verdade, só simula.
        enviado = True
    return render_template("forgot_password.html", enviado=enviado)


# ---------- PERFIL ----------
@app.route("/perfil")
@login_required
def perfil():
    user = usuario_atual()
    conn = get_db()
    itens = conn.execute(
        "SELECT * FROM items WHERE user_id = ? ORDER BY id DESC", (user["id"],)
    ).fetchall()
    total_doacoes = len(itens)
    conn.close()
    return render_template("profile.html", user=user, itens=itens, total_doacoes=total_doacoes)


# ---------- RECOMPENSAS ----------
@app.route("/recompensas")
def recompensas():
    conn = get_db()
    lista = conn.execute("SELECT * FROM rewards ORDER BY cost_points ASC").fetchall()
    conn.close()
    return render_template("rewards.html", recompensas=lista)


@app.route("/recompensas/<int:reward_id>/resgatar", methods=["POST"])
@login_required
def resgatar(reward_id):
    user = usuario_atual()
    conn = get_db()
    reward = conn.execute("SELECT * FROM rewards WHERE id = ?", (reward_id,)).fetchone()

    if reward is None:
        conn.close()
        flash("Recompensa não encontrada.")
        return redirect(url_for("recompensas"))

    if user["points"] < reward["cost_points"]:
        conn.close()
        flash(f"Você precisa de mais {reward['cost_points'] - user['points']} pontos para resgatar '{reward['name']}'.")
        return redirect(url_for("recompensas"))

    conn.execute("UPDATE users SET points = points - ? WHERE id = ?", (reward["cost_points"], user["id"]))
    conn.commit()
    conn.close()
    flash(f"Recompensa '{reward['name']}' resgatada com sucesso!")
    return redirect(url_for("recompensas"))


# ---------- ADMIN ----------
@app.route("/admin")
@admin_required
def admin():
    conn = get_db()
    pendentes = conn.execute(
        "SELECT items.*, users.name as doador FROM items JOIN users ON items.user_id = users.id "
        "WHERE items.status = 'pendente' ORDER BY items.id ASC"
    ).fetchall()
    total_usuarios = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    total_pendentes = len(pendentes)
    total_aprovados = conn.execute("SELECT COUNT(*) as c FROM items WHERE status='aprovado'").fetchone()["c"]
    conn.close()
    return render_template(
        "admin.html",
        pendentes=pendentes,
        total_usuarios=total_usuarios,
        total_pendentes=total_pendentes,
        total_aprovados=total_aprovados,
    )


@app.route("/admin/aprovar/<int:item_id>", methods=["POST"])
@admin_required
def admin_aprovar(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if item:
        conn.execute("UPDATE items SET status = 'aprovado' WHERE id = ?", (item_id,))
        conn.execute("UPDATE users SET points = points + ? WHERE id = ?", (item["points"], item["user_id"]))
        conn.commit()
    conn.close()
    flash("Doação aprovada e pontos creditados ao doador.")
    return redirect(url_for("admin"))


@app.route("/admin/recusar/<int:item_id>", methods=["POST"])
@admin_required
def admin_recusar(item_id):
    conn = get_db()
    conn.execute("UPDATE items SET status = 'recusado' WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    flash("Doação recusada.")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
