from __future__ import annotations
import json
from jarvis.agency import AgencyCapability
from jarvis.memory import CompanyMemory

TASKS = (
    "Vireon için yeni Meta kampanyası hazırla. Mevcut satış ve reklam verisini kullan. 3 farklı kreatif açı üret.",
    "Mevcut reklam performansında hangi problemler ve fırsatlar var? Ne test edilmeli?",
    "L'CARLIE için 7 günlük Instagram planı hazırla.",
)

if __name__ == "__main__":
    agency = AgencyCapability(CompanyMemory(host=None))
    print(json.dumps([agency.run(task) for task in TASKS], ensure_ascii=False, indent=2))
