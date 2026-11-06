import os
import json
import datetime
import random
from flask import (
    Flask, render_template, jsonify, request,
    redirect, url_for, session, send_from_directory
)
from jinja2 import ChoiceLoader, FileSystemLoader
from urllib.parse import parse_qs
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)

app = Flask(__name__)
app.secret_key = 'urna-electoral-secret-2024'

# ─── Vercel Path Middleware ──────────────────────────────────────────────────

class VercelPathMiddleware:
    """Restaura o caminho original da requisicao no WSGI a partir do parametro __path ou x-matched-path da Vercel."""
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        qs = parse_qs(environ.get("QUERY_STRING", ""))
        if "__path" in qs and qs["__path"]:
            sub = "/" + qs["__path"][0].lstrip("/")
            environ["PATH_INFO"] = sub
        else:
            matched_path = environ.get("HTTP_X_MATCHED_PATH") or environ.get("HTTP_X_FORWARDED_URI")
            if matched_path:
                clean_path = matched_path.split("?")[0]
                if clean_path not in ("/api/index", "/api/index.py"):
                    environ["PATH_INFO"] = clean_path
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)

# ─── Template Loader ─────────────────────────────────────────────────────────

template_dirs = [
    os.path.join(BASE_DIR, "templates"),
    os.path.join(ROOT_DIR, "templates"),
    os.path.join(BASE_DIR, "api", "templates"),
]
valid_dirs = [d for d in template_dirs if os.path.exists(d)]
if valid_dirs:
    app.jinja_loader = ChoiceLoader([FileSystemLoader(d) for d in valid_dirs])

# ─── File helpers ─────────────────────────────────────────────────────────────

