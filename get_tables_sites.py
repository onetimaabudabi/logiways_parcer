import pdfplumber
import pandas as pd
import re
from pathlib import Path
import requests

def download_file_requests(url, filename):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Проверка на ошибки HTTP
        
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Файл успешно скачан и сохранён как {filename}")
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при скачивании файла: {e}")

def parse_shedule_EuroSib_ports_to_json(file_path: str, output_json: str = None):
	"""
	Парсит Excel-расписание с компоновкой:
	- слева колонка "Судно"
	- далее для каждого порта по 4 колонки: "№ рейса", "CUTOFF", "ETA", "ETD"
	- над ними в верхних строках указаны названия портов (ячейки, содержащие "Порт ...")

	Возвращает словарь: {порт: [{vessel, voyage_no, CUTOFF, ETA, ETD}, ...]}
	"""
	def normalize_date(value):
		if pd.isna(value):
			return None
		try:
			dt = pd.to_datetime(value, dayfirst=True, errors="coerce")
			return dt.strftime("%d.%m.%Y") if pd.notna(dt) else None
		except Exception:
			return None

	# Читаем первый лист как есть, без заголовков
	df = pd.read_excel(file_path, header=None)

	# Ищем строку, где находится заголовок с текстом "Судно"
	vessel_header_row = None
	vessel_col = None
	for ridx in range(min(20, len(df))):
		row_str = df.iloc[ridx, :].astype(str).str.strip().str.lower()
		matches = row_str[row_str == "судно"]
		if not matches.empty:
			vessel_header_row = ridx
			vessel_col = int(matches.index[0])
			break
	if vessel_header_row is None or vessel_col is None:
		raise ValueError("Не удалось найти строку заголовков с ячейкой 'Судно'.")

	# Строка(и) выше содержат названия портов; возьмём до двух строк выше
	port_rows_to_scan = list(range(max(0, vessel_header_row - 2), vessel_header_row))

	# Определим группы портов: каждая группа состоит из 4 колонок, начиная от первого вхождения "№ рейса"
	# Сканируем заголовочную строку (строка с "Судно") справа от колонки "Судно"
	header_row_values = df.iloc[vessel_header_row, :].astype(str).str.strip().tolist()
	port_groups = []  # [{"start": c, "cols": {"voyage_no": c, "CUTOFF": c+1, "ETA": c+2, "ETD": c+3}, "name": "Порт ..."}]
	c = vessel_col + 1
	max_col = df.shape[1]
	while c < max_col:
		label = str(header_row_values[c]).lower()
		if "№ рейса" in label or "№" == label or "номер рейса" in label or "рейс" in label:
			voy_col = c
			cut_col = c + 1 if c + 1 < max_col else None
			eta_col = c + 2 if c + 2 < max_col else None
			etd_col = c + 3 if c + 3 < max_col else None
			group = {"start": voy_col, "cols": {"voyage_no": voy_col, "CUTOFF": cut_col, "ETA": eta_col, "ETD": etd_col}, "name": None}
			port_groups.append(group)
			c += 4
		else:
			c += 1

	if not port_groups:
		raise ValueError("Не удалось определить группы колонок для портов (№ рейса, CUTOFF, ETA, ETD).")

	# Присвоим именам портов и терминалам значения из строк над заголовком
	for g in port_groups:
		name_found = None
		terminal_found = None
		start_col = g["start"]
		candidate_cols = list(range(start_col, min(start_col + 4, max_col)))
		for pr in port_rows_to_scan:
			for cc in candidate_cols:
				val = df.iat[pr, cc]
				if pd.isna(val):
					continue
				text = str(val).strip()
				if not text:
					continue
				if ("Порт" in text or "порт" in text) and not name_found:
					name_found = text
				elif ("Терминал" in text or "терминал" in text) and not terminal_found:
					terminal_found = text
			if name_found:
				# не выходим полностью, чтобы успеть найти терминал на другой строке
				pass
		# если не нашли по слову "Порт", просто берём первый непустой текст сверху
		if not name_found:
			for pr in port_rows_to_scan:
				for cc in candidate_cols:
					val = df.iat[pr, cc]
					if pd.isna(val):
						continue
					text = str(val).strip()
					if text:
						name_found = text
						break
				if name_found:
					break
		g["name"] = (name_found or f"Порт_{start_col}").replace("Порт", "Порт").strip()
		g["terminal"] = terminal_found.strip() if terminal_found else None

	# Читаем данные, начиная со строки ниже заголовка
	data_start = vessel_header_row + 1
	result = {g["name"]: [] for g in port_groups}

	for ridx in range(data_start, len(df)):
		vessel_val = df.iat[ridx, vessel_col] if vessel_col is not None and vessel_col < df.shape[1] else None
		vessel = None if pd.isna(vessel_val) else str(vessel_val).strip()
		# пропустим полностью пустые строки
		row_is_empty = True
		for g in port_groups:
			cols = g["cols"]
			values = [df.iat[ridx, c] if c is not None and c < df.shape[1] else None for c in cols.values()]
			if any(pd.notna(v) and str(v).strip() for v in values):
				row_is_empty = False
				break
		if row_is_empty and (not vessel or not str(vessel).strip()):
			continue

		for g in port_groups:
			cols = g["cols"]
			voy = df.iat[ridx, cols["voyage_no"]] if cols["voyage_no"] is not None else None
			cut = df.iat[ridx, cols["CUTOFF"]] if cols["CUTOFF"] is not None else None
			eta = df.iat[ridx, cols["ETA"]] if cols["ETA"] is not None else None
			etd = df.iat[ridx, cols["ETD"]] if cols["ETD"] is not None else None

			entry_present = any([
				pd.notna(voy) and str(voy).strip(),
				pd.notna(cut) and str(cut).strip(),
				pd.notna(eta) and str(eta).strip(),
				pd.notna(etd) and str(etd).strip(),
				vessel and str(vessel).strip(),
			])
			if not entry_present:
				continue

			entry = {
				"vessel": vessel,
				"voyage_no": None if pd.isna(voy) else str(voy).strip(),
				"CUTOFF": normalize_date(cut),
				"ETA": normalize_date(eta),
				"ETD": normalize_date(etd),
			}
			# добавляем терминал из заголовков порта
			entry["terminal"] = g.get("terminal")
			# отфильтруем полностью пустые записи (все поля None/пустые)
			if any(v for v in entry.values()):
				result[g["name"]].append(entry)

	# Сохраняем JSON при необходимости
	if output_json:
		with open(output_json, "w", encoding="utf-8") as f:
			json.dump(result, f, ensure_ascii=False, indent=2)

	return result

def get_shedule_EuroSib(url, path):
    download_file_requests(url, path)
    return parse_shedule_EuroSib_ports_to_json(path)

def get_tables_pdf(url=None, path='', company=''):

    if url != None:
        download_file_requests(url, path)
    pdf_path = Path(path)

    tables_data = []
    extra_info = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Попытка извлечь таблицы
            for table in page.extract_tables():
                df = pd.DataFrame(table)
                tables_data.append(df)

            # Текст страницы
            text = page.extract_text()
            if text:
                extra_info.append(text)
    # Сохранение таблиц
    for i, df in enumerate(tables_data, 1):
        df.to_csv(f"tablets/table_{i}_{company}.csv", index=False)

    # Сохранение дополнительного текста
    with open(f"tablets/extra_info_{company}.txt", "w", encoding="utf-8") as f:
        f.write("\n\n--- PAGE SPLIT ---\n\n".join(extra_info))
    
    return tables_data, extra_info
#tables, extra_info = get_tables_pdf(url='https://cont.eurosib.biz/files/shipping/sea%20line%20tariffs.pdf', path='download/sea_line_tariffs.pdf', company="company")
#print(tables, extra_info)