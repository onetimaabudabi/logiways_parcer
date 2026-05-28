import pandas as pd
import json
import re
from pathlib import Path
from main import container_size_dict,get_country,currency_dict,port_dict,region_dict,clean,get_city_station, border_dict
import pdfplumber
import pandas as pd
import re
from pathlib import Path
import requests
from get_tables_sites import get_tables_pdf
import datetime

# =============================
# 28. Парсер Shenzhen Wotu International Logistics
# =============================
def parse_khasan_rates(filepath: str):
    company = "KHASAN"
    tables, text_blocks = get_tables_pdf(None, filepath, company)
    data_scvoznoi = []
    text_all = "\n".join(text_blocks)
    # нормализация пробелов и переводов строк
    text = text_all.replace("\r", "\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # ==============================
    # ПАРСИНГ МОРСКОЙ СТАРТУЮЩИХ ИЗ ПОРТА
    # ==============================

    # regex: берём любую текстовую часть до первых чисел (цены)
    line_re = re.compile(r"^(?P<pol>.+?)\s+(?P<dc>\d{3,5})\s*\$?\s+(?P<hc>\d{3,5})\s*\$?$")
    # также вариант где числа и $ могут быть слиты, или присутствует /40HQ, и т.п.
    line_re2 = re.compile(r"^(?P<pol>.+?)\s+(?P<dc>\d{3,5})\s*\$?\s*/?\s*(?P<hc>\d{3,5})\s*\$?$")

    results = []
    pod = "Владивосток" if "ВМПП/SOLLERS" in text else ""
    shenzhen_20 = shenzhen_40 = None

    for ln in lines:
        # пробуем найти пар (поле цены) в строке (строго построчно)
        m = line_re.match(ln) or line_re2.match(ln)
        if m:
            pol = m.group("pol").strip()
            dc = int(m.group("dc"))
            hc = int(m.group("hc"))

            # нормализуем пол: если в конце есть запятая/точка — убрать
            pol = pol.strip(" ,;.-")

            # запомним цену Shenzhen для подстановки в дальнейшем
            if pol.lower().startswith("shenzhen"):
                shenzhen_20, shenzhen_40 = dc, hc

            results.append({"pol": pol, "pod": pod, "20DC": dc, "40HC": hc})
            continue

    # Подставляем цены Shenzhen для GUANGZHOU и XIAMEN при отсутствии собственных цен
    # (ищем в тексте слова GUANGZHOU и XIAMEN, если их нет в results как с ценой)
    pols_present = {r["pol"].lower() for r in results}
    for need in ("Guangzhou", "XIAMEN"):
        if need.lower() not in pols_present and shenzhen_20 is not None:
            results.append({"pol": need, "pod": pod, "20DC": shenzhen_20, "40HC": shenzhen_40})

    # Также дополнительно: если есть строка "NINGBO / SHANGHAI 1500 $ 2400 $"
    # наша регекспы это поймают, т.к. пол — любая текстовая часть до числа.
    # Но нам может понадобиться разделить "NINGBO / SHANGHAI" на два пол-адреса.
    expanded = []
    for rec in results:
        pol = rec["pol"]
        if "/" in pol:
            parts = [p.strip() for p in pol.split("/") if p.strip()]
            for p in parts:
                expanded.append({"pol": p, "pod": rec["pod"], "20DC": rec["20DC"], "40HC": rec["40HC"]})
        else:
            expanded.append(rec)

    # Ищем общий транзитный срок: "Общий Транзитный срок доставки ~37 дней."
    td = None
    mtd = re.search(r"Общий\s+Транзитный\s+срок\s+доставки[^0-9]*(\d{1,3})\s*д", text, re.I)
    if mtd:
        try:
            td = int(mtd.group(1))
        except:
            td = None
    for sea_rate in expanded:
        pol = sea_rate["pol"].title()
        pod = sea_rate["pod"].title()
        pol_port = port_dict.get(pol, pol)
        pod_port = region_dict.get(pod, pod)
        
        start_country = get_country(pol_port)
        end_country = get_country(pod_port)
        for i in sea_rate.keys():
            if i not in ["pol", "pod"]:
                container_type = i
                cost = sea_rate[i]
                data_scvoznoi.append({
                    "transport_type": "sea",
                    "start_point": f"{pol_port}, {start_country}",
                    "end_point": f"{pod_port}, {end_country}",
                    "final_destination": f"All, {end_country}",
                    "container_type": container_type,
                    "weight_limit": container_size_dict.get(container_type, ""),
                    "cost": cost,
                    "currency": currency_dict.get("$", "USD"),
                    "departure_dates": [],
                    "company": company,
                    "customs": f"Общий Транзитный срок доставки: {td}",
                    "conditions": "FILO COC"
                })
    # ==============================
    # ПАРСИНГ ЖД СТАРТУЮЩИХ ИЗ ПОРТА
    # ==============================
    data_rail = []
    rails = []
    pattern = re.compile(
        r"^(?P<pol>[A-Za-zА-Яа-я/]+)\s+"
        r"(?P<city>[A-Za-zА-Яа-яёЁ\-]+)\s+"
        r"(?P<r1>\d[\d\s]*)\s*₽\s+"
        r"(?P<r2>\d[\d\s]*)\s*₽\s+"
        r"(?P<r3>\d[\d\s]*)\s*₽$"
    )

    for ln in lines:
        ln = ln.strip()
        m = pattern.match(ln)
        if not m:
            continue

        r1 = int(m.group("r1").replace(" ", ""))
        r2 = int(m.group("r2").replace(" ", ""))
        r3 = int(m.group("r3").replace(" ", ""))

        rails.append({
            "pol": m.group("pol"),
            "pod": m.group("city"),
            "20DC": r1,
            "20DC_28": r2,
            "40HC": r3
        })
    
    for rail_rate in rails:
        #pol = rail_rate["pol"].title()
        pol = "Владивосток" if "ВМПП/SOLLERS" in rail_rate["pol"] else rail_rate["pol"].title()
        pod = rail_rate["pod"].title()
        pol_port = port_dict.get(pol, pol)
        pod_port = get_city_station(pod)
        
        start_country = get_country(pol_port)
        end_country = get_country(pod_port)
        for i in rail_rate.keys():
            if i not in ["pol", "pod"]:
                container_type = i
                cost = rail_rate[i]
                data_rail.append({
                    "transport_type": "rail",
                    "start_point": f"{pol_port}, {start_country}",
                    "end_point": f"{pod_port}, {end_country}",
                    "final_destination": f"All, {end_country}",
                    "container_type": "20DC" if "20DC_28" == container_type else container_type,
                    "weight_limit": container_size_dict.get(container_type, ""),
                    "cost": cost,
                    "currency": currency_dict.get("руб", "RUB"),
                    "departure_dates": [],
                    "company": company,
                    "customs": "",
                    "conditions": ""
                })
    print(data_rail)
    scvoznoi = pd.DataFrame(data_scvoznoi)
    rail = pd.DataFrame(data_rail)
    return pd.concat([scvoznoi, rail], ignore_index=True) 

def parse_Shenzhen_Wotu_International_Logistics(filepath: str):
    """
    Парсит текст с предложениями по перевозке грузов и возвращает список словарей с полями:
    - origin: точка отправления
    - destination: точка прибытия
    - price: цена
    - currency: валюта (обычно USD)
    - terms: условия (например, 40'HQ COC)
    - route: маршрут (через какие станции/границы)
    - timestamp: дата и время, если указаны
    """
    company = "Shenzhen Wotu International Logistics"
    tables, text_blocks = get_tables_pdf(None, filepath, company)
    text_all = "\n".join(text_blocks)
    text = text_all.replace("\r", "\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    data_rail = []

    fob_pattern = re.compile(
        r'^FOB\s+(.+?)\s*-\s*(.+?)\s*-\s*([\w\s]+?)\s+([40\'[A-Z]+\s+(?:COC|SOC))',
        re.IGNORECASE
    )

    # Шаблон для цены: ищем USD<число> или USD<пробел><число>
    price_pattern = re.compile(r'USD\s*(\d+)', re.IGNORECASE)

    current_route = None
    current_destination = None
    current_terms = None
    timestamp = None
    border_part = None
    currency = ""
    container_type = "40HQ"
    for line in lines:
        # Ищем маршрут FOB ... – ... – ...
        route_match = fob_pattern.search(line)
        if route_match:
            origin_part = route_match.group(1).strip()
            middle_part = route_match.group(2).strip()
            destination_part = route_match.group(3).strip()
            border_part = middle_part
            current_route = f"{origin_part} – {middle_part} – {destination_part}"
            current_destination = destination_part
            current_terms = None  # сбрасываем, т.к. может быть новый terms
            continue

        # Ищем цены
        price_match = price_pattern.search(line)
        if price_match:
            
            if "USD" in price_match.group(0):
                currency = "USD"
            else:
                currency = "руб"
            price_str = price_match.group(1)
            
            city_part = re.sub(r'[A-Z]{3}\d+|\d+', '', line).strip()
            city_part = re.sub(r'-\s*', '', city_part).strip() + "/"
            for pol_ in city_part.split("/"):
                if pol_ and price_str:
                    pol = pol_.title()
                    pod = current_destination.title()
                    pol_port = port_dict.get(pol, pol)
                    pod_port = region_dict.get(pod, pod)
                    border_point = border_dict.get(border_part, border_part)
                    start_country = get_country(pol_port)
                    end_country = get_country(pod_port)
                    data_rail.append({
                        "transport_type": "rail",
                        "start_point": f"{pol_port}, {start_country}",
                        "end_point": f"{pod_port}, {end_country}",
                        "final_destination": f"All, {end_country}",
                        "container_type": container_type,
                        "weight_limit": container_size_dict.get(container_type, ""),
                        "cost": price_str,
                        "currency": currency_dict.get(currency, "USD"),
                        "departure_dates": [],
                        "company": company,
                        "customs": "",
                        "conditions": "COC",
                        "border_point": border_point
                    })
    return pd.DataFrame(data_rail)


def parse_khasan_schedule(filepath: str):
    """
    Парсер расписания KHASAN:
    QINGDAO 4 Direct SOLLERS места есть
    22.11.2025
    14.11.2025
    """
    company = "KHASAN LLC"
    tables, text_blocks = get_tables_pdf(None, filepath, company)

    text_all = "\n".join(text_blocks)
    text_lines = [ln.strip() for ln in text_all.splitlines() if ln.strip()]
    results = []

    # Регулярка для шапки блока
    header_re = re.compile(
        r"^(?P<port>[A-Za-zА-Яа-яёЁ()/,.\s-]+?)\s+"
        r"(?P<num>\d{1,2}|\d{1,2}\.\d{1,2}\.\d{4})\s+"
        r"Direct\s+(?P<dest>[A-Za-zА-Яа-яёЁ]+)\s+места\s+есть$",
        re.IGNORECASE
    )

    date_re = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")

    current_block = None
    schedule = False
    etd_dates = []
    for line in text_lines:
        line = line.strip()
        if "РАСПИСАНИЕ" in line:
            schedule = True
        if not line or "Fwd" in line or not schedule:
            continue
        # Проверяем — это заголовок блока?
        m = header_re.match(line)
        
        if m:
            print(m)
            # Новый блок — сохраняем предыдущий
            if current_block:
                etd_dates = []
                results.append(current_block)

            current_block = {
                "port": m.group("port").strip(),
                "value": m.group("num"),
                "destination": m.group("dest"),
                "availability": "места есть",
                "etd_dates": etd_dates
            }
            print(current_block["etd_dates"])
            continue
        else:
            dates = date_re.findall(line)
            print(dates)
            for d in dates:
                etd_dates.append(d)
            if current_block:
                current_block["etd_dates"]=etd_dates

    # Сохраняем последний блок
    if current_block:
        results.append(current_block)

    return results

df_Shenzhen_Wotu_International_Logistics = parse_Shenzhen_Wotu_International_Logistics("D:/Logiways/Ноябрь/Тарифы+ Расписание-3/25. Shenzhen Wotu International Logistics/Тариф.pdf")

print(df_Shenzhen_Wotu_International_Logistics)

with pd.ExcelWriter("tariff_analysis_Shenzhen_Wotu_International_Logistics.xlsx") as writer:
    df_Shenzhen_Wotu_International_Logistics.to_excel(writer, sheet_name="Raw Data", index=False)