def resolver_arquivo(nome):
    candidatos = [
        os.path.join(BASE_DIR, nome),
        os.path.join(ROOT_DIR, nome),
        nome
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    return os.path.join(BASE_DIR, nome)

ELEITORES_DB_FILE = resolver_arquivo("eleitores_votados.json")
VOTOS_DB_FILE     = resolver_arquivo("votos.json")
CANDIDATOS_FILE   = resolver_arquivo("candidatos.json")

# Pasta para upload de fotos
FOTOS_DIR = os.path.join(BASE_DIR, "static", "fotos")
os.makedirs(FOTOS_DIR, exist_ok=True)

# ─── Candidatos padrão ────────────────────────────────────────────────────────

CANDIDATOS_PADRAO = [
    {"numero": "10", "nome": "Ana Silva",    "partido": "PARTIDO A", "vice": "Carlos Lima",   "foto_char": "👩", "cor": "#3b82f6", "foto_path": ""},
    {"numero": "20", "nome": "Bruno Santos", "partido": "PARTIDO B", "vice": "Diana Costa",   "foto_char": "👨", "cor": "#10b981", "foto_path": ""},
    {"numero": "30", "nome": "Clara Melo",   "partido": "PARTIDO C", "vice": "Eduardo Neto",  "foto_char": "👩", "cor": "#8b5cf6", "foto_path": ""},
    {"numero": "40", "nome": "Daniel Rocha", "partido": "PARTIDO D", "vice": "Fernanda Dias", "foto_char": "👨", "cor": "#f59e0b", "foto_path": ""},
    {"numero": "50", "nome": "Elena Braga",  "partido": "PARTIDO E", "vice": "Gabriel Souza", "foto_char": "👩", "cor": "#ec4899", "foto_path": ""},
]

TMP_DIR = "/tmp" if os.path.exists("/tmp") else BASE_DIR

_MEMORIA_CACHE = {}

# ─── JSON persistence ─────────────────────────────────────────────────────────

def carregar_json(arquivo, padrao):
    if arquivo in _MEMORIA_CACHE:
        return _MEMORIA_CACHE[arquivo]
    nome = os.path.basename(arquivo)
    tmp_path = os.path.join(TMP_DIR, nome)
    if os.path.exists(tmp_path):
        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                dados = json.load(f)
                _MEMORIA_CACHE[arquivo] = dados
                return dados
        except Exception:
            pass
    if os.path.exists(arquivo):
        try:
            with open(arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)
                _MEMORIA_CACHE[arquivo] = dados
                return dados
        except Exception:
            return padrao
    _MEMORIA_CACHE[arquivo] = padrao
    return padrao

def salvar_json(arquivo, dados):
    _MEMORIA_CACHE[arquivo] = dados
    try:
        with open(arquivo, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except (OSError, IOError, PermissionError):
        pass
    try:
        nome = os.path.basename(arquivo)
        tmp_path = os.path.join(TMP_DIR, nome)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ─── Candidatos helpers ───────────────────────────────────────────────────────

def carregar_candidatos():
    """Carrega candidatos do JSON, usando padrão se não existir."""
    dados = carregar_json(CANDIDATOS_FILE, None)
    if dados is None:
        # Primeira vez: salva o padrão
        salvar_json(CANDIDATOS_FILE, CANDIDATOS_PADRAO)
        return list(CANDIDATOS_PADRAO)
    return dados

def salvar_candidatos(candidatos):
    salvar_json(CANDIDATOS_FILE, candidatos)
    # Invalida cache para forçar reload
    _MEMORIA_CACHE.pop(CANDIDATOS_FILE, None)

def get_candidatos():
    """Retorna a lista de candidatos sempre fresca."""
    _MEMORIA_CACHE.pop(CANDIDATOS_FILE, None)
    return carregar_candidatos()

# ─── Sigilo de votos ─────────────────────────────────────────────────────────

def sanitizar_sigilo_votos(votos):
    alterado = False
    votos_limpos = []
    campos_proibidos = ["cpf_eleitor", "cpf", "nome_eleitor", "eleitor", "identificacao"]
    for v in votos:
        novo_voto = {}
        for k, val in v.items():
            if k.lower() in campos_proibidos:
                alterado = True
            else:
                novo_voto[k] = val
        votos_limpos.append(novo_voto)
    if alterado:
        salvar_json(VOTOS_DB_FILE, votos_limpos)
    return votos_limpos

# ─── Dados de apuração ────────────────────────────────────────────────────────

def obter_dados_apuracao():
    candidatos = get_candidatos()
    votos_raw = carregar_json(VOTOS_DB_FILE, [])
    votos = sanitizar_sigilo_votos(votos_raw)
    eleitores_votados = carregar_json(ELEITORES_DB_FILE, [])

    total_votos = len(votos)
    total_comparecimento = len(eleitores_votados)

    contagem = {c["numero"]: 0 for c in candidatos}
    outros_votos = 0
    for v in votos:
        num = str(v.get("numero_cand", "")).strip()
        if num in contagem:
            contagem[num] += 1
        else:
            outros_votos += 1

    candidatos_apuracao = []
    for c in candidatos:
        qnt = contagem.get(c["numero"], 0)
        perc = (qnt / total_votos * 100) if total_votos > 0 else 0.0
        candidatos_apuracao.append({
            "numero":               c["numero"],
            "nome":                 c["nome"],
            "partido":              c["partido"],
            "vice":                 c["vice"],
            "foto_char":            c.get("foto_char", "🗳️"),
            "cor":                  c.get("cor", "#3b82f6"),
            "foto_path":            c.get("foto_path", ""),
            "votos":                qnt,
            "percentual":           round(perc, 2),
            "percentual_formatado": f"{perc:.2f}%"
        })

    candidatos_apuracao.sort(key=lambda x: (x["votos"], -int(x["numero"])), reverse=True)

    for i, c in enumerate(candidatos_apuracao, 1):
        c["posicao"] = i
        if total_votos > 0:
            if i == 1 and c["votos"] > 0:
                if c["percentual"] > 50.0:
                    c["status_badge"] = "Maioria Absoluta"
                else:
                    c["status_badge"] = "Líder"
            else:
                c["status_badge"] = f"{i}º Lugar"
        else:
            c["status_badge"] = "0 Votos"

    lider = candidatos_apuracao[0] if total_votos > 0 and candidatos_apuracao and candidatos_apuracao[0]["votos"] > 0 else None

    sigilo_info = {
        "sigiloso": True,
        "campos_voto": ["numero_cand", "nome_cand", "partido_cand"],
        "desvinculado_eleitor": True,
        "mensagem": "Votos armazenados anonimamente sem vínculo com CPF ou eleitor."
    }

    agora = datetime.datetime.now().strftime("%d/%m/%Y às %H:%M:%S")

    return {
        "total_votos":        total_votos,
        "total_comparecimento": total_comparecimento,
        "candidatos":         candidatos_apuracao,
        "lider":              lider,
        "sigilo":             sigilo_info,
        "ultima_atualizacao": agora
    }

def render_tela_apuracao(dados):
    try:
        return render_template("index.html", dados=dados)
    except Exception:
        return render_template("apuracao.html", dados=dados)

# ─── Auth helper ──────────────────────────────────────────────────────────────

def admin_logado():
    return session.get("admin_logado") is True

# ─── Rotas principais ─────────────────────────────────────────────────────────

@app.route("/")
@app.route("/index")
@app.route("/apuracao")
@app.route("/api/index")
@app.route("/api/index/")
def index():
    p = request.args.get("__path", "").strip("/").split("?")[0]
    if p == "boletim":
        return boletim()
    elif p == "api/apuracao":
        return api_apuracao()
    elif p == "api/votar" and request.method == "POST":
        return api_votar()
    elif p == "api/zerar" and request.method == "POST":
        return zerar()

    dados = obter_dados_apuracao()
    return render_tela_apuracao(dados)

@app.route("/api/apuracao")
@app.route("/api/index/api/apuracao")
def api_apuracao():
    dados = obter_dados_apuracao()
    return jsonify(dados)

@app.route("/boletim")
@app.route("/api/index/boletim")
def boletim():
    dados = obter_dados_apuracao()
    return render_template("boletim.html", dados=dados)

@app.route("/api/zerar", methods=["POST"])
@app.route("/api/index/api/zerar", methods=["POST"])
def zerar():
    salvar_json(VOTOS_DB_FILE, [])
    salvar_json(ELEITORES_DB_FILE, [])
    return jsonify({"success": True, "message": "Urna resetada com sucesso!"})

@app.route("/api/votar", methods=["POST"])
@app.route("/api/index/api/votar", methods=["POST"])
def api_votar():
    try:
        dados = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "error": "JSON inválido"}), 400

    if not dados or "voto" not in dados:
        return jsonify({"success": False, "error": "Dados de voto ausentes"}), 400

    voto_recebido = dados.get("voto", {})
    cpf_eleitor   = str(dados.get("cpf_eleitor", "")).strip()

    eleitores = carregar_json(ELEITORES_DB_FILE, [])
    votos     = carregar_json(VOTOS_DB_FILE, [])

    if cpf_eleitor:
        if cpf_eleitor in eleitores:
            return jsonify({"success": False, "error": "Eleitor já votou nesta eleição."}), 400
        eleitores.append(cpf_eleitor)

    campos_permitidos = ["numero_cand", "nome_cand", "partido_cand"]
    voto_limpo = {k: voto_recebido[k] for k in campos_permitidos if k in voto_recebido}

    votos.append(voto_limpo)
    random.shuffle(votos)

    salvar_json(VOTOS_DB_FILE, votos)
    salvar_json(ELEITORES_DB_FILE, eleitores)

    return jsonify({
        "success": True,
        "message": "Voto computado com sucesso na nuvem!",
        "total_votos": len(votos)
    })

