import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox
import json
import os
import datetime
import re
import random

# ─────────────────────────────────────────────────────────────
# BANCO DE DADOS SIMULADO
# ─────────────────────────────────────────────────────────────

CANDIDATOS = [
    {"numero": "10", "nome": "Ana Silva",    "partido": "PARTIDO A", "vice": "Carlos Lima",   "foto_char": "👩"},
    {"numero": "20", "nome": "Bruno Santos", "partido": "PARTIDO B", "vice": "Diana Costa",   "foto_char": "👨"},
    {"numero": "30", "nome": "Clara Melo",   "partido": "PARTIDO C", "vice": "Eduardo Neto",  "foto_char": "👩"},
    {"numero": "40", "nome": "Daniel Rocha", "partido": "PARTIDO D", "vice": "Fernanda Dias", "foto_char": "👨"},
    {"numero": "50", "nome": "Elena Braga",  "partido": "PARTIDO E", "vice": "Gabriel Souza", "foto_char": "👩"},
]

ELEITORES_DB_FILE = "eleitores_votados.json"
VOTOS_DB_FILE = "votos.json"

# URL do servidor de apuração (para sincronização em tempo real na nuvem ou local)
# Altere para "http://127.0.0.1:5000" se for rodar o Flask no seu computador
API_URL = os.environ.get("URNA_API_URL", "https://urna-eletronica-ruddy.vercel.app")


def carregar_json(arquivo: str, padrao) -> dict | list:
    if os.path.exists(arquivo):
        with open(arquivo, "r", encoding="utf-8") as f:
            return json.load(f)
    return padrao


