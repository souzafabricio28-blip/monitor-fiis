"""PDF resumido da lista do gestor — só para envio, sem tela no app."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from criterios import (
    _criterio_idade_fii,
    _ano_listagem,
    avaliar_diversificacao_setores,
    classificar_setor,
)
from lista_gestor import ACOES_GESTOR, FUNDOS_GESTOR
from portfolio import resumo_criterios


def _txt(texto) -> str:
    if texto is None:
        return "N/D"
    convertido = (
        str(texto)
        .replace("—", "-")
        .replace("–", "-")
        .replace("≥", ">=")
        .replace("≤", "<=")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .replace("…", "...")
    )
    return convertido.encode("latin-1", "replace").decode("latin-1")


def _fmt_num(valor, casas=2):
    if valor is None:
        return "N/D"
    try:
        return f"{float(valor):.{casas}f}"
    except (TypeError, ValueError):
        return "N/D"


def _status_pt(status: str) -> str:
    return {"aprovado": "APROVADO", "reprovado": "REPROVADO", "nd": "N/D"}.get(
        status, status.upper()
    )


def montar_resumo_lista(avaliacoes: dict | None = None) -> dict:
    """Monta o texto do PDF. Sem avaliacoes, usa so catalogo + idade/incorporacao."""
    ano_atual = datetime.now().year
    fundos = []
    setores = []
    for ticker in FUNDOS_GESTOR:
        ano = _ano_listagem(ticker, "fii", permitir_scrape=False)
        idade = _criterio_idade_fii(ticker, ano)
        setor = classificar_setor("", ticker=ticker)
        setores.append(setor)
        av = (avaliacoes or {}).get(ticker)
        linha = {
            "ticker": ticker,
            "setor": setor,
            "idade": idade["valor"],
            "idade_ok": idade["ok"],
            "idade_obs": idade["obs"],
            "ano": ano,
            "anos_ticker": (ano_atual - ano) if ano else None,
        }
        if av:
            resumo = resumo_criterios(av)
            dados = av.get("dados") or {}
            linha.update(
                {
                    "nome": dados.get("nome") or ticker,
                    "status": resumo["status"],
                    "ok": resumo["ok"],
                    "fail": resumo["fail"],
                    "nd": resumo["nd"],
                    "p_vp": dados.get("p_vp"),
                    "p_vp_fonte": dados.get("p_vp_fonte"),
                    "dy_mensal": dados.get("dy_mensal"),
                    "criterios": av.get("criterios") or [],
                }
            )
        else:
            linha.update(
                {
                    "nome": ticker,
                    "status": "nd",
                    "ok": 0,
                    "fail": 0,
                    "nd": 0,
                    "p_vp": None,
                    "criterios": [idade],
                }
            )
        fundos.append(linha)

    acoes = []
    for ticker in ACOES_GESTOR:
        ano = _ano_listagem(ticker, "acao", permitir_scrape=False)
        idade = (ano_atual - ano) if ano else None
        av = (avaliacoes or {}).get(ticker)
        linha = {
            "ticker": ticker,
            "ano": ano,
            "idade": f"{idade} anos (desde {ano})" if ano else "N/D",
            "idade_ok": idade >= 10 if idade is not None else None,
        }
        if av:
            resumo = resumo_criterios(av)
            dados = av.get("dados") or {}
            linha.update(
                {
                    "nome": dados.get("nome") or ticker,
                    "status": resumo["status"],
                    "ok": resumo["ok"],
                    "fail": resumo["fail"],
                    "nd": resumo["nd"],
                    "p_vp": dados.get("p_vp"),
                    "p_vp_fonte": dados.get("p_vp_fonte"),
                    "criterios": av.get("criterios") or [],
                }
            )
        else:
            linha.update(
                {
                    "nome": ticker,
                    "status": "nd",
                    "p_vp": None,
                    "p_vp_fonte": None,
                    "criterios": [],
                }
            )
        acoes.append(linha)

    return {
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fundos": fundos,
        "acoes": acoes,
        "diversificacao": avaliar_diversificacao_setores(setores),
        "tem_avaliacao": bool(avaliacoes),
    }


class ListaGestorPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 16)
        self.set_text_color(102, 126, 234)
        self.cell(0, 10, "Lista do Ricardo - analise resumida", ln=True, align="C")
        self.set_font("Arial", "", 10)
        self.set_text_color(100, 100, 100)
        self.cell(
            0,
            7,
            _txt(f"RT Tintas · WhatsApp 28/08/2026 · Monitor de FIIs · {datetime.now().strftime('%d/%m/%Y %H:%M')}"),
            ln=True,
            align="C",
        )
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "", 8)
        self.set_text_color(140, 140, 140)
        self.cell(
            0,
            8,
            "Dado ausente = N/D, nunca 0. Nao e recomendacao de investimento.",
            align="C",
        )


def _bloco(pdf: FPDF, texto: str, h: float = 5) -> None:
    """multi_cell a partir da margem esquerda (fpdf2 deixa o cursor a direita)."""
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, h, _txt(texto))
    pdf.set_x(pdf.l_margin)


def gerar_pdf_lista_gestor_bytes(resumo: dict | None = None) -> bytes:
    dados = resumo or montar_resumo_lista()
    pdf = ListaGestorPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_font("Arial", "B", 13)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, "O que foi corrigido neste recado", ln=True)
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(50, 50, 50)
    _bloco(
        pdf,
        "1) P/VP de SAPR4 e KLBN4. O Yahoo distorce o P/B de acoes PN. "
        "Passamos a preferir o P/VP do Fundamentus (VPA da B3): SAPR4 0,81 "
        "(nao 0,16) e KLBN4 2,47 (nao 0,49).\n"
        "2) FIIs com 8 anos no ticker atual. XPLG11, HSML11 e RZTR11 ja tem "
        "10+ anos pela origem (troca de nome / incorporacao). O sistema nao "
        "reprova mais so pelo IPO do codigo novo.",
    )
    pdf.ln(3)

    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 8, "Conclusao (nao comprar o pacote inteiro)", ln=True)
    pdf.set_font("Arial", "", 10)
    _bloco(
        pdf,
        "Nucleo de FII mais alinhado: HGLG11 e MXRF11. "
        "XPLG11, HSML11 e RZTR11 passam o criterio de 10 anos pela continuidade; "
        "ainda assim olhe DY, P/VP e vacancia (vacancia segue N/D sem scrape). "
        "Acoes mais proximas dos criterios: ITSA3, PETR4, VALE3. "
        "SAPR4 agora passa o P/VP minimo (0,81). "
        "KLBN4 passa o minimo (2,47) mas esta cara contra o patrimonio. "
        "TAEE11 continua mais distante do restante da tese.",
    )
    pdf.ln(3)

    div = dados.get("diversificacao") or {}
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 8, "Fundos", ln=True)
    pdf.set_font("Arial", "", 10)
    _bloco(
        pdf,
        f"Diversificacao: {', '.join(div.get('presentes') or []) or 'nenhum'}. "
        f"Faltando: {', '.join(div.get('faltando') or []) or 'nenhum'}. "
        "Meta: galpao, shopping, empresarial e papel (>=3). "
        "RZTR11 (agro/hibrido) nao conta nessa meta. Falta Empresarial. "
        "Concentracao em galpao (HGLG11, BTLG11, XPLG11).",
    )
    pdf.ln(2)

    for fundo in dados.get("fundos") or []:
        pdf.set_font("Arial", "B", 11)
        titulo = f"{fundo['ticker']}  {fundo.get('setor') or ''}  {_status_pt(fundo.get('status') or 'nd')}"
        pdf.cell(0, 7, _txt(titulo), ln=True)
        pdf.set_font("Arial", "", 9)
        if fundo.get("idade_ok") is True:
            idade_flag = "OK"
        elif fundo.get("idade_ok") is False:
            idade_flag = "REPROVADO"
        else:
            idade_flag = "N/D"
        extra = ""
        if dados.get("tem_avaliacao"):
            extra = (
                f"  P/VP {_fmt_num(fundo.get('p_vp'))}  "
                f"DY mes {_fmt_num(fundo.get('dy_mensal'))}%  "
                f"OK {fundo.get('ok')} / Fail {fundo.get('fail')} / N/D {fundo.get('nd')}"
            )
        _bloco(pdf, f"Idade: {fundo.get('idade')} [{idade_flag}].{extra}")
        if fundo.get("idade_obs") and fundo.get("anos_ticker") is not None and fundo["anos_ticker"] < 10:
            pdf.set_text_color(80, 80, 120)
            _bloco(pdf, fundo["idade_obs"])
            pdf.set_text_color(50, 50, 50)

    pdf.ln(3)
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 8, "Acoes", ln=True)

    for acao in dados.get("acoes") or []:
        pdf.set_font("Arial", "B", 11)
        pdf.cell(
            0,
            7,
            _txt(f"{acao['ticker']}  {_status_pt(acao.get('status') or 'nd')}"),
            ln=True,
        )
        pdf.set_font("Arial", "", 9)
        fonte = acao.get("p_vp_fonte") or ""
        pvp_txt = _fmt_num(acao.get("p_vp"))
        if fonte:
            pvp_txt = f"{pvp_txt} (fonte {fonte})"
        extra = ""
        if dados.get("tem_avaliacao"):
            extra = f"  OK {acao.get('ok')} / Fail {acao.get('fail')} / N/D {acao.get('nd')}"
        _bloco(
            pdf,
            f"Bolsa: {acao.get('idade')}  P/VP {pvp_txt}.{extra}",
        )

    pdf.ln(2)
    pdf.set_font("Arial", "I", 9)
    _bloco(
        pdf,
        "BBAS3 veio duplicado no WhatsApp e entra uma vez. "
        "TAEE11 e acao (unit), nao fundo, mesmo terminando em 11.",
    )

    raw = pdf.output(dest="S")
    if isinstance(raw, str):
        return raw.encode("latin-1")
    return bytes(raw)


def avaliar_lista_completa(permitir_scrape: bool = False) -> dict:
    from criterios import avaliar_ativo

    avaliacoes = {}
    for ticker in list(FUNDOS_GESTOR) + list(ACOES_GESTOR):
        try:
            avaliacoes[ticker] = avaliar_ativo(ticker, permitir_scrape=permitir_scrape)
        except Exception as exc:
            avaliacoes[ticker] = {
                "dados": {"nome": ticker},
                "criterios": [],
                "erro": str(exc),
            }
    return avaliacoes
