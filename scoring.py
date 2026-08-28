"""Pontuação auxiliar de FIIs sem transformar dados ausentes em zero."""


def calcular_score(dados: dict) -> float:
    score = 50
    dy = dados.get("dy")
    if dy is not None:
        score += 15 if dy >= 12 else 10 if dy >= 10 else 5 if dy >= 8 else -10 if dy < 6 else 0

    pvp = dados.get("p_vp")
    if pvp is not None:
        score += 12 if 0.8 <= pvp <= 1.0 else 8 if 0.7 <= pvp < 0.8 else -5 if pvp > 1.2 else 0

    vacancia = dados.get("vacancia")
    if vacancia is not None:
        score += 10 if vacancia < 5 else 5 if vacancia < 10 else -10 if vacancia > 20 else 0

    patrimonio = dados.get("patrimonio")
    if patrimonio is not None:
        score += 8 if patrimonio > 1_000_000_000 else 5 if patrimonio > 500_000_000 else 0

    setor = dados.get("setor") or ""
    score += 5 if setor in {"Logístico", "Tijolo", "Logística/Galpão", "Shopping"} else 3 if setor == "Papel" else 0
    return min(max(score, 0), 100)