# ─── API candidatos (para página de votação) ─────────────────────────────────

@app.route("/api/candidatos")
def api_candidatos():
    candidatos = get_candidatos()
    return jsonify(candidatos)

# ─── Votação ─────────────────────────────────────────────────────────────────

@app.route("/votar")
def votar():
    return render_template("votar.html")

# ─── Arquivos estáticos ───────────────────────────────────────────────────────

@app.route("/static/<path:filename>")
def static_files(filename):
    static_dir = os.path.join(BASE_DIR, "static")
    return send_from_directory(static_dir, filename)

# ─── Admin login ─────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    erro = None
    if request.method == "POST":
        username = request.form.get("username", "")
        senha    = request.form.get("senha", "")
        if username == "admin" and senha == "1234":
            session["admin_logado"] = True
            return redirect(url_for("admin"))
        else:
            erro = "Usuário ou senha incorretos."
    return render_template("admin_login.html", erro=erro)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logado", None)
    return redirect(url_for("admin_login"))

# ─── Admin painel ─────────────────────────────────────────────────────────────

@app.route("/admin")
def admin():
    if not admin_logado():
        return redirect(url_for("admin_login"))
    candidatos = get_candidatos()
    msg = request.args.get("msg", "")
    return render_template("admin.html", candidatos=candidatos, msg=msg)

# ─── Admin: adicionar candidato ───────────────────────────────────────────────

@app.route("/admin/candidato/add", methods=["GET", "POST"])
def admin_candidato_add():
    if not admin_logado():
        return redirect(url_for("admin_login"))
    erro = None
    if request.method == "POST":
        numero   = request.form.get("numero", "").strip()
        nome     = request.form.get("nome", "").strip()
        partido  = request.form.get("partido", "").strip()
        vice     = request.form.get("vice", "").strip()
        foto_char = request.form.get("foto_char", "🗳️").strip()
        cor      = request.form.get("cor", "#3b82f6").strip()
        foto_path = ""

        candidatos = get_candidatos()
        if any(c["numero"] == numero for c in candidatos):
            erro = f"Número {numero} já existe. Escolha outro número."
        elif not numero or not nome:
            erro = "Número e nome são obrigatórios."
        else:
            # Upload de foto
            foto = request.files.get("foto")
            if foto and foto.filename:
                fname = secure_filename(f"{numero}_{foto.filename}")
                foto.save(os.path.join(FOTOS_DIR, fname))
                foto_path = f"/static/fotos/{fname}"

            candidatos.append({
                "numero":    numero,
                "nome":      nome,
                "partido":   partido,
                "vice":      vice,
                "foto_char": foto_char,
                "cor":       cor,
                "foto_path": foto_path
            })
            salvar_candidatos(candidatos)
            return redirect(url_for("admin", msg=f"Candidato {nome} adicionado com sucesso!"))

    return render_template("admin_form.html", modo="add", candidato=None, erro=erro)

# ─── Admin: editar candidato ─────────────────────────────────────────────────

@app.route("/admin/candidato/edit/<numero>", methods=["GET", "POST"])
def admin_candidato_edit(numero):
    if not admin_logado():
        return redirect(url_for("admin_login"))

    candidatos = get_candidatos()
    candidato  = next((c for c in candidatos if c["numero"] == numero), None)
    if not candidato:
        return redirect(url_for("admin", msg="Candidato não encontrado."))

    erro = None
    if request.method == "POST":
        nome      = request.form.get("nome", "").strip()
        partido   = request.form.get("partido", "").strip()
        vice      = request.form.get("vice", "").strip()
        foto_char = request.form.get("foto_char", candidato.get("foto_char", "🗳️")).strip()
        cor       = request.form.get("cor", candidato.get("cor", "#3b82f6")).strip()
        foto_path = candidato.get("foto_path", "")

        if not nome:
            erro = "Nome é obrigatório."
        else:
            # Upload de nova foto (opcional)
            foto = request.files.get("foto")
            if foto and foto.filename:
                fname = secure_filename(f"{numero}_{foto.filename}")
                foto.save(os.path.join(FOTOS_DIR, fname))
                foto_path = f"/static/fotos/{fname}"

            for c in candidatos:
                if c["numero"] == numero:
                    c["nome"]      = nome
                    c["partido"]   = partido
                    c["vice"]      = vice
                    c["foto_char"] = foto_char
                    c["cor"]       = cor
                    c["foto_path"] = foto_path
                    break

            salvar_candidatos(candidatos)
            return redirect(url_for("admin", msg=f"Candidato {nome} atualizado com sucesso!"))

    return render_template("admin_form.html", modo="edit", candidato=candidato, erro=erro)

# ─── Admin: excluir candidato ────────────────────────────────────────────────

@app.route("/admin/candidato/delete/<numero>", methods=["POST"])
def admin_candidato_delete(numero):
    if not admin_logado():
        return redirect(url_for("admin_login"))

    candidatos = get_candidatos()
    candidatos = [c for c in candidatos if c["numero"] != numero]
    salvar_candidatos(candidatos)
    return redirect(url_for("admin", msg=f"Candidato {numero} removido."))

# ─── Catch-all (Vercel compatibility) ────────────────────────────────────────

@app.route("/<path:subpath>", methods=["GET", "POST"])
def catch_all(subpath):
    clean = subpath.strip("/").replace("api/index/", "")
    if clean == "boletim":
        return boletim()
    elif clean == "api/apuracao":
        return api_apuracao()
    elif clean == "api/votar" and request.method == "POST":
        return api_votar()
    elif clean == "api/zerar" and request.method == "POST":
        return zerar()
    elif clean == "votar":
        return votar()
    elif clean == "admin":
        return admin()
    elif clean in ("admin/login",):
        return admin_login()
    elif clean == "admin/logout":
        return admin_logout()
    dados = obter_dados_apuracao()
    return render_tela_apuracao(dados)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
