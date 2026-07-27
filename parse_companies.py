# parse_companies.py
"""
Парсер для "Транспортные компании.xlsx"
Скрипт обходит все листы кроме первого и создаёт для каждой ТК:
 - output/<company_safe>.json
 - output/<company_safe>.xlsx
А также общий:
 - output/all_companies.json
 - output/all_companies.xlsx

Формат итоговой записи (пример):
{
 "transport_type": "rail/sea",
 "start_point": pol_port,
 "end_point": pod_port,
 "container_type": "20DC",
 "weight_limit": "24",
 "cost": "100",
 "currency": "$",
 "departure_dates": [],
 "company": company,
 "customs": "Станция отправления: ...\nСтанция назначения: ...",
 "conditions": "FILO SOC/COC",
 "vessel": "GREEN DRAGON",
 "voyage_no": "92516W"
}
"""

import pandas as pd
import re
import json
from pathlib import Path
from datetime import datetime

INPUT_FILE = Path("Транспортные компании.xlsx")
OUTPUT_DIR = Path("output1")
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# ---------------------------
# Helpers: normalization
# ---------------------------
def _safe_name(name: str) -> str:
    s = re.sub(r"[^\w\d]+", "_", str(name or "")).strip("_")
    if not s:
        s = "company"
    return s[:80]