def salvar_json(arquivo: str, dados) -> None:
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def validar_cpf(cpf: str) -> bool:
    """Valida CPF (formato e dígitos verificadores)."""
    cpf = re.sub(r"\D", "", cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        soma = sum(int(cpf[j]) * (i + 1 - j) for j in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[i]):
            return False
    return True


def formatar_cpf(cpf: str) -> str:
    cpf = re.sub(r"\D", "", cpf)
    if len(cpf) == 11:
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return cpf


# ─────────────────────────────────────────────────────────────
# PALETA DE CORES (estilo urna real)
# ─────────────────────────────────────────────────────────────

CORES = {
    "bg_principal":   "#1a1a2e",
    "bg_painel":      "#16213e",
    "bg_campo":       "#0f3460",
    "azul_urna":      "#0077b6",
    "azul_claro":     "#00b4d8",
    "verde":          "#06d6a0",
    "vermelho":       "#ef476f",
    "amarelo":        "#ffd166",
    "branco":         "#e0e0e0",
    "cinza":          "#aaaaaa",
    "texto_escuro":   "#0f3460",
}


# ─────────────────────────────────────────────────────────────
# APLICAÇÃO PRINCIPAL
# ─────────────────────────────────────────────────────────────

class UrnaEletronica(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Urna Eletrônica — Eleição Municipal")
        self.geometry("780x580")
        self.resizable(False, False)
        self.configure(bg=CORES["bg_principal"])

        # Dados de sessão
        self.eleitor_atual: dict | None = None
        self.candidato_selecionado: dict | None = None

        # Carrega persistência
        self.eleitores_votados: list = carregar_json(ELEITORES_DB_FILE, [])
        self.votos: list = carregar_json(VOTOS_DB_FILE, [])

        # Fontes
        self.fonte_titulo  = tkfont.Font(family="Arial", size=18, weight="bold")
        self.fonte_subtit  = tkfont.Font(family="Arial", size=13, weight="bold")
        self.fonte_normal  = tkfont.Font(family="Arial", size=11)
        self.fonte_pequena = tkfont.Font(family="Arial", size=9)
        self.fonte_numero  = tkfont.Font(family="Courier", size=28, weight="bold")
        self.fonte_rf04    = tkfont.Font(family="Arial", size=10)

        # Frame container único (troca de telas por pack/pack_forget)
        self.frame_atual: tk.Frame | None = None

        self.mostrar_tela_login()

    # ── utilidades de tela ──────────────────────────────────

    def _limpar_tela(self):
        if self.frame_atual:
            self.frame_atual.destroy()

    def _cabecalho(self, parent: tk.Frame, titulo: str):
        tk.Label(
            parent, text="🗳  URNA ELETRÔNICA", bg=CORES["bg_painel"],
            fg=CORES["azul_claro"], font=self.fonte_pequena
        ).pack(pady=(10, 0))
        tk.Label(
            parent, text=titulo, bg=CORES["bg_painel"],
            fg=CORES["branco"], font=self.fonte_titulo
        ).pack()
        tk.Frame(parent, bg=CORES["azul_urna"], height=2).pack(fill="x", padx=20, pady=5)

    def _botao(self, parent, texto, comando, cor_bg, cor_fg="#ffffff", largura=18):
        return tk.Button(
            parent, text=texto, command=comando,
            bg=cor_bg, fg=cor_fg, activebackground=cor_bg,
            font=self.fonte_subtit, relief="flat", cursor="hand2",
            padx=12, pady=8, width=largura
        )

    # ══════════════════════════════════════════════════════════
    # RF01 — TELA DE LOGIN (CPF + Nome)
    # ══════════════════════════════════════════════════════════

    def mostrar_tela_login(self):
        self._limpar_tela()
        frame = tk.Frame(self, bg=CORES["bg_painel"], padx=30, pady=20)
        frame.pack(expand=True, fill="both", padx=30, pady=30)
        self.frame_atual = frame

        self._cabecalho(frame, "IDENTIFICAÇÃO DO ELEITOR")

        instrucao = "Insira seus dados para acessar o sistema de votação."
        tk.Label(frame, text=instrucao, bg=CORES["bg_painel"],
                 fg=CORES["cinza"], font=self.fonte_normal).pack(pady=(10, 20))

        # ── Campos ──────────────────────────────────────────
        def campo(label_txt, placeholder=""):
            row = tk.Frame(frame, bg=CORES["bg_painel"])
            row.pack(fill="x", pady=6)
            tk.Label(row, text=label_txt, bg=CORES["bg_painel"],
                     fg=CORES["branco"], font=self.fonte_normal, width=12, anchor="w").pack(side="left")
            entry = tk.Entry(row, bg=CORES["bg_campo"], fg=CORES["branco"],
                             insertbackground="white", font=self.fonte_numero,
                             width=18, relief="flat", bd=4)
            entry.pack(side="left", padx=6)
            return entry

        self.entry_cpf  = campo("CPF:")
        self.entry_nome = campo("Nome:")
        self.entry_data_nasc = campo("Nascimento:")

        tk.Label(frame, text="Formato CPF: 000.000.000-00  |  Nascimento: DD/MM/AAAA",
                 bg=CORES["bg_painel"], fg=CORES["cinza"],
                 font=self.fonte_pequena).pack(pady=(4, 16))

        # ── Botão confirmar ──────────────────────────────────
        self._botao(frame, "✔  CONFIRMAR", self._validar_login,
                    CORES["verde"], "#000000").pack(pady=4)

        # ── Status ──────────────────────────────────────────
        self.label_status_login = tk.Label(frame, text="", bg=CORES["bg_painel"],
                                            fg=CORES["vermelho"], font=self.fonte_normal)
        self.label_status_login.pack(pady=8)

        # ── Rodapé ──────────────────────────────────────────
        tk.Label(frame, text="⚡  Tribunal Regional Eleitoral  |  Eleição Municipal",
                 bg=CORES["bg_painel"], fg=CORES["cinza"],
                 font=self.fonte_pequena).pack(side="bottom", pady=10)

    # ══════════════════════════════════════════════════════════
    # RF02 — VALIDAÇÃO DO CPF (duplicidade + formato)
    # ══════════════════════════════════════════════════════════

    def _validar_login(self):
        cpf_raw  = self.entry_cpf.get().strip()
        nome     = self.entry_nome.get().strip()
        data_nasc= self.entry_data_nasc.get().strip()
        cpf_limpo = re.sub(r"\D", "", cpf_raw)

        # Validações
        if not nome:
            self.label_status_login.config(text="⚠ Por favor, insira seu nome.")
            return
        if not validar_cpf(cpf_limpo):
            self.label_status_login.config(text="⚠ CPF inválido. Verifique e tente novamente.")
            return
        if not re.match(r"\d{2}/\d{2}/\d{4}", data_nasc):
            self.label_status_login.config(text="⚠ Data de nascimento inválida. Use DD/MM/AAAA.")
            return

        # RF02: verifica duplicidade
        if cpf_limpo in self.eleitores_votados:
            self.label_status_login.config(
                text="🚫 Este CPF já votou nesta eleição."
            )
            return

        # Sessão salva
        self.eleitor_atual = {
            "cpf": cpf_limpo,
            "nome": nome,
            "data_nasc": data_nasc,
        }
        self.mostrar_tela_votacao()

    # ══════════════════════════════════════════════════════════
    # RF03 | RF04 | RF05 — TELA DE VOTAÇÃO com busca
    # ══════════════════════════════════════════════════════════

    def mostrar_tela_votacao(self):
        self._limpar_tela()
        frame = tk.Frame(self, bg=CORES["bg_painel"], padx=20, pady=10)
        frame.pack(expand=True, fill="both", padx=20, pady=20)
        self.frame_atual = frame

        self._cabecalho(frame, "VOTAÇÃO — PREFEITO")

        # Saudação
        nome_curto = self.eleitor_atual["nome"].split()[0]
        tk.Label(frame, text=f"Olá, {nome_curto}! Digite o número do candidato.",
                 bg=CORES["bg_painel"], fg=CORES["cinza"],
                 font=self.fonte_normal).pack(pady=(4, 8))

        # ── RF04/RF05: Área de busca (colinha) ──────────────
        frame_busca = tk.LabelFrame(
            frame, text=" 🔍 Consultar Candidatos (colinha) ",
            bg=CORES["bg_painel"], fg=CORES["amarelo"],
            font=self.fonte_rf04, padx=8, pady=6
        )
        frame_busca.pack(fill="x", pady=(0, 10))

        row_busca = tk.Frame(frame_busca, bg=CORES["bg_painel"])
        row_busca.pack(fill="x")

        self.entry_busca = tk.Entry(
            row_busca, bg=CORES["bg_campo"], fg=CORES["branco"],
            insertbackground="white", font=self.fonte_normal,
            width=22, relief="flat", bd=3
        )
        self.entry_busca.pack(side="left", padx=(0, 6))
        self.entry_busca.bind("<KeyRelease>", self._buscar_candidatos)

        tk.Label(row_busca, text="Busque por número, nome ou partido",
                 bg=CORES["bg_painel"], fg=CORES["cinza"],
                 font=self.fonte_pequena).pack(side="left")

        # Listbox de resultados da busca
        self.listbox_busca = tk.Listbox(
            frame_busca, bg=CORES["bg_campo"], fg=CORES["branco"],
            selectbackground=CORES["azul_urna"], font=self.fonte_normal,
            height=4, relief="flat", activestyle="none"
        )
        self.listbox_busca.pack(fill="x", pady=(4, 0))
        self.listbox_busca.bind("<<ListboxSelect>>", self._selecionar_da_lista)
        self._popular_listbox(CANDIDATOS)

        # ── RF03: Campo de número do candidato ──────────────
        frame_num = tk.Frame(frame, bg=CORES["bg_painel"])
        frame_num.pack(pady=8)

        tk.Label(frame_num, text="Número do Candidato:",
                 bg=CORES["bg_painel"], fg=CORES["branco"],
                 font=self.fonte_subtit).pack(side="left", padx=(0, 10))

        self.entry_numero = tk.Entry(
            frame_num, bg=CORES["bg_campo"], fg=CORES["amarelo"],
            insertbackground="yellow", font=self.fonte_numero,
            width=6, relief="flat", bd=4, justify="center"
        )
        self.entry_numero.pack(side="left")
        self.entry_numero.bind("<KeyRelease>", self._verificar_numero_live)

        self._botao(frame_num, "🔎 VER", self._confirmar_numero,
                    CORES["azul_urna"], largura=8).pack(side="left", padx=10)

        # ── Preview do candidato ─────────────────────────────
        self.frame_preview = tk.Frame(frame, bg=CORES["bg_painel"])
        self.frame_preview.pack(fill="x", pady=4)

        self.label_preview = tk.Label(
            self.frame_preview, text="", bg=CORES["bg_painel"],
            fg=CORES["cinza"], font=self.fonte_normal
        )
        self.label_preview.pack()

        # ── Botões confirmar / cancelar (RF06, RF07) ─────────
        frame_btns = tk.Frame(frame, bg=CORES["bg_painel"])
        frame_btns.pack(pady=10)

        self._botao(frame_btns, "✔  CONFIRMAR VOTO", self._confirmar_voto,
                    CORES["verde"], "#000000").pack(side="left", padx=10)
        self._botao(frame_btns, "✖  CANCELAR / VOLTAR", self._cancelar_voto,
                    CORES["vermelho"]).pack(side="left", padx=10)

        self.label_status_voto = tk.Label(
            frame, text="", bg=CORES["bg_painel"],
            fg=CORES["vermelho"], font=self.fonte_normal
        )
        self.label_status_voto.pack()

    # ── RF05: Busca parcial ──────────────────────────────────

    def _buscar_candidatos(self, event=None):
        termo = self.entry_busca.get().strip().lower()
        if not termo:
            self._popular_listbox(CANDIDATOS)
            return
        resultado = [
            c for c in CANDIDATOS
            if termo in c["numero"]
            or termo in c["nome"].lower()
            or termo in c["partido"].lower()
        ]
        self._popular_listbox(resultado)

    def _popular_listbox(self, candidatos: list):
        self.listbox_busca.delete(0, tk.END)
        for c in candidatos:
            self.listbox_busca.insert(
                tk.END,
                f"  {c['numero']}  —  {c['nome']}  |  {c['partido']}"
            )
        self._candidatos_visiveis = candidatos

    def _selecionar_da_lista(self, event=None):
        sel = self.listbox_busca.curselection()
        if not sel:
            return
        idx = sel[0]
        candidato = self._candidatos_visiveis[idx]
        self.entry_numero.delete(0, tk.END)
        self.entry_numero.insert(0, candidato["numero"])
        self._mostrar_preview(candidato)

    # ── RF06: Preview / confirmação do candidato ─────────────

    def _verificar_numero_live(self, event=None):
        numero = self.entry_numero.get().strip()
        candidato = self._buscar_por_numero(numero)
        if candidato:
            self._mostrar_preview(candidato)
        else:
            self.label_preview.config(
                text="Candidato não encontrado." if numero else "",
                fg=CORES["vermelho"]
            )
            self.candidato_selecionado = None

    def _confirmar_numero(self):
        numero = self.entry_numero.get().strip()
        candidato = self._buscar_por_numero(numero)
        if not candidato:
            self.label_status_voto.config(text="⚠ Número de candidato inválido.")
        else:
            self._mostrar_preview(candidato)

    def _buscar_por_numero(self, numero: str) -> dict | None:
        return next((c for c in CANDIDATOS if c["numero"] == numero), None)

    def _mostrar_preview(self, candidato: dict):
        self.candidato_selecionado = candidato
        texto = (
            f"{candidato['foto_char']}  Nº {candidato['numero']}  —  {candidato['nome']}\n"
            f"Partido: {candidato['partido']}  |  Vice: {candidato['vice']}"
        )
        self.label_preview.config(text=texto, fg=CORES["verde"])
        self.label_status_voto.config(text="")

    # ══════════════════════════════════════════════════════════
    # RF06 — CONFIRMAR VOTO
    # ══════════════════════════════════════════════════════════

    def _confirmar_voto(self):
        if not self.candidato_selecionado:
            self.label_status_voto.config(text="⚠ Nenhum candidato selecionado.")
            return

        c = self.candidato_selecionado
        resposta = messagebox.askyesno(
            "Confirmar Voto",
            f"Você deseja votar em:\n\n"
            f"Nº {c['numero']} — {c['nome']}\n"
            f"Partido: {c['partido']}\n\n"
            f"Esta ação é irreversível. Confirmar?",
        )
        if not resposta:
            return

        # Registra voto de forma 100% SIGILOSA:
        # Nenhum dado pessoal do eleitor (CPF, nome) é associado ao voto.
        # Além disso, a lista de votos é embaralhada aleatoriamente (como no RDV da urna real)
        # para impossibilitar correlação temporal ou sequencial com a lista de presença.
        registro = {
            "numero_cand":  c["numero"],
            "nome_cand":    c["nome"],
            "partido_cand": c["partido"],
        }
        self.votos.append(registro)
        random.shuffle(self.votos)
        self.eleitores_votados.append(self.eleitor_atual["cpf"])

        salvar_json(VOTOS_DB_FILE, self.votos)
        salvar_json(ELEITORES_DB_FILE, self.eleitores_votados)

        # Envia voto em tempo real para o servidor na nuvem (Vercel) ou local
        self._sincronizar_voto_nuvem(registro, self.eleitor_atual["cpf"])

        self.mostrar_tela_confirmacao(c)

    def _sincronizar_voto_nuvem(self, registro: dict, cpf: str):
        """Envia o voto computado de forma assincrona para a Vercel / API."""
        if not API_URL:
            return

        def _requisicao():
            try:
                import urllib.request
                import urllib.error
                url = f"{API_URL.rstrip('/')}/api/votar"
                payload = json.dumps({
                    "voto": registro,
                    "cpf_eleitor": cpf
                }).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "UrnaEletronica/1.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    print(f"  🌐 [Nuvem] Voto para candidato nº {registro['numero_cand']} sincronizado com sucesso na Vercel!")
            except Exception as e:
                print(f"  ⚠ [Nuvem] Aviso: Nao foi possivel sincronizar voto com a nuvem ({e}). O voto foi registrado localmente.")

        import threading
        threading.Thread(target=_requisicao, daemon=True).start()

    # ══════════════════════════════════════════════════════════
    # RF07 — CANCELAR / VOLTAR
    # ══════════════════════════════════════════════════════════

    def _cancelar_voto(self):
        self.candidato_selecionado = None
        self.entry_numero.delete(0, tk.END)
        self.label_preview.config(text="")
        self.label_status_voto.config(text="✖ Seleção cancelada. Insira um novo número.")
        self.entry_busca.delete(0, tk.END)
        self._popular_listbox(CANDIDATOS)

    # ══════════════════════════════════════════════════════════
    # TELA DE CONFIRMAÇÃO FINAL
    # ══════════════════════════════════════════════════════════

    def mostrar_tela_confirmacao(self, candidato: dict):
        self._limpar_tela()
        frame = tk.Frame(self, bg=CORES["bg_painel"], padx=40, pady=20)
        frame.pack(expand=True, fill="both", padx=30, pady=30)
        self.frame_atual = frame

        self._cabecalho(frame, "VOTO REGISTRADO COM SUCESSO")

        tk.Label(frame, text=candidato["foto_char"], bg=CORES["bg_painel"],
                 font=tkfont.Font(size=64)).pack(pady=10)

        tk.Label(frame,
                 text=f"Nº {candidato['numero']}  —  {candidato['nome']}",
                 bg=CORES["bg_painel"], fg=CORES["verde"],
                 font=self.fonte_titulo).pack()

        tk.Label(frame, text=f"Partido: {candidato['partido']}  |  Vice: {candidato['vice']}",
                 bg=CORES["bg_painel"], fg=CORES["cinza"],
                 font=self.fonte_normal).pack(pady=4)

        tk.Frame(frame, bg=CORES["verde"], height=2).pack(fill="x", padx=20, pady=12)

        tk.Label(frame,
                 text="✅  Obrigado por exercer sua cidadania!\n"
                      "Seu voto foi computado com segurança.",
                 bg=CORES["bg_painel"], fg=CORES["branco"],
                 font=self.fonte_subtit, justify="center").pack(pady=8)

        # Botão para novo eleitor
        self._botao(frame, "🔄  NOVO ELEITOR", self._reiniciar_sessao,
                    CORES["azul_urna"]).pack(pady=12)

    # ══════════════════════════════════════════════════════════
    # REINICIAR SESSÃO (próximo eleitor)
    # ══════════════════════════════════════════════════════════

    def _reiniciar_sessao(self):
        self.eleitor_atual = None
        self.candidato_selecionado = None
        self.mostrar_tela_login()


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  🗳  URNA ELETRÔNICA SIMULADA (TRE)")
    print(f"  🌐  Painel Conectado: {API_URL}")
    print("  🔒  Sigilo RDV ativo (Votos desvinculados do CPF)")
    print("=" * 60)
    app = UrnaEletronica()
    app.mainloop()

