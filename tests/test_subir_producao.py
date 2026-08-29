from pathlib import Path

from subir_producao import arquivos_para_github, arquivos_rastreados, copiar_arvore


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
