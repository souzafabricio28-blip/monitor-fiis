from pathlib import Path

from subir_producao import (
    arquivos_para_github,
    arquivos_rastreados,
    copiar_arvore,
    remover_arquivos_obsoletos,
)


def test_arquivos_rastreados_nunca_incluem_env():
    caminhos = arquivos_rastreados(Path("."))
    assert ".env" not in caminhos
    assert not any(Path(c).name == ".env" for c in caminhos)


def test_github_nao_envia_workflows_nem_env():
    caminhos = arquivos_para_github(Path("."))
    assert ".env" not in caminhos
    assert not any(c.startswith(".github/workflows/") for c in caminhos)


def test_copiar_arvore_recusa_env(tmp_path):
    origem = tmp_path / "origem"
    destino = tmp_path / "destino"
    origem.mkdir()
    (origem / ".env").write_text("GH_TOKEN=secreto\n", encoding="utf-8")
    (origem / "app.py").write_text("print('ok')\n", encoding="utf-8")
    copiar_arvore(origem, destino, [".env", "app.py"])
    assert (destino / "app.py").is_file()
    assert not (destino / ".env").exists()


def test_remover_arquivos_obsoletos_apaga_telegram(tmp_path):
    destino = tmp_path / "destino"
    destino.mkdir()
    (destino / "app.py").write_text("ok\n", encoding="utf-8")
    (destino / "telegram_notifier.py").write_text("legado\n", encoding="utf-8")
    wf = destino / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    remover_arquivos_obsoletos(destino, ["app.py", "whatsapp_notifier.py"])
    assert (destino / "app.py").is_file()
    assert not (destino / "telegram_notifier.py").exists()
    assert (wf / "ci.yml").is_file()
