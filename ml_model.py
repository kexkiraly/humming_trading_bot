# ============================================================
# ml_model.py – Gépi tanulás modul
# ============================================================

import sqlite3
import logging
import os
import numpy as np
import joblib
import json

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

logger = logging.getLogger(__name__)

DB_FILE    = "trades.db"
MODEL_FILE = "model.pkl"     # ide menti a betanított modellt
SCALER_FILE = "scaler.pkl"   # ide menti a normalizálót
IMPORTANCE_FILE = "feature_importance.json"

# Feature nevek – pontosan ebben a sorrendben kerülnek a modellbe
FEATURE_NAMES = [
    "RSI",
    "MACD",
    "Fear_Greed",
    "Szavazatok",
    "OB_Ratio",    # orderbook bid/ask arány
    "OFI",         # order flow imbalance
]

# Ennyi lezárt pozíció kell a valódi tanításhoz
MIN_REAL_TRADES = 50


def get_training_data_from_db():
    """
    Lekéri a lezárt pozíciókat az adatbázisból tanításhoz.
    Visszaad egy (X, y) párt ahol:
      X = indikátor értékek (jellemzők)
      y = 1 ha nyereséges volt, 0 ha nem
    """
    try:
        conn   = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT rsi, macd, fg_value, votes, profit_pct
            FROM trades
            WHERE side = 'sell'
              AND profit_pct IS NOT NULL
              AND rsi IS NOT NULL
              AND macd IS NOT NULL
              AND CAST(rsi AS TEXT) != 'STOP-LOSS'
              AND typeof(rsi) = 'real'
              AND typeof(macd) = 'real'
              AND typeof(profit_pct) = 'real'
        """)
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Adatbázis olvasási hiba: {e}")
        return []


def generate_simulated_data(n=300):
    """
    Szimulált tanítóadatot generál, amíg nincs elég valódi adat.
    A minták a valós piaci viselkedést közelítik.
    """
    np.random.seed(42)
    X, y = [], []

    for _ in range(n):
        rsi      = np.random.uniform(20, 80)
        macd     = np.random.uniform(-50, 50)
        fg_value = np.random.randint(10, 90)
        votes    = np.random.randint(0, 7)

        # Egyszerű logika: ha több a vételi jel → nagyobb esély a nyereségre
        profit_chance = 0.5
        if rsi < 35:          profit_chance += 0.15
        if rsi > 65:          profit_chance -= 0.15
        if macd > 10:         profit_chance += 0.10
        if macd < -10:        profit_chance -= 0.10
        if fg_value < 30:     profit_chance += 0.10
        if fg_value > 70:     profit_chance -= 0.10
        if votes >= 4:        profit_chance += 0.15
        if votes <= 2:        profit_chance -= 0.15

        profit_chance = max(0.1, min(0.9, profit_chance))
        label = 1 if np.random.random() < profit_chance else 0

        ob_ratio = np.random.uniform(0.5, 2.0)
        ofi      = np.random.uniform(-1.0, 1.0)
        X.append([rsi, macd, fg_value, votes, ob_ratio, ofi])
        y.append(label)

    return X, y


def train_model():
    """
    Betanítja a modellt.
    Ha van elég valódi adat → azt használja.
    Ha nincs → szimulált adatokkal indul.
    Elmenti a modellt fájlba.
    """
    real_rows = get_training_data_from_db()

    if len(real_rows) >= MIN_REAL_TRADES:
        logger.info(f"🎓 Valódi adatokból tanítás ({len(real_rows)} sor)...")
        # Valódi adatok feldolgozása (6 bemeneti paraméter + 1 célváltozó)
        X = [[r[0], r[1], r[2] or 50, r[3] or 3, 1.0, 0.0] for r in real_rows]
        y = [1 if r[4] > 0 else 0 for r in real_rows]
    else:
        logger.info(
            f"⚙️  Csak {len(real_rows)} valódi adat van (kell: {MIN_REAL_TRADES}). "
            f"Szimulált adatokkal tanítás..."
        )
        X, y = generate_simulated_data(300)

        # JAVÍTÁS: Itt is 6 elemnek kell lennie a listában!
        if real_rows:
            for r in real_rows:
                # r[0]:rsi, r[1]:macd, r[2]:fg, r[3]:votes + alapértelmezett 1.0 és 0.0 az új feature-öknek
                X.append([r[0], r[1], r[2] or 50, r[3] or 3, 1.0, 0.0])
                y.append(1 if r[4] > 0 else 0)

    # Biztonsági szűrés – minden nem-szám értéket kiszűr
    clean_X = []
    clean_y = []
    for features, label in zip(X, y):
        try:
            clean_features = [float(f) for f in features]
            clean_X.append(clean_features)
            clean_y.append(float(label))
        except (ValueError, TypeError):
            continue

    X = clean_X
    y = clean_y

    if not X:
        logger.error("Nincs tiszta tanítóadat!")
        return None, None, 0.0
    X = np.array(X)
    y = np.array(y)

    # Normalizálás
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Tanítás/teszt felosztás
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42
    )

    # Random Forest modell
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=5,
        random_state=42
    )
    model.fit(X_train, y_train)

    # Pontosság mérése
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    logger.info(f"✅ Modell betanítva! Pontosság: {accuracy:.1%}")

    # Mentés
    joblib.dump(model, MODEL_FILE)
    joblib.dump(scaler, SCALER_FILE)
    
    # Feature fontosság mentése
    importance = dict(zip(FEATURE_NAMES, model.feature_importances_.tolist()))
    importance_sorted = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
    
    with open(IMPORTANCE_FILE, "w") as f:
        json.dump(importance_sorted, f, indent=2)

    logger.info("📊 Feature fontossági sorrend:")
    for i, (name, imp) in enumerate(importance_sorted.items(), 1):
        bar = "█" * int(imp * 50)
        logger.info(f"  {i}. {name:<15} {imp:>6.1%} {bar}")

    return model, scaler, accuracy


def load_or_train_model():
    """
    Betölti a mentett modellt, vagy ha nincs → betanítja.
    """
    if os.path.exists(MODEL_FILE) and os.path.exists(SCALER_FILE):
        try:
            model  = joblib.load(MODEL_FILE)
            scaler = joblib.load(SCALER_FILE)
            logger.info("📂 Mentett modell betöltve.")
            return model, scaler
        except Exception as e:
            logger.warning(f"Modell betöltési hiba, újratanítás: {e}")

    return train_model()[:2]


def predict(model, scaler, rsi, macd, fg_value, votes,
            ob_ratio=1.0, ofi=0.0):
    """
    Megjósolja, hogy a jelenlegi indikátorok alapján
    nyereséges lesz-e a kereskedés.

    Visszaad:
      - should_trade (bool): érdemes-e kereskedni
      - confidence (float): magabiztosság 0-100% között
    """
    try:
        features = np.array([[rsi, macd, fg_value, votes,
                               ob_ratio, ofi]])
        features_scaled = scaler.transform(features)

        # Valószínűség lekérése (0 = veszteséges, 1 = nyereséges)
        proba = model.predict_proba(features_scaled)[0]
        confidence = proba[1] * 100  # nyereséges valószínűség %-ban

        # Csak akkor kereskedjünk, ha 60%+ a bizalom
        should_trade = confidence >= 60.0

        logger.info(
            f"🤖 ML előrejelzés: {'✅ Kereskedj!' if should_trade else '⏸️  Várj!'} "
            f"(Bizalom: {confidence:.1f}%)"
        )
        return should_trade, confidence

    except Exception as e:
        logger.error(f"ML előrejelzési hiba: {e}")
        return True, 50.0  # hiba esetén nem blokkoljuk a kereskedést


def retrain_periodically(trade_count, retrain_every=20):
    """
    Minden N-edik kereskedés után újratanítja a modellt
    a friss adatokkal.
    """
    if trade_count > 0 and trade_count % retrain_every == 0:
        logger.info(f"🔄 Újratanítás ({trade_count}. kereskedés után)...")
        return train_model()[:2]
    return None, None