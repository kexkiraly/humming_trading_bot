import logging
import time
import threading
from exchange import Exchange
from strategy import SimpleStrategy
from config import LOOP_DELAY
from database import init_db, print_stats
from simulator import TradingSimulator
from dashboard import run_dashboard
from guard import is_kill_switch_active, deactivate_kill_switch

# Telegram notifier
from notifier import send_message, handle_telegram_commands

# Naplózás beállítása
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("🤖 Trading bot indítása...")
    
    # 1. Alapok inicializálása
    init_db()
    
    # Esetleges régi kill switch törlése induláskor
    if is_kill_switch_active():
        deactivate_kill_switch()
        logger.info("🔄 Régi kill switch törölve.")

    # 2. Exchange és Szimulátor létrehozása (SORREND FONTOS!)
    try:
        # Előbb az exchange objektum
        exchange = Exchange()
        
        # Aztán a szimulátor
        simulator = TradingSimulator()
        
        # Végül az összekötés
        exchange.simulator = simulator
        
        # Most már jöhet a stratégia, ami megkapja a felkészített exchange-et
        strategy = SimpleStrategy(exchange)
        
    except Exception as e:
        logger.critical(f"Inicializálási hiba: {e}")
        send_message(f"⚠️ <b>Bot hiba:</b> Nem sikerült az indulás: {e}")
        return

    # 3. Kiegészítő szolgáltatások indítása
    t = threading.Thread(target=run_dashboard, daemon=True)
    t.start()
    logger.info("🌐 Dashboard elérhető: http://localhost:5000")
    
    send_message("🤖 <b>A trading botod elindult és figyel!</b>")
    logger.info(f"🕒 Főciklus elindult (körök között: {LOOP_DELAY}s)")

    # 4. Főciklus
    while True:
        try:
            # A stratégia lefuttatása
            strategy.run()
            
            # Snapshot mentése minden ~5 percben
            if exchange.simulator and int(time.time()) % 300 < 5:
                prices = {s: exchange.get_ticker(s).get("last", 0) for s in ["BTC/USDT"]}
                exchange.simulator.save_snapshot(prices)
            
            # Telegram parancsok kezelése
            cmd = handle_telegram_commands()
            if cmd == "stop":
                logger.warning("⛔ Telegram stop parancs érkezett.")
                break
            elif cmd == "status":
                stats = strategy.guard.get_status()
                send_message(
                    f"📊 <b>Bot státusz</b>\n"
                    f"Kill switch: {'🔴 AKTÍV' if stats['kill_switch'] else '✅ Inaktív'}\n"
                    f"Circuit breaker: {'⚡ AKTÍV' if stats['circuit_breaker'] else '✅ Inaktív'}\n"
                    f"Napi megbízások: {stats['daily_trades']}/{stats['max_trades']}\n"
                    f"Napi veszteség: {stats['daily_loss']:.2f}%/{stats['max_daily_loss']}%"
                )

            time.sleep(LOOP_DELAY)

        except KeyboardInterrupt:
            logger.info("⛔ Manuális leállítás (Ctrl+C).")
            send_message("⛔ <b>Trading bot leállt.</b>")
            if exchange.simulator:
                prices = {s: exchange.get_ticker(s).get("last", 0) for s in ["BTC/USDT"]}
                exchange.simulator.print_stats(prices)
                strategy.portfolio.print_status()
            print_stats()
            break
        except Exception as e:
            logger.error(f"Hiba a ciklusban: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()