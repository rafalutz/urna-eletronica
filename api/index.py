import os
import json
import time
import base64
import datetime
import random
from flask import (
    Flask, render_template, jsonify, request,
    redirect, url_for, session, send_from_directory, make_response
)
from jinja2 import ChoiceLoader, FileSystemLoader
from urllib.parse import parse_qs
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR) if os.path.basename(BASE_DIR) == "api" else BASE_DIR

app = Flask(__name__)
app.secret_key = "urna-electoral-secret-2024-vercel-key"

# ─── Vercel Path Middleware ──────────────────────────────────────────────────

class VercelPathMiddleware:
    """Restaura o caminho original da requisicao no WSGI a partir do parametro __path ou headers da Vercel."""
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        qs = parse_qs(environ.get("QUERY_STRING", ""))
        if "__path" in qs and qs["__path"]:
            sub = "/" + qs["__path"][0].lstrip("/")
            environ["PATH_INFO"] = sub
        else:
            for header in ("HTTP_X_FORWARDED_URI", "REQUEST_URI", "HTTP_X_MATCHED_PATH"):
                val = environ.get(header)
                if val:
                    clean_path = val.split("?")[0]
                    if clean_path and clean_path not in ("/api/index", "/api/index.py", "/"):
                        environ["PATH_INFO"] = clean_path
                        break
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)

@app.after_request
def add_no_cache_headers(response):
    """Evita cache na CDN da Vercel para que votos e candidatos atualizem em tempo real."""
    if not request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# ─── Template Loader ─────────────────────────────────────────────────────────

template_dirs = [
    os.path.join(BASE_DIR, "templates"),
    os.path.join(ROOT_DIR, "templates"),
    os.path.join(BASE_DIR, "api", "templates"),
    os.path.join(ROOT_DIR, "api", "templates"),
]
valid_dirs = [d for d in template_dirs if os.path.exists(d)]
if valid_dirs:
    app.jinja_loader = ChoiceLoader([FileSystemLoader(d) for d in valid_dirs])

# ─── File helpers ─────────────────────────────────────────────────────────────

TMP_DIR = "/tmp" if os.path.exists("/tmp") else BASE_DIR