def _normalize_date(val):
    if pd.isna(val) or val == "":
        return None
    if isinstance(val, (pd.Timestamp, datetime)):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    # common patterns
    patterns = ["%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"]
    for fmt in patterns:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    # find first date-like substring
    m = re.search(r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", s)
    if m:
        ds = m.group(1)
        for fmt in ["%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d-%m-%Y"]:
            try:
                return datetime.strptime(ds, fmt).strftime("%Y-%m-%d")
            except Exception:
                pass
    # fallback: return original trimmed string (useful if it's like 'Q4 2025' or 'approx')
    return s or None

def _extract_currency_and_cost(s):
    if s is None or s == "":
        return None, None
    txt = str(s)
    # common currencies
    cur_map = {"$": "USD", "USD": "USD", "€": "EUR", "EUR": "EUR", "руб": "RUB", "RUB": "RUB", "¥": "CNY", "CNY": "CNY"}
    # find currency symbol or code
    c = None
    m = re.search(r"(\$|USD|€|EUR|руб|RUB|¥|CNY)", txt, re.I)
    if m:
        token = m.group(1)
        token_up = token.upper()
        c = cur_map.get(token, token_up)
    # find number
    m2 = re.search(r"([0-9]{1,3}(?:[ ,.\u00A0][0-9]{3})*(?:[.,][0-9]+)?)", txt.replace("\xa0", " "))
    val = None
    if m2:
        val = m2.group(1).replace(" ", "").replace(",", ".")
    return val, c or ""

def _detect_container(s):
    if s is None or s == "":
        return ""
    s = str(s).upper()
    if re.search(r"20('|’)?\s?DC|20DC|20'", s):
        return "20DC"
    if re.search(r"40('|’)?\s?HC|40HC|40'", s):
        return "40HC"
    # fallback check digits 20/40
    if re.search(r"\b20\b", s):
        return "20DC"
    if re.search(r"\b40\b", s):
        return "40HC"
    return ""

def _detect_weight(s):
    if s is None or s == "":
        return ""
    s = str(s)
    m = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s?(т|тонн|T|t|kg|кг)", s, re.I)
    if m:
        return m.group(1).replace(",", ".")
    m2 = re.search(r"\b(\d{1,3})\b", s)
    if m2:
        return m2.group(1)
    return ""

# ---------------------------
# Heuristics/strategies
# ---------------------------
def _find_header_row(df, look_for=("ETA","ETD","CUTOFF","№","РЕЙС","Судно","ПОРТ")):
    # look in top 6 rows for header-like content
    rows = min(8, len(df))
    for i in range(rows):
        r = df.iloc[i].astype(str).str.upper().fillna("").tolist()
        joined = " ".join(r)
        if any(k.upper() in joined for k in look_for):
            return i
    # fallback 0
    return 0

def _gather_free_text(df, header_row):
    parts = []
    # above header
    for r in range(0, header_row):
        parts.append(" ".join([str(x) for x in df.iloc[r].fillna("").astype(str).tolist()]).strip())
    # bottom 6 rows
    for r in range(max(header_row+1, len(df)-6), len(df)):
        parts.append(" ".join([str(x) for x in df.iloc[r].fillna("").astype(str).tolist()]).strip())
    # single long cells
    for r in range(len(df)):
        for c in range(df.shape[1]):
            v = str(df.iat[r,c])
            if len(v)>100:
                parts.append(v.strip())
    return "\n".join([p for p in parts if p])

# Generic parser for a sheet that is "ports across columns" (schedules)
def parse_sheet_schedule_style(df, header_row, company):
    """
    Парсер для layout: порты в заголовке рядами, затем под ними ETA/ETD/№рейса/CUTOFF и строки судов
    """
    results = []
    # header row contains port titles scattered across columns
    headers = df.iloc[header_row].astype(str).fillna("").tolist()
    # find columns which include the word 'Порт' OR look like "PortName (...)" by presence of known port names or parentheses
    port_indices = []
    for idx, val in enumerate(headers):
        s = str(val)
        if s.strip() == "":
            continue
        if "ПОРТ" in s.upper() or re.search(r"\b(Tianjin|Shanghai|Qingdao|Ningbo|Shenzhen|Vladivostok|Владивосток|Находк|Nakhodka|Hochiminh|Haiphong)\b", s, re.I):
            # normalize name
            pname = re.sub(r"(?i)порт", "", s).strip()
            pname = re.sub(r"терминал.*", "", pname, flags=re.I).strip()
            port_indices.append((idx, pname))
    # if no explicit port headers, attempt to group by repeating ETA/ETD labels in header+1 row
    if not port_indices:
        # look for columns where header_row or header_row+1 contain ETA/ETD
        candidate_cols = []
        for c in range(df.shape[1]):
            block = " ".join([str(df.iat[r,c]).upper() for r in range(header_row, min(header_row+2, len(df)))])
            if any(k in block for k in ("ETA","ETD","CUTOFF","РЕЙС","№")):
                candidate_cols.append(c)
        if candidate_cols:
            # group continuous sequences into port blocks
            groups = []
            cur = [candidate_cols[0]]
            for c in candidate_cols[1:]:
                if c == cur[-1] + 1:
                    cur.append(c)
                else:
                    groups.append(cur)
                    cur = [c]
            groups.append(cur)
            port_indices = []
            for g in groups:
                # search upward for name
                pname = ""
                for r in range(max(0, header_row-3), header_row):
                    cell = str(df.iat[r, g[0]]).strip()
                    if cell and "ETA" not in cell.upper() and "ETD" not in cell.upper():
                        pname = cell
                        break
                if not pname:
                    pname = f"port_{g[0]}"
                port_indices.append((g[0], pname))

    # Build port sections: start_col -> end_col, name
    port_sections = []
    for i, (start, pname) in enumerate(port_indices):
        end = df.shape[1] if i == len(port_indices)-1 else port_indices[i+1][0]
        port_sections.append((start, end, pname))

    free_text = _gather_free_text(df, header_row)

    # find vessel column (usually left side before first port)
    vessel_col = 0
    # look for explicit 'Судно' or 'Vessel' in header_row
    for c in range(0, min(6, df.shape[1])):
        if "СУДНО" in str(df.iat[header_row, c]).upper() or "VESSEL" in str(df.iat[header_row, c]).upper():
            vessel_col = c
            break

    # iterate rows
    for r in range(header_row+1, len(df)):
        vessel = str(df.iat[r, vessel_col]).strip()
        if vessel == "" or vessel.lower() in ("nan",):
            # try find vessel name in first 4 cols
            for c in range(0, min(6, df.shape[1])):
                v = str(df.iat[r,c]).strip()
                if v and len(v) > 1 and not re.search(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", v):
                    vessel = v
                    vessel_col = c
                    break
        if not vessel:
            continue

        # for each port in sheet create an entry row-port
        for (start, end, port_name) in port_sections:
            # examine header labels in this block to map ETA/ETD/CUTOFF/voyage/cost/container
            labels_top = [str(df.iat[header_row, c]).upper() for c in range(start, end)]
            labels_sub = []
            if header_row+1 < len(df):
                labels_sub = [str(df.iat[header_row+1, c]).upper() for c in range(start, end)]
            # prepare mapping from block columns to types
            mapping = {}
            for j in range(start, end):
                L = (str(df.iat[header_row, j]) + " " + (str(df.iat[header_row+1, j]) if header_row+1 < len(df) else "")).upper()
                if "ETA" in L:
                    mapping["ETA"] = j
                elif "ETD" in L:
                    mapping["ETD"] = j
                elif "CUTOFF" in L:
                    mapping["CUTOFF"] = j
                elif "РЕЙС" in L or "№" in L or "VOY" in L:
                    mapping["voyage_no"] = j
                elif re.search(r"20'|40'|20DC|40HC|20FT|40FT", L):
                    mapping["container"] = j
                elif re.search(r"\$|USD|EUR|RUB|руб", L):
                    mapping["cost"] = j
            # fallback scan cells for date/cost/container
            ETA = None; ETD = None; CUTOFF = None; voyage_no = None; cost = None; currency = ""; container_type = ""; weight = ""
            if "ETA" in mapping:
                ETA = _normalize_date(df.iat[r, mapping["ETA"]])
            if "ETD" in mapping:
                ETD = _normalize_date(df.iat[r, mapping["ETD"]])
            if "CUTOFF" in mapping:
                CUTOFF = _normalize_date(df.iat[r, mapping["CUTOFF"]])
            if "voyage_no" in mapping:
                voyage_no = str(df.iat[r, mapping["voyage_no"]]).strip()
            if "cost" in mapping:
                cval, cur = _extract_currency_and_cost(df.iat[r, mapping["cost"]])
                cost, currency = cval, cur
            if "container" in mapping:
                container_type = _detect_container(df.iat[r, mapping["container"]])
            # scan block cells if missing
            for c in range(start, end):
                cell = str(df.iat[r, c]).strip()
                if not ETA and re.search(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", cell):
                    ETA = _normalize_date(cell)
                if not cost:
                    v,curr = _extract_currency_and_cost(cell)
                    if v:
                        cost, currency = v, curr
                if not container_type:
                    container_type = _detect_container(cell)
                if not weight:
                    weight = _detect_weight(cell)

            # build departure_dates list
            dep_dates = []
            if ETD: dep_dates.append({"type": "ETD","value":ETD})
            if ETA: dep_dates.append({"type": "ETA","value":ETA})
            if CUTOFF: dep_dates.append({"type": "CUTOFF","value":CUTOFF})

            entry = {
                "transport_type": "sea",
                "start_point": port_name,
                "end_point": "",
                "container_type": container_type or "",
                "weight_limit": weight or "",
                "cost": cost or "",
                "currency": currency or "",
                "departure_dates": dep_dates,
                "company": company,
                "customs": f"Верх/низ листа: { _gather_free_text(df, header_row) }",
                "conditions": "",  # could be filled from free text
                "vessel": vessel,
                "voyage_no": voyage_no or ""
            }
            results.append(entry)
    return results

# Generic parser for "table-like" sheet: each row is a tariff record with columns
def parse_sheet_table_style(df, header_row, company):
    results = []
    # Use header_row as column names
    header = df.iloc[header_row].astype(str).fillna("").tolist()
    data = df.iloc[header_row+1:].reset_index(drop=True)
    data.columns = header
    free_text = _gather_free_text(df, header_row)
    # try to locate important columns by name heuristics
    col_map = {}
    for c in data.columns:
        name = str(c).lower()
        if any(k in name for k in ("порт отправ", "port of loading", "pol", "получ")):
            col_map["pol"] = c
        if any(k in name for k in ("порт назначения", "port of discharge", "pod")):
            col_map["pod"] = c
        if any(k in name for k in ("контейнер", "20", "40", "container")):
            col_map["container"] = c
        if any(k in name for k in ("вес", "ton", "тн", "kg")):
            col_map["weight"] = c
        if any(k in name for k in ("стоимость", "rate", "price", "cost")):
            col_map["cost"] = c
        if any(k in name for k in ("валюта", "currency", "$", "usd", "руб")):
            col_map["currency"] = c
        if any(k in name for k in ("etd","отпр","departure")):
            col_map["etd"] = c
        if any(k in name for k in ("eta","приб","arrival")):
            col_map["eta"] = c
        if any(k in name for k in ("cutoff","cut off")):
            col_map["cutoff"] = c
        if any(k in name for k in ("судно","vessel")):
            col_map["vessel"] = c
        if any(k in name for k in ("рейс","voy","voyage","№")):
            col_map["voyage_no"] = c

    for _, row in data.iterrows():
        vessel = str(row.get(col_map.get("vessel",""), "")).strip() if col_map.get("vessel") else ""
        pol = str(row.get(col_map.get("pol",""), "")).strip() if col_map.get("pol") else ""
        pod = str(row.get(col_map.get("pod",""), "")).strip() if col_map.get("pod") else ""
        voyage = str(row.get(col_map.get("voyage_no",""), "")).strip() if col_map.get("voyage_no") else ""
        container_type = _detect_container(row.get(col_map.get("container",""), ""))
        weight_limit = _detect_weight(row.get(col_map.get("weight",""), ""))
        cost_raw = row.get(col_map.get("cost",""), "")
        cost, currency = _extract_currency_and_cost(cost_raw)
        etd = _normalize_date(row.get(col_map.get("etd",""), ""))
        eta = _normalize_date(row.get(col_map.get("eta",""), ""))
        cutoff = _normalize_date(row.get(col_map.get("cutoff",""), ""))
        dep_dates = []
        if etd: dep_dates.append({"type":"ETD","value":etd})
        if eta: dep_dates.append({"type":"ETA","value":eta})
        if cutoff: dep_dates.append({"type":"CUTOFF","value":cutoff})

        entry = {
            "transport_type": "rail" if "rail" in str(company).lower() or "жд" in str(company).lower() else "sea",
            "start_point": pol,
            "end_point": pod,
            "container_type": container_type or "",
            "weight_limit": weight_limit or "",
            "cost": cost or "",
            "currency": currency or "",
            "departure_dates": dep_dates,
            "company": company,
            "customs": f"Станция отправления: {pol}.\nСтанция назначения: {pod}.\nДоп: {free_text}",
            "conditions": "", 
            "vessel": vessel,
            "voyage_no": voyage
        }
        results.append(entry)
    return results

# Fallback generic parser: try to find key tokens in rows and produce one entry per meaningful row
def parse_sheet_generic(df, header_row, company):
    results = []
    free_text = _gather_free_text(df, header_row)
    # try to build a small table: treat header_row as header if many non-empty cells
    header = df.iloc[header_row].astype(str).fillna("").tolist()
    nonempty_headers = sum(1 for h in header if str(h).strip())
    if nonempty_headers >= 2:
        return parse_sheet_table_style(df, header_row, company)

    # otherwise: scan rows for vessel names / date patterns and group
    for r in range(header_row+1, len(df)):
        row_str = " ".join([str(x) for x in df.iloc[r].fillna("").astype(str).tolist()]).strip()
        if not row_str:
            continue
        # if row contains both vessel-like token and date -> treat as entry
        has_date = bool(re.search(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", row_str))
        if has_date or len(row_str.split())>3:
            # heuristics: extract first vessel-like token (all-caps words)
            m_v = re.search(r"([A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9\-\s]{2,30})", row_str)
            vessel = m_v.group(1).strip() if m_v else ""
            # extract any currency/price
            cost, currency = _extract_currency_and_cost(row_str)
            # extract container
            container_type = _detect_container(row_str)
            # extract weight
            weight = _detect_weight(row_str)
            # extract dates
            dates = re.findall(r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", row_str)
            dep_dates = [{"type": f"DATE_{i+1}", "value": _normalize_date(d)} for i,d in enumerate(dates)]
            # attempt to detect pol/pod by keywords "отправ" "назнач"
            pol = ""
            pod = ""
            mpol = re.search(r"Отправл(?:ение|ено|я|:)?\s*([^;,\n]+)", row_str, re.I)
            mpod = re.search(r"Назн(?:ачение|ачен|:)?\s*([^;,\n]+)", row_str, re.I)
            if mpol: pol = mpol.group(1).strip()
            if mpod: pod = mpod.group(1).strip()

            entry = {
                "transport_type": "sea",
                "start_point": pol,
                "end_point": pod,
                "container_type": container_type or "",
                "weight_limit": weight or "",
                "cost": cost or "",
                "currency": currency or "",
                "departure_dates": dep_dates,
                "company": company,
                "customs": free_text,
                "conditions": row_str[:300],
                "vessel": vessel,
                "voyage_no": ""
            }
            results.append(entry)
    return results

# Top-level per-sheet dispatcher: analyze layout and call corresponding parser
def parse_sheet(book_path, sheet_name):
    df_raw = pd.read_excel(book_path, sheet_name=sheet_name, header=None, dtype=object)
    df = df_raw.fillna("")
    header_row = _find_header_row(df)
    company = sheet_name
    # decide layout type
    # heuristic 1: header row contains many "Порт" or port names -> schedule style
    hr_cells = " ".join([str(x).upper() for x in df.iloc[header_row].tolist()])
    if any(x in hr_cells for x in ("ПОРТ","Tianjin".upper(),"SHANGHAI","VLADIVOSTOK","НАХОДК")) or "ETA" in hr_cells or "ETD" in hr_cells:
        return parse_sheet_schedule_style(df, header_row, company)
    # heuristic 2: header row looks like column headers (contains "стоимость"/"rate"/"container"/"pod")
    if any(x in hr_cells for x in ("СТОИМОСТ", "RATE", "COST", "CONTAINER", "ПОЛ", "ПОД", "ETD", "ETA")):
        return parse_sheet_table_style(df, header_row, company)
    # fallback
    return parse_sheet_generic(df, header_row, company)

# ---------------------------
# Main: process all sheets except first
# ---------------------------
def parse_all(input_file=INPUT_FILE):
    xls = pd.ExcelFile(input_file)
    all_results = {}
    sheets = xls.sheet_names
    if len(sheets) <= 1:
        print("No sheets to parse (only base sheet present).")
        return {}

    for sheet in sheets[1:]:
        try:
            print(f"Parsing sheet: {sheet} ...")
            parsed = parse_sheet(input_file, sheet)
            all_results[sheet] = parsed

            # save per-company JSON
            safe = _safe_name(sheet)
            json_path = OUTPUT_DIR / f"{safe}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)

            # save per-company xlsx flattened
            rows_flat = []
            for rec in parsed:
                dep = "; ".join([f"{d['type']}:{d['value']}" for d in rec.get("departure_dates", [])])
                rows_flat.append({
                    "company": rec.get("company"),
                    "vessel": rec.get("vessel"),
                    "voyage_no": rec.get("voyage_no",""),
                    "transport_type": rec.get("transport_type"),
                    "start_point": rec.get("start_point"),
                    "end_point": rec.get("end_point"),
                    "container_type": rec.get("container_type"),
                    "weight_limit": rec.get("weight_limit"),
                    "cost": rec.get("cost"),
                    "currency": rec.get("currency"),
                    "departure_dates": dep,
                    "customs": rec.get("customs"),
                    "conditions": rec.get("conditions")
                })
            df_out = pd.DataFrame(rows_flat)
            xlsx_path = OUTPUT_DIR / f"{safe}.xlsx"
            df_out.to_excel(xlsx_path, index=False)
            print(f" -> saved {len(rows_flat)} rows to {xlsx_path}")

        except Exception as e:
            print(f"Error parsing sheet {sheet}: {e}")

    # combined files
    combined_json = OUTPUT_DIR / "all_companies.json"
    with open(combined_json, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    combined_xlsx = OUTPUT_DIR / "all_companies.xlsx"
    with pd.ExcelWriter(combined_xlsx) as writer:
        for sheet, parsed in all_results.items():
            rows_flat = []
            for rec in parsed:
                dep = "; ".join([f"{d['type']}:{d['value']}" for d in rec.get("departure_dates", [])])
                rows_flat.append({
                    "company": rec.get("company"),
                    "vessel": rec.get("vessel"),
                    "voyage_no": rec.get("voyage_no",""),
                    "transport_type": rec.get("transport_type"),
                    "start_point": rec.get("start_point"),
                    "end_point": rec.get("end_point"),
                    "container_type": rec.get("container_type"),
                    "weight_limit": rec.get("weight_limit"),
                    "cost": rec.get("cost"),
                    "currency": rec.get("currency"),
                    "departure_dates": dep,
                    "customs": rec.get("customs"),
                    "conditions": rec.get("conditions")
                })
            df_out = pd.DataFrame(rows_flat)
            sheet_safe = _safe_name(sheet)[:31]
            try:
                df_out.to_excel(writer, sheet_name=sheet_safe, index=False)
            except Exception:
                # fallback: shorten sheet name
                df_out.to_excel(writer, sheet_name=f"sheet_{list(all_results.keys()).index(sheet)}", index=False)

    print("Saved combined json & xlsx to output/")
    return all_results

if __name__ == "__main__":
    parse_all()
