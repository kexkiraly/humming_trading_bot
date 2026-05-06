# ============================================================
# show_importance.py – Feature fontosság megjelenítése
# ============================================================

import json
import os

IMPORTANCE_FILE = "feature_importance.json"

def show():
    if not os.path.exists(IMPORTANCE_FILE):
        print("❌ Még nincs feature importance adat.")
        print("   Futtasd először: python main.py")
        print("   A modell 20 trade után automatikusan újratanít.")
        return

    with open(IMPORTANCE_FILE, "r") as f:
        importance = json.load(f)

    print("\n" + "="*55)
    print("  📊 FEATURE FONTOSSÁGI SORREND")
    print("="*55)

    for i, (name, imp) in enumerate(importance.items(), 1):
        bar    = "█" * int(imp * 40)
        empty  = "░" * (40 - len(bar))
        print(f"  {i}. {name:<15} {imp:>6.1%}  {bar}{empty}")

    print("="*55)

    # Tanács
    print("\n💡 Tanácsok:")
    items = list(importance.items())
    if items:
        best  = items[0]
        worst = items[-1]
        print(f"  ✅ Leghasznosabb: {best[0]} ({best[1]:.1%})")
        print(f"  ⚠️  Legkevésbé hasznos: {worst[0]} ({worst[1]:.1%})")
        if worst[1] < 0.05:
            print(
                f"  💭 A '{worst[0]}' indikátor keveset ad hozzá – "
                f"esetleg elhagyható."
            )
    print()

if __name__ == "__main__":
    show()