def resolver_arquivo(nome):
    # Prioriza /tmp se já existir (para manter estado na instância serverless)
    tmp_candidate = os.path.join(TMP_DIR, nome)
    if os.path.exists(tmp_candidate):
        return tmp_candidate
    candidatos = [
        os.path.join(BASE_DIR, nome),
        os.path.join(ROOT_DIR, nome),
        os.path.join(ROOT_DIR, "api", nome),
        nome
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    return os.path.join(BASE_DIR, nome)

ELEITORES_DB_FILE = "eleitores_votados.json"
VOTOS_DB_FILE     = "votos.json"
CANDIDATOS_FILE   = "candidatos.json"
META_FILE         = "urna_meta.json"

# Pasta para upload de fotos (usa /tmp como fallback na Vercel)
FOTOS_DIR = os.path.join(BASE_DIR, "static", "fotos")
try:
    os.makedirs(FOTOS_DIR, exist_ok=True)
except OSError:
    FOTOS_DIR = os.path.join(TMP_DIR, "fotos")
    os.makedirs(FOTOS_DIR, exist_ok=True)

# ─── Candidatos padrão ────────────────────────────────────────────────────────

CANDIDATOS_PADRAO = [
    {"numero": "10", "nome": "Ana Silva",    "partido": "PARTIDO A", "vice": "Carlos Lima",   "foto_char": "👩", "cor": "#3b82f6", "foto_path": ""},
    {"numero": "20", "nome": "Bruno Santos", "partido": "PARTIDO B", "vice": "Diana Costa",   "foto_char": "👨", "cor": "#10b981", "foto_path": ""},
    {"numero": "30", "nome": "Clara Melo",   "partido": "PARTIDO C", "vice": "Eduardo Neto",  "foto_char": "👩", "cor": "#8b5cf6", "foto_path": ""},
    {"numero": "40", "nome": "Daniel Rocha", "partido": "PARTIDO D", "vice": "Fernanda Dias", "foto_char": "👨", "cor": "#f59e0b", "foto_path": ""},
    {"numero": "50", "nome": "Elena Braga",  "partido": "PARTIDO E", "vice": "Gabriel Souza", "foto_char": "👩", "cor": "#ec4899", "foto_path": ""},
]

_MEMORIA_CACHE = {}

# ─── JSON persistence ─────────────────────────────────────────────────────────

def carregar_json(nome_arquivo, padrao):
    nome = os.path.basename(nome_arquivo)
    if nome in _MEMORIA_CACHE:
        return _MEMORIA_CACHE[nome]

    # 1. Tenta ler de /tmp (escritas recentes em serverless)
    tmp_path = os.path.join(TMP_DIR, nome)
    if os.path.exists(tmp_path):
        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                dados = json.load(f)
                _MEMORIA_CACHE[nome] = dados
                return dados
        except Exception:
            pass

    # 2. Tenta ler dos diretórios do projeto
    for pasta in (BASE_DIR, ROOT_DIR, os.path.join(ROOT_DIR, "api")):
        caminho = os.path.join(pasta, nome)
        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                    _MEMORIA_CACHE[nome] = dados
                    return dados
            except Exception:
                pass

    _MEMORIA_CACHE[nome] = padrao
    return padrao

def salvar_json(nome_arquivo, dados):
    nome = os.path.basename(nome_arquivo)
    _MEMORIA_CACHE[nome] = dados

    # Salva em todos os locais possíveis (local + /tmp)
    caminhos = [
        os.path.join(TMP_DIR, nome),
        os.path.join(BASE_DIR, nome),
        os.path.join(ROOT_DIR, nome),
    ]
    for caminho in caminhos:
        try:
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

def obter_meta():
    return carregar_json(META_FILE, {"cand_ts": 0, "reset_ts": 0})

def atualizar_meta(cand_ts=None, reset_ts=None):
    meta = dict(obter_meta())
    agora_ms = int(time.time() * 1000)
    if cand_ts is not None:
        meta["cand_ts"] = cand_ts if cand_ts > 0 else agora_ms
    if reset_ts is not None:
        meta["reset_ts"] = reset_ts if reset_ts > 0 else agora_ms
    salvar_json(META_FILE, meta)
    return meta

# ─── Candidatos helpers ───────────────────────────────────────────────────────

def converter_foto_local_para_base64(foto_path):
    """Se foto_path for um caminho /static/fotos/..., converte para data URI base64 para nunca falhar na Vercel."""
    if not foto_path or foto_path.startswith("data:"):
        return foto_path
    rel = foto_path.lstrip("/")
    possiveis = [
        os.path.join(BASE_DIR, rel),
        os.path.join(ROOT_DIR, rel),
        os.path.join(ROOT_DIR, "api", rel),
        os.path.join(TMP_DIR, os.path.basename(rel)),
        os.path.join(FOTOS_DIR, os.path.basename(rel)),
    ]
    for p in possiveis:
        if os.path.exists(p) and os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    raw = f.read()
                ext = os.path.splitext(p)[1].lower()
                mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
                b64 = base64.b64encode(raw).decode("ascii")
                return f"data:{mime};base64,{b64}"
            except Exception:
                pass
    return foto_path

def carregar_candidatos():
    """Carrega candidatos do JSON, usando padrão se não existir."""
    dados = carregar_json(CANDIDATOS_FILE, None)
    if not dados:
        salvar_json(CANDIDATOS_FILE, CANDIDATOS_PADRAO)
        return [dict(c) for c in CANDIDATOS_PADRAO]
    alterado = False
    for c in dados:
        fp = c.get("foto_path", "")
        if fp and not fp.startswith("data:"):
            novo_fp = converter_foto_local_para_base64(fp)
            if novo_fp != fp:
                c["foto_path"] = novo_fp
                alterado = True
    if alterado:
        salvar_json(CANDIDATOS_FILE, dados)
    return dados

def salvar_candidatos(candidatos):
    salvar_json(CANDIDATOS_FILE, candidatos)
    atualizar_meta(cand_ts=int(time.time() * 1000))

def get_candidatos():
    return carregar_candidatos()

def processar_upload_foto(foto_file, numero):
    """Converte a foto enviada para Data URI base64 (100% compatível com Vercel serverless)."""
    if not foto_file or not foto_file.filename:
        return ""
    raw_bytes = foto_file.read()
    if not raw_bytes:
        return ""
    try:
        fname = secure_filename(f"{numero}_{foto_file.filename}")
        with open(os.path.join(FOTOS_DIR, fname), "wb") as f:
            f.write(raw_bytes)
    except Exception:
        pass
    mime = foto_file.mimetype or "image/png"
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"

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

# ─── Sincronização Serverless (evita perda de dados entre instâncias Vercel) ──

def sincronizar_estado_cliente(payload):
    """
    Mescla de forma segura o estado enviado pelo navegador caso esta instância
    serverless da Vercel tenha acabado de reiniciar (cold start).
    """
    if not payload or not isinstance(payload, dict):
        return

    meta_srv = obter_meta()
    srv_reset_ts = meta_srv.get("reset_ts", 0)
    srv_cand_ts = meta_srv.get("cand_ts", 0)

    cli_reset_ts = int(payload.get("reset_ts") or 0)
    cli_cand_ts  = int(payload.get("cand_ts") or 0)

    # 1. Se o cliente tem um reset mais recente que esta instância, aplica o reset
    if cli_reset_ts > srv_reset_ts:
        salvar_json(VOTOS_DB_FILE, [])
        salvar_json(ELEITORES_DB_FILE, [])
        atualizar_meta(reset_ts=cli_reset_ts)
        srv_reset_ts = cli_reset_ts

    # 2. Se o cliente tem alterações de candidatos (Admin) mais recentes que esta instância, aplica
    cli_candidatos = payload.get("candidatos")
    if isinstance(cli_candidatos, list) and len(cli_candidatos) > 0 and cli_cand_ts > srv_cand_ts:
        salvar_json(CANDIDATOS_FILE, cli_candidatos)
        atualizar_meta(cand_ts=cli_cand_ts)

    # 3. Se o reset do cliente é compatível (>= srv_reset_ts), garante que nenhum voto computado se perca
    if cli_reset_ts >= srv_reset_ts:
        cli_votos = payload.get("votos")
        cli_eleitores = payload.get("eleitores")

        votos_srv = carregar_json(VOTOS_DB_FILE, [])
        eleitores_srv = carregar_json(ELEITORES_DB_FILE, [])

        # Mescla eleitores únicos
        if isinstance(cli_eleitores, list):
            alterou_el = False
            for el in cli_eleitores:
                if el and el not in eleitores_srv:
                    eleitores_srv.append(el)
                    alterou_el = True
            if alterou_el:
                salvar_json(ELEITORES_DB_FILE, eleitores_srv)

        # Se o cliente tem mais votos computados (após o último reset) que esta instância serverless, restaura
        if isinstance(cli_votos, list) and len(cli_votos) > len(votos_srv):
            votos_limpos = sanitizar_sigilo_votos(cli_votos)
            salvar_json(VOTOS_DB_FILE, votos_limpos)

def obter_estado_completo():
    meta = obter_meta()
    return {
        "candidatos": get_candidatos(),
        "votos": sanitizar_sigilo_votos(carregar_json(VOTOS_DB_FILE, [])),
        "eleitores": carregar_json(ELEITORES_DB_FILE, []),
        "cand_ts": meta.get("cand_ts", 0),
        "reset_ts": meta.get("reset_ts", 0),
    }

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

    def sort_key(x):
        try:
            num_int = -int(x["numero"])
        except ValueError:
            num_int = 0
        return (x["votos"], num_int)

    candidatos_apuracao.sort(key=sort_key, reverse=True)

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
        "total_votos":          total_votos,
        "total_comparecimento": total_comparecimento,
        "candidatos":           candidatos_apuracao,
        "lider":                lider,
        "sigilo":               sigilo_info,
        "ultima_atualizacao":   agora,
        "estado_sync":          obter_estado_completo()
    }

def render_tela_apuracao(dados):
    try:
        return render_template("index.html", dados=dados)
    except Exception:
        return render_template("apuracao.html", dados=dados)

# ─── Auth helper ──────────────────────────────────────────────────────────────

def admin_logado():
    return session.get("admin_logado") is True

# ─── Despachante unificado para Vercel (__path / catch_all) ──────────────────

def despachar_rota(caminho):
    p = caminho.strip("/").replace("api/index/", "").split("?")[0]
    if p == "boletim":
        return boletim()
    elif p == "api/apuracao":
        return api_apuracao()
    elif p == "api/sync":
        return api_sync()
    elif p == "api/votar":
        return api_votar()
    elif p == "api/zerar":
        return zerar()
    elif p == "api/candidatos":
        return api_candidatos()
    elif p == "votar":
        return votar()
    elif p.startswith("static/"):
        filename = p[len("static/"):]
        return static_files(filename)
    elif p == "admin/logout":
        return admin_logout()
    elif p == "admin/login":
        return admin_login()
    elif p.startswith("admin/candidato/delete/"):
        numero = p[len("admin/candidato/delete/"):]
        return admin_candidato_delete(numero)
    elif p.startswith("admin/candidato/edit/"):
        numero = p[len("admin/candidato/edit/"):]
        return admin_candidato_edit(numero)
    elif p == "admin/candidato/add":
        return admin_candidato_add()
    elif p == "admin":
        return admin()
    return None

# ─── Rotas principais ─────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
@app.route("/apuracao", methods=["GET", "POST"])
@app.route("/api/index", methods=["GET", "POST"])
@app.route("/api/index/", methods=["GET", "POST"])
def index():
    p = request.args.get("__path", "")
    if p:
        resp = despachar_rota(p)
        if resp is not None:
            return resp

    dados = obter_dados_apuracao()
    return render_tela_apuracao(dados)

@app.route("/api/apuracao", methods=["GET", "POST"])
@app.route("/api/index/api/apuracao", methods=["GET", "POST"])
def api_apuracao():
    if request.method == "POST":
        try:
            payload = request.get_json(force=True, silent=True)
            sincronizar_estado_cliente(payload)
        except Exception:
            pass
    dados = obter_dados_apuracao()
    return jsonify(dados)

@app.route("/api/sync", methods=["POST"])
@app.route("/api/index/api/sync", methods=["POST"])
def api_sync():
    try:
        payload = request.get_json(force=True, silent=True)
        sincronizar_estado_cliente(payload)
    except Exception:
        pass
    return jsonify({"success": True, "estado_sync": obter_estado_completo()})

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
    atualizar_meta(reset_ts=int(time.time() * 1000))
    return jsonify({
        "success": True,
        "message": "Urna resetada com sucesso!",
        "estado_sync": obter_estado_completo()
    })

@app.route("/api/votar", methods=["POST"])
@app.route("/api/index/api/votar", methods=["POST"])
def api_votar():
    try:
        dados = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "error": "JSON inválido"}), 400

    if not dados or "voto" not in dados:
        return jsonify({"success": False, "error": "Dados de voto ausentes"}), 400

    # Se o cliente enviou seu estado atual junto com o voto, sincroniza antes de computar
    if "estado_sync" in dados:
        sincronizar_estado_cliente(dados.get("estado_sync"))

    voto_recebido = dados.get("voto", {})
    cpf_eleitor   = str(dados.get("cpf_eleitor", "")).strip()

    eleitores = list(carregar_json(ELEITORES_DB_FILE, []))
    votos     = list(carregar_json(VOTOS_DB_FILE, []))

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
        "total_votos": len(votos),
        "estado_sync": obter_estado_completo()
    })

# ─── API candidatos (para página de votação) ─────────────────────────────────

@app.route("/api/candidatos", methods=["GET", "POST"])
@app.route("/api/index/api/candidatos", methods=["GET", "POST"])
def api_candidatos():
    if request.method == "POST":
        try:
            payload = request.get_json(force=True, silent=True)
            sincronizar_estado_cliente(payload)
        except Exception:
            pass
    candidatos = get_candidatos()
    return jsonify(candidatos)

# ─── Votação ─────────────────────────────────────────────────────────────────

@app.route("/votar")
@app.route("/api/index/votar")
def votar():
    return render_template("votar.html", estado_sync=obter_estado_completo())

# ─── Arquivos estáticos ───────────────────────────────────────────────────────

@app.route("/static/<path:filename>")
@app.route("/api/index/static/<path:filename>")
def static_files(filename):
    for d in (
        os.path.join(BASE_DIR, "static"),
        os.path.join(ROOT_DIR, "static"),
        os.path.join(ROOT_DIR, "api", "static"),
        TMP_DIR,
    ):
        if os.path.exists(os.path.join(d, filename)):
            return send_from_directory(d, filename)
    return send_from_directory(os.path.join(BASE_DIR, "static"), filename)

# ─── Admin login ─────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
@app.route("/api/index/admin/login", methods=["GET", "POST"])
def admin_login():
    erro = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        senha    = request.form.get("senha", "").strip()
        if username == "admin" and senha == "1234":
            session["admin_logado"] = True
            return redirect("/admin")
        else:
            erro = "Usuário ou senha incorretos."
    return render_template("admin_login.html", erro=erro)

@app.route("/admin/logout")
@app.route("/api/index/admin/logout")
def admin_logout():
    session.pop("admin_logado", None)
    return redirect("/admin/login")

# ─── Admin painel ─────────────────────────────────────────────────────────────

@app.route("/admin")
@app.route("/api/index/admin")
def admin():
    if not admin_logado():
        return redirect("/admin/login")
    candidatos = get_candidatos()
    msg = request.args.get("msg", "")
    return render_template("admin.html", candidatos=candidatos, msg=msg, estado_sync=obter_estado_completo())

# ─── Admin: adicionar candidato ───────────────────────────────────────────────

@app.route("/admin/candidato/add", methods=["GET", "POST"])
@app.route("/api/index/admin/candidato/add", methods=["GET", "POST"])
def admin_candidato_add():
    if not admin_logado():
        return redirect("/admin/login")
    erro = None
    if request.method == "POST":
        # Sincroniza lista prévia enviada pelo form caso o container tenha sofrido cold start
        backup_json = request.form.get("candidatos_backup", "")
        if backup_json:
            try:
                b_cands = json.loads(backup_json)
                if isinstance(b_cands, list) and len(b_cands) > 0:
                    salvar_json(CANDIDATOS_FILE, b_cands)
            except Exception:
                pass

        numero    = request.form.get("numero", "").strip()
        nome      = request.form.get("nome", "").strip()
        partido   = request.form.get("partido", "").strip()
        vice      = request.form.get("vice", "").strip()
        foto_char = request.form.get("foto_char", "🗳️").strip() or "🗳️"
        cor       = request.form.get("cor", "#3b82f6").strip()
        foto_path = ""

        candidatos = list(get_candidatos())
        if any(c["numero"] == numero for c in candidatos):
            erro = f"Número {numero} já existe. Escolha outro número."
        elif not numero or not nome:
            erro = "Número e nome são obrigatórios."
        else:
            foto = request.files.get("foto")
            if foto and foto.filename:
                foto_path = processar_upload_foto(foto, numero)

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
            return redirect(f"/admin?msg=Candidato+{nome}+adicionado+com+sucesso!")

    return render_template("admin_form.html", modo="add", candidato=None, erro=erro, estado_sync=obter_estado_completo())

# ─── Admin: editar candidato ─────────────────────────────────────────────────

@app.route("/admin/candidato/edit/<numero>", methods=["GET", "POST"])
@app.route("/api/index/admin/candidato/edit/<numero>", methods=["GET", "POST"])
def admin_candidato_edit(numero):
    if not admin_logado():
        return redirect("/admin/login")

    if request.method == "POST":
        backup_json = request.form.get("candidatos_backup", "")
        if backup_json:
            try:
                b_cands = json.loads(backup_json)
                if isinstance(b_cands, list) and len(b_cands) > 0:
                    salvar_json(CANDIDATOS_FILE, b_cands)
            except Exception:
                pass

    candidatos = list(get_candidatos())
    candidato  = next((c for c in candidatos if c["numero"] == numero), None)
    if not candidato and request.method == "GET":
        # Cria placeholder que será preenchido pelo backup do cliente se necessário
        candidato = {"numero": numero, "nome": "", "partido": "", "vice": "", "foto_char": "🗳️", "cor": "#3b82f6", "foto_path": ""}

    erro = None
    if request.method == "POST":
        nome      = request.form.get("nome", "").strip()
        partido   = request.form.get("partido", "").strip()
        vice      = request.form.get("vice", "").strip()
        foto_char = request.form.get("foto_char", (candidato or {}).get("foto_char", "🗳️")).strip() or "🗳️"
        cor       = request.form.get("cor", (candidato or {}).get("cor", "#3b82f6")).strip()
        foto_path = (candidato or {}).get("foto_path", "")

        if not nome:
            erro = "Nome é obrigatório."
        else:
            foto = request.files.get("foto")
            if foto and foto.filename:
                nova_foto = processar_upload_foto(foto, numero)
                if nova_foto:
                    foto_path = nova_foto

            encontrou = False
            for c in candidatos:
                if c["numero"] == numero:
                    c["nome"]      = nome
                    c["partido"]   = partido
                    c["vice"]      = vice
                    c["foto_char"] = foto_char
                    c["cor"]       = cor
                    c["foto_path"] = foto_path
                    encontrou = True
                    break
            if not encontrou:
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
            return redirect(f"/admin?msg=Candidato+{nome}+atualizado+com+sucesso!")

    return render_template("admin_form.html", modo="edit", candidato=candidato, erro=erro, estado_sync=obter_estado_completo())

# ─── Admin: excluir candidato ────────────────────────────────────────────────

@app.route("/admin/candidato/delete/<numero>", methods=["POST"])
@app.route("/api/index/admin/candidato/delete/<numero>", methods=["POST"])
def admin_candidato_delete(numero):
    if not admin_logado():
        return redirect("/admin/login")

    backup_json = request.form.get("candidatos_backup", "")
    if backup_json:
        try:
            b_cands = json.loads(backup_json)
            if isinstance(b_cands, list) and len(b_cands) > 0:
                salvar_json(CANDIDATOS_FILE, b_cands)
        except Exception:
            pass

    candidatos = get_candidatos()
    candidatos = [c for c in candidatos if c["numero"] != numero]
    salvar_candidatos(candidatos)
    return redirect(f"/admin?msg=Candidato+{numero}+removido.")

# ─── Catch-all (Vercel compatibility) ────────────────────────────────────────

@app.route("/<path:subpath>", methods=["GET", "POST"])
def catch_all(subpath):
    resp = despachar_rota(subpath)
    if resp is not None:
        return resp
    dados = obter_dados_apuracao()
    return render_tela_apuracao(dados)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
