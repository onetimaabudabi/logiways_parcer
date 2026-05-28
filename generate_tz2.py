"""
Генератор ТЗ по парсеру.
Открываем шаблон договора, находим раздел «Техническое задание» и заменяем
его на ТЗ по модулю парсинга, сохраняя стиль/форматирование шаблона.
"""

from copy import deepcopy
import re

from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

TEMPLATE = "D:/Documents/Договор_на_разработку_ФЛ_1Х_Макар_Андрей_драфт.docx"
OUTPUT   = "D:/Documents/TZ_Parser_Logiways_v2.docx"

# ─────────────────────────────────────────────
# 1. Загружаем шаблон
# ─────────────────────────────────────────────
doc = Document(TEMPLATE)
paras = doc.paragraphs

# Находим параграф «Техническое задание № 1» (первый в блоке ТЗ)
# В шаблоне он идёт примерно с параграфа 155 (Normal + bold «Техническое задание № 1»)
tz_start_idx = None
for i, p in enumerate(paras):
    if "Техническое задание" in p.text and i > 140:
        tz_start_idx = i
        break

if tz_start_idx is None:
    raise RuntimeError("Не найден параграф 'Техническое задание' в шаблоне")

# Параграф «Подписи сторон» — по нему ищем конец блока ТЗ
# В шаблоне он обозначен «АКТ СДАЧИ-ПРИЁМКИ РЕЗУЛЬТАТОВ РАБОТ»
tz_end_idx = None
for i, p in enumerate(paras):
    if i <= tz_start_idx:
        continue
    text = p.text.strip()
    if "АКТ СДАЧИ" in text.upper() or "СДАЧИ-ПРИЁМКИ" in text.upper():
        tz_end_idx = i
        break
if tz_end_idx is None:
    tz_end_idx = len(paras)  # до конца

print(f"ТЗ блок: параграфы {tz_start_idx}..{tz_end_idx-1}")

# ─────────────────────────────────────────────
# 2. Вспомогательные функции добавления параграфов
#    с теми же стилями что в шаблоне
# ─────────────────────────────────────────────
body_xml = doc.element.body

def _clone_para_after(ref_para_el, new_text, style_name, bold=False, align=None, first_indent=None):
    """Вставляет параграф с заданным стилем непосредственно перед target_el."""
    p_new = OxmlElement('w:p')

    pPr = OxmlElement('w:pPr')
    pStyle = OxmlElement('w:pStyle')
    pStyle.set(qn('w:val'), style_name)
    pPr.append(pStyle)

    if align is not None:
        jc = OxmlElement('w:jc')
        jc.set(qn('w:val'), align)
        pPr.append(jc)

    if first_indent is not None:
        ind = OxmlElement('w:ind')
        ind.set(qn('w:firstLine'), str(first_indent))
        pPr.append(ind)

    p_new.append(pPr)

    r = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    if bold:
        b = OxmlElement('w:b')
        rPr.append(b)
    r.append(rPr)
    t = OxmlElement('w:t')
    t.set(qn('xml:space'), 'preserve')
    t.text = new_text
    r.append(t)
    p_new.append(r)

    ref_para_el.addnext(p_new)
    return p_new


def _para_xml(style_name, runs, align=None, first_indent=None, space_after=None):
    """
    Создаёт XML-элемент параграфа.
    runs: list of (text, bold, size_pt)  -- size_pt=None значит наследуется
    """
    p_el = OxmlElement('w:p')
    pPr = OxmlElement('w:pPr')

    pStyle = OxmlElement('w:pStyle')
    pStyle.set(qn('w:val'), style_name)
    pPr.append(pStyle)

    if align:
        jc = OxmlElement('w:jc')
        jc.set(qn('w:val'), align)
        pPr.append(jc)

    if first_indent is not None:
        ind = OxmlElement('w:ind')
        ind.set(qn('w:firstLine'), str(first_indent))
        pPr.append(ind)

    if space_after is not None:
        spacing = OxmlElement('w:spacing')
        spacing.set(qn('w:after'), str(space_after))
        pPr.append(spacing)

    p_el.append(pPr)

    for (txt, bold, size_pt) in runs:
        r = OxmlElement('w:r')
        rPr = OxmlElement('w:rPr')
        if bold:
            b = OxmlElement('w:b')
            rPr.append(b)
        if size_pt:
            sz = OxmlElement('w:sz')
            sz.set(qn('w:val'), str(int(size_pt * 2)))
            rPr.append(sz)
            szCs = OxmlElement('w:szCs')
            szCs.set(qn('w:val'), str(int(size_pt * 2)))
            rPr.append(szCs)
        r.append(rPr)
        t = OxmlElement('w:t')
        t.set(qn('xml:space'), 'preserve')
        t.text = txt
        r.append(t)
        p_el.append(r)

    return p_el


# ─────────────────────────────────────────────
# 3. Удаляем старый блок ТЗ (параграфы tz_start_idx .. tz_end_idx-1)
#    и запоминаем позицию вставки
# ─────────────────────────────────────────────
# Найдём XML-элементы параграфов для удаления
all_p_els = body_xml.findall(qn('w:p'))

# Найдём XML-элемент «АКТ» (первый после удаляемого блока) — вставлять перед ним
insert_before_el = all_p_els[tz_end_idx] if tz_end_idx < len(all_p_els) else None

# Удаляем параграфы блока ТЗ
for i in range(tz_start_idx, tz_end_idx):
    el = all_p_els[i]
    el.getparent().remove(el)

# ─────────────────────────────────────────────
# 4. Формируем новый блок ТЗ и вставляем перед insert_before_el
# ─────────────────────────────────────────────
# Стили шаблона (из анализа):
#   Normal + bold size=139700 (10pt*2=20 → 139700 EMU = 11pt в half-points? нет)
#   139700 / 12700 = 11.0 pt  (EMU->pt: /12700)
#   Halfpoints: 139700 / 6350 = 22 → 11pt
#   В half-points: 139700 EMU → но размер шрифта в half-points хранится в w:sz
#   Значит size=139700 это значение в EMU, а w:sz хранит half-points:
#   docx.shared.Pt(11) = 139700 EMU, w:sz = 22 (half-points = 11pt)
#   Нормальный текст шаблона = 11pt (139700 EMU)
#   Заголовок (Heading 1) наследует стиль
#   Первый отступ: 540385 EMU / 914400 * 2.54 * 10 = ~15mm ≈ абзацный отступ

# Стили:
S_NORMAL  = "Normal"
S_H1      = "Heading1"       # в XML ID без пробела
S_H2      = "Heading2"
S_H3      = "Heading3"
S_BODY    = "BodyText"       # Body Text
S_COMPACT = "Compact"
S_03      = "03"             # «03 абзац»

# Размеры в half-points (w:sz):
# 11pt = 22;  12pt = 24;  14pt = 28; 10pt = 20
SZ11 = None  # наследуем от стиля (Normal = 11pt в шаблоне)

FIRST_INDENT = 540385   # EMU ≈ 1.25 cm абзацный отступ шаблона

new_paragraphs = []  # список XML-элементов для вставки

def N(*runs, align=None, fi=None, space_after=None):
    """Normal paragraph."""
    return _para_xml(S_NORMAL, runs, align=align, first_indent=fi, space_after=space_after)

def H1(*runs):
    return _para_xml(S_H1, runs)

def H2(*runs):
    return _para_xml(S_H2, runs)

def H3(*runs):
    return _para_xml(S_H3, runs)

def BT(*runs):
    """Body Text — с левым отступом как в шаблоне."""
    return _para_xml(S_BODY, runs)

def C(*runs):
    """Compact (пункт списка как в шаблоне)."""
    return _para_xml(S_COMPACT, runs)

def T(*runs, fi=None, space_after=0):
    """03 абзац (основной текст с отступом)."""
    return _para_xml(S_03, runs, first_indent=fi, space_after=space_after)

def t(text, bold=False):
    return (text, bold, None)

def tb(text):
    return (text, True, None)

# ─── Заголовок ТЗ ───
new_paragraphs += [
    N(tb("Техническое задание"), tb(" "), tb("№ 2"), align="center"),
    N(tb("(далее — Техническое задание № 2, Техническое задание, ТЗ)"), align="center"),
    N(t(""), fi=0),
    N(t("Настоящее Техническое задание № 2 "),
      t("(далее — Техническое задание № 2)"),
      t(" является неотъемлемой частью "),
      t("Договора № "), t("12"), t("-ФЛ"), t(" от "),
      t("«"), t("24"), t("» ноября"), t(" 20"), t("25"), t(" г."),
      tb(" "), tb("(далее — Договор)"),
      t(" между"),
      fi=FIRST_INDENT),
    N(tb("Кручининым Юрием Владимировичем, "),
      t("гражданином РФ, паспорт 4518 025850, действующим от своего имени и в своих интересах, именуемым в дальнейшем "),
      tb("«"), tb("Заказчик"), tb("»"), t(", с одной стороны, и"),
      fi=FIRST_INDENT),
    N(tb("Родько Никитой Сергеевичем"),
      t(", гражданином РФ, паспорт серия "),
      t("_____"),
      t(", зарегистрированным по адресу: "),
      t("____"),
      t(", именуемым в дальнейшем "),
      tb("«"), tb("Исполнитель"), tb("»"),
      t(", с другой стороны."),
      fi=FIRST_INDENT),
    N(t("Стороны согласовали настоящее Техническое задание, а по отдельности — «Сторона». "),
      fi=FIRST_INDENT),
    N(t("Термины и определения, использованные в настоящем Техническом задании, имеют значение, определённое в Договоре, если иное прямо не предусмотрено настоящим Техническим заданием."),
      fi=FIRST_INDENT),
]

# ─── Описание задания ───
new_paragraphs += [
    T(t("В соответствии с условиями Договора Заказчик поручает, а Исполнитель принимает на себя обязанность выполнить следующие Работы (далее — Работы) в составе Программного комплекса (платформы) "),
      t("«Logiways»"),
      t(", указанного в Договоре:"),
      fi=0),
    T(t("Программный комплекс (платформа) "),
      t("«Logiways»"),
      t(" включает в себя следующие модули:"),
      fi=FIRST_INDENT),
]

modules = [
    "Модуль парсинга и структурирования тарифов и данных транспортных компаний — модуль BD: сбор, очистка, нормализация тарифных данных, создание базы данных и загрузка через API",
    "SMS-верификация и управление учётными записями — модуль БД: users, security и API: /api/users",
    "Управление организациями — модуль БД: organizations и API: /api/organizations",
    "Локации — модуль БД: routes и API: /api/locations",
    "Перевозчики (транспортные компании) — модуль БД: carriers и API: /api/carriers",
    "Маршрутные сегменты и тарифы — модуль БД: routes и API: /api/route-segments, /api/route-segments/{id}/tariffs",
    "Поиск маршрутов — модуль БД: routes и API: /api/routes/search",
    "Тарифные пакеты / Billing — модуль БД: billing и API: /api/packages",
    "Платёжная интеграция (Tochka Bank) — модуль БД: payments, integrations и API: /api/payments",
    "Интеграция с SMS-сервисом (SMS.ru / Exolve) — внешний сервис, прямой вызов API",
]
for m in modules:
    new_paragraphs.append(C(t(m)))

new_paragraphs.append(
    T(t("Объём Работ по настоящему Техническому заданию, а также иные условия их выполнения определены в приложениях к настоящему Техническому заданию."),
      fi=0)
)

# ─── Heading ТЗ ───
new_paragraphs += [
    H1(t("Техническое задание по разработке модуля парсинга и структурирования тарифов и данных транспортных компаний")),
    H2(t("Раздел 1. Общее описание и назначение модуля")),
    H3(t("1. Цели и задачи")),
]

new_paragraphs += [
    BT(t("Модуль парсинга и структурирования тарифов "), t("— автоматизированный программный компонент платформы "),
       t("«Logiways»"), t(", предназначенный для сбора тарифных данных транспортных компаний, "
       "их нормализации в единую каноническую структуру и загрузки в базу данных платформы.")),
    BT(t("Модуль решает следующие задачи:")),
]

tasks = [
    "автоматическое извлечение тарифных таблиц, маршрутов, расписаний и условий перевозки из документов форматов PDF, XLSX, DOCX;",
    "нормализация и стандартизация географических наименований (портов, станций, городов) через централизованные справочники;",
    "создание базы данных локаций (портов, ж/д-станций, городов, терминалов, таможенных пунктов, пограничных переходов), транспортных компаний, маршрутных сегментов и тарифов;",
    "загрузка структурированных данных в платформу через REST API;",
    "мониторинг изменений тарифных документов в хранилище Google Drive и автоматический перезапуск парсинга;",
    "поддержка более 35 транспортных компаний с индивидуальными алгоритмами парсинга.",
]
for task in tasks:
    new_paragraphs.append(C(t(task)))

# ─── Раздел 2 ───
new_paragraphs += [
    H2(t("Раздел 2. Канонические модели данных (TariffSegment)")),
    H3(t("2.1. Основная единица данных")),
    BT(t("Все парсеры создают объекты класса "), t("TariffSegment"), t(" — неизменяемый датакласс (frozen dataclass), являющийся единственным форматом передачи тарифных данных между подсистемами модуля.")),
    BT(t("Обязательные поля:")),
]
for f in ["transport_type — тип транспорта: sea, rail, auto, air;",
          "start_point — пункт отправления;",
          "end_point — пункт назначения;",
          "container_type — тип контейнера (20DC, 40HC, 20GP и др.)."]:
    new_paragraphs.append(C(t(f)))

new_paragraphs.append(BT(t("Тарифные поля:")))
for f in ["cost — стоимость; currency — валюта (USD, RUB, EUR);",
          "weight_limit, min_weight_kg, max_weight_kg — весовые параметры;",
          "conditions — условия тарифа (FOB, FOT, CY-CY).",
          "valid_from, valid_to — период действия тарифа (формат ISO 8601)."]:
    new_paragraphs.append(C(t(f)))

new_paragraphs.append(BT(t("Поля временны́х характеристик:")))
for f in ["departure_dates — даты отправлений;",
          "departures — расписание рейсов: судно, номер рейса, CUTOFF, ETD, ETA, терминал;",
          "duration_min_days, duration_max_days — срок доставки в днях."]:
    new_paragraphs.append(C(t(f)))

new_paragraphs.append(BT(t("Поля географической иерархии:")))
for f in ["start_location_type, end_location_type, final_destination_location_type — типы локаций (port, rail_station, city, terminal, border, customs, warehouse);",
          "parent_start_location, parent_end_location — родительские локации (город для порта);",
          "stopovers_location, stopovers_location_type, stopovers_location_country — промежуточные порты перевалки;",
          "dropoff_location, dropoff_location_type — пункты сдачи контейнеров;",
          "border_point, border_location — пограничные переходы."]:
    new_paragraphs.append(C(t(f)))

new_paragraphs.append(BT(t("Сервисные поля:")))
for f in ["company — наименование транспортной компании;",
          "container_ownership — принадлежность контейнера: COC (перевозчика), SOC (грузовладельца), ANY;",
          "port_service_term — условия порта: FILO, FIFO, LILO, LIFO;",
          "customs — признак таможенного оформления;",
          "sequence — порядковый номер сегмента в составном маршруте."]:
    new_paragraphs.append(C(t(f)))

new_paragraphs += [
    H3(t("2.2. Валидация и конвертация")),
    BT(t("Метод "), t("TariffSegment.from_dict()"), t(" выполняет десериализацию с проверкой обязательных полей; при их отсутствии выбрасывается "), t("ValueError"), t(" с перечислением недостающих полей. Метод "), t("to_dict()"), t(" сериализует объект в словарь для передачи в API.")),
    BT(t("Функция "), t("to_segments(data)"), t(" универсально конвертирует DataFrame, список словарей или список TariffSegment в стандартизованный список объектов. Функция "), t("_clean_record()"), t(" заменяет значения NaN на None при чтении из Excel/CSV.")),
]

# ─── Раздел 3 ───
new_paragraphs += [
    H2(t("Раздел 3. Справочники и нормализация данных (shared.py)")),
    H3(t("3.1. Справочник портов (port_dict)")),
    BT(t("Словарь из более чем 300 записей: латинское / транслитерированное название порта → официальное русскоязычное наименование. Охватывает порты России, Китая, Японии, Кореи, США, Европы, Ближнего Востока, Индии, ЮВА. Используется всеми парсерами для унификации написания названий портов из документов разных компаний.")),
    H3(t("3.2. Справочник стран (country_dict)")),
    BT(t("Инвертированный индекс: страна → список городов и портов. Охватывает более 30 стран. Функция "), t("get_country(city)"), t(" возвращает страну по названию города/порта.")),
    H3(t("3.3. Справочник ж/д-станций (stations_dist) и портовых терминалов (port_city_dict)")),
    BT(t("Маппинг: город → множество ж/д-станций (более 80 записей для 30+ городов России). Функция "), t("get_city_station(station)"), t(" возвращает город. Аналогично "), t("port_city_dict"), t(": город → список терминалов; функция "), t("get_city_port(port)"), t(" возвращает город для терминала.")),
    H3(t("3.4. Прочие справочники")),
]
for item in [
    "currency_dict — нормализация обозначений валют ($→USD, руб→RUB);",
    "container_size_dict — максимальный вес груза для каждого типа контейнера (20DC→24 т, 40HC→28 т и др.);",
    "region_dict — аббревиатуры и латинские написания городов → русскоязычные наименования (МСК→Москва, Ekaterinburg→Екатеринбург);",
    "border_dict — пограничные переходы (Erlian→Эрлан, Manzhouli→Маньчжурия, Horgos→Хоргос).",
]:
    new_paragraphs.append(C(t(item)))

new_paragraphs += [
    H3(t("3.5. Вспомогательные функции")),
]
for f in [
    "convert_date(date_str) — конвертация дат формата «15 April» в DD.MM.YYYY;",
    "normalize_date(date_str) — конвертация дат в ISO формат YYYY-MM-DD;",
    "get_container_type_from_header(cell) — определение типа контейнера из заголовка таблицы;",
    "_to_number_or_zero(value), _to_str_or_empty(value) — безопасные конверторы значений с обработкой NaN/None;",
    "clean(v) — нормализация строк (удаление переносов строк, лишних пробелов).",
]:
    new_paragraphs.append(C(t(f)))

# ─── Раздел 4 ───
new_paragraphs += [
    H2(t("Раздел 4. Извлечение данных из документов (get_tables_sites.py)")),
    H3(t("4.1. Функция get_tables_pdf — извлечение таблиц из PDF")),
    BT(t("При наличии URL скачивает PDF через HTTP GET (потоковая загрузка чанками по 8 КБ). Открывает файл через pdfplumber. Для каждой страницы извлекает таблицы (page.extract_tables()) и конвертирует в DataFrame. Параллельно сохраняет текст страниц (page.extract_text()) для захвата данных вне таблиц — заголовков, условий, примечаний. Результаты сохраняются в CSV и TXT-файлы для отладки.")),
    H3(t("4.2. Алгоритм parse_tariff_matrix_to_json — обработка тарифных матриц")),
    BT(t("Специализированный алгоритм для таблиц формата «пункт отправления — станция назначения — тарифы по типам контейнеров»:")),
]
for step in [
    "поиск строки заголовков: сканирование первых 20 строк по ключевым словам «Пункт отправления» / «Станция назначения»;",
    "сборка многострочных заголовков: конкатенация значений из диапазона ±2 строки от заголовка для обработки объединённых ячеек;",
    "нормализация заголовков типов контейнеров: функция normalize_header() унифицирует обозначения (20'DC <24т → 20DC_lt24t, 40'HC <28т → 40HC_lt28t);",
    "обработка разрывов origin: при пустом значении в колонке origin для строки используется значение предыдущей непустой строки (forward fill);",
    "нормализация цен: функция normalize_price() извлекает числа из строк (удаление символов валют, пробелов), возвращает None при отсутствии числового значения.",
]:
    new_paragraphs.append(C(t(step)))

new_paragraphs += [
    H3(t("4.3. Функция get_shedule_EuroSib — парсинг расписаний судовых рейсов")),
    BT(t("Обрабатывает Excel-файлы расписания со сложной многоколоночной структурой. Алгоритм: автоматическое определение строки заголовка по ячейке «Судно»; определение групп портов (каждая = 4 колонки: № рейса, CUTOFF, ETA, ETD); извлечение названий портов и терминалов из строк выше заголовка; нормализация дат через pandas to_datetime. Результат: словарь "), t("{порт: [{vessel, voyage_no, CUTOFF, ETA, ETD, terminal}]}")),
]

# ─── Раздел 5 ───
new_paragraphs += [
    H2(t("Раздел 5. Парсеры транспортных компаний (каталог parsers/)")),
    H3(t("5.1. Архитектура парсеров")),
    BT(t("Для каждой транспортной компании разработан отдельный модуль-парсер в директории parsers/. Все парсеры реализуют единый интерфейс: публичная функция parse(file_path) возвращает список объектов TariffSegment. Для PDF используется pdfplumber, для Excel — pandas read_excel(), для DOCX — python-docx. Нормализация географических наименований производится через справочники shared.py.")),
    H3(t("5.2. Перечень парсеров")),
]

companies = [
    ("EuroSib", "PDF + Excel. Морской фрахт COC/SOC + ЖД-тарифы. Скачивает PDF с сайта перевозчика. Таблицы A1/A2: порт отгрузки → порт назначения, тарифы 20DC/40HC, условия FOB/FOT. Таблица JD: матрица ЖД-тарифов порт→станция через parse_tariff_matrix_to_json. Обогащает каждый тариф данными расписания (судно, рейс, CUTOFF, ETA, ETD, терминал)."),
    ("FESCO", "PDF. Тарифы FESCO Shuttles THROUGH (COC RUR). Извлекает дату valid_from из имени файла по регулярному выражению. Различает заголовки стран (UPPER CASE) и строки портов. Пропускает ж/д-строки по паттерну «(город)цифра» в конце ячейки."),
    ("Гарант Интермодал", "PDF. 5 типов файлов с разной структурой. Извлекает период действия тарифа из текста документа через regex. Маршруты Шанхай/Пусан → порты ДВ → ж/д-станции назначения. Тип файла определяется по имени (COC/SOC, порт, тип тарифа)."),
    ("РусТранс", "Excel. Морские и ЖД-перевозки. Обработка лимитов безопасности для 20'/40'."),
    ("ТрансКонтейнер", "PDF. Многостраничная структура. Маршруты через ДВ-порты и ж/д-станции России."),
    ("KHASAN LLC", "DOCX. Мультимодальные маршруты через ст. Хасан."),
    ("GrandLog", "PDF. Два метода: parse() для ЖД-файла и parse_GrandLog_offer() для морских тарифов."),
    ("Poseidon", "DOCX. Тарифы по приёму и отправке из портов."),
    ("RailTrust", "PDF. Два метода: parse() (стандартные) и parse_skvoznoy() (сквозные тарифы)."),
    ("Аметист Лайн", "PDF. Морские тарифы, типы start/end локации."),
    ("TCL Baltic Line / TCL Asia Line", "PDF. Два отдельных модуля по географическим направлениям."),
    ("Логопер", "PDF. Интермодальные тарифы CY-FOR: ДВ-станции → Москва/Екатеринбург/Новосибирск."),
    ("Mohill Rus", "Excel. Исключён раздел VVO+Railway по особенностям структуры."),
    ("Moro Logistics", "PDF. Предобработка через get_tables_pdf_MoroLogistics()."),
    ("TML", "Excel. Извлечение из общего файла Транспортные компании.xlsx."),
    ("Torgmoll", "Excel. Морские и интермодальные маршруты."),
    ("Мармед-контейнер", "Excel. Тарифы контейнерного агентства."),
    ("HS China Limited", "Excel. Китайские морские тарифы."),
    ("GW China Limited", "Excel. Транзитное время, Via-порты, даты отправления."),
    ("Shenzhen-группа (5 компаний)", "PDF и Excel. Shenzhen Wotu International, Shenzhen Interrail Logistics, Shenzhen Space Logistics, Shenzhen Eagleway Supply Chain Management, Shenzhen Wotu International Logistics. Каждая имеет собственный алгоритм разбора специфических форматов китайских экспедиторов."),
    ("LCL", "Excel. Тарифы LCL (Less than Container Load). Типы локации старт/финиш."),
    ("Hesion Global Logistics", "Excel. ETD, VIA-данные."),
    ("NingBo Y-STAR Logistics", "Excel. Поля free time хранения."),
    ("Spacelog", "Excel. Многоформатный парсер."),
    ("Shaanxi Coal International Logistics", "Excel. Специализированные угольные тарифы."),
    ("Transforever International Forwarding", "Excel. Международные тарифы на экспедирование."),
]
for name, desc in companies:
    new_paragraphs.append(C(tb(name + ": "), t(desc)))

# ─── Раздел 6 ───
new_paragraphs += [
    H2(t("Раздел 6. Мониторинг Google Drive (drive/service.py)")),
    H3(t("6.1. Аутентификация")),
    BT(t("Сервисный аккаунт Google (Service Account) с ключом JSON. Область доступа: https://www.googleapis.com/auth/drive. Клиент Google Drive API v3.")),
    H3(t("6.2. Алгоритм мониторинга")),
    BT(t("Получение стартового токена страницы изменений (getStartPageToken). Циклический запрос changes().list() с актуальным pageToken. Фильтрация: пропуск удалённых файлов; обработка только файлов с родительской папкой. Для каждого изменения: запрос метаданных родительской папки (files().get()), имя папки = имя компании. Скачивание файла через MediaIoBaseDownload (потоковая запись); удаление старого файла перед загрузкой. После загрузки: вызов start_parse(). Интервал проверки: 120 секунд.")),
    H3(t("6.3. Структура хранилища")),
    BT(t("Корневая папка Google Drive: «Тарифы транспортных компаний». Вложенная структура: каждая транспортная компания — отдельная подпапка. Локальное зеркало: drive/downloads/{компания}/{файл}.")),
]

# ─── Раздел 7 ───
new_paragraphs += [
    H2(t("Раздел 7. Создание базы данных и API-клиент (send_api_New.py)")),
    H3(t("7.1. Создание базы данных")),
    BT(t("В рамках модуля реализуется создание и наполнение базы данных платформы Logiways. Основные сущности БД:")),
]
for entity in [
    "Локации (Locations) — иерархический справочник: страны, города, порты, ж/д-станции, терминалы, таможенные пункты, пограничные переходы, склады. Атрибуты: тип локации, название, код страны (ISO 2), регион, ссылка на родительскую локацию, координаты (lat/lon), внешние коды.",
    "Транспортные компании (Transport Companies) — перевозчики с контактной информацией, логотипом, флагом активности и языками работы.",
    "Маршрутные сегменты (Route Segments) — маршруты с типом транспорта, ID локаций отправления/назначения, пограничным переходом, таможней, сроками доставки и расписанием.",
    "Тарифы (Tariffs) — тарифные предложения: тип цены, тип контейнера, принадлежность контейнера, период действия, НДС, инкотермс, портовые условия, весовые полосы (WeightBand), надбавки (Charge), контейнерная политика, пункты сдачи (DropoffLocation).",
    "Координаты маршрутов (Route Segment Coordinates) — точки ломаной линии маршрута для визуализации на карте.",
]:
    new_paragraphs.append(C(t(entity)))

new_paragraphs += [
    H3(t("7.2. Типизированные модели данных")),
    BT(t("Модуль содержит полный набор датаклассов для сериализации запросов к API: TransportCompaniesCreate, LocationsCreate, RouteSegmentCreate, RouteSegmentCreateBulk, TariffCreate, TariffUpdate, WeightBand, Charge, ContainerPolicy, DropoffLocationCreate, RouteSegmentCoordinate, Departure.")),
    BT(t("Типобезопасные перечисления (Enum) для всех категорийных полей: TransportType (rail, sea, auto, air), LocationType (port, rail_station, city, terminal, border, customs, warehouse), ContainerType (20DC, 20GP, 40HC и др.), ContainerOwnership (COC, SOC, ANY), PortServiceTermType (FILO/FIFO/LILO/LIFO), Currency (USD, EUR, RUB, KZT и др.), CountryCodeType (30+ кодов ISO 2).")),
    H3(t("7.3. HTTP-клиент LogiwaysClient")),
    BT(t("Базовый URL: https://test.logiways.ru. Использует requests.Session(). Методы аутентификации: signup(), request_sms(), verify_sms(), refresh_token(). Автоматическое обновление токена при получении HTTP 401 (_handle_401).")),
    BT(t("Методы управления данными:")),
]
for m in [
    "create_transport_companies() — POST /admin/transport-companies;",
    "get_transport_company_by_name() — поиск по точному и частичному совпадению имени. GET /admin/transport-companies?search=;",
    "create_locations() — POST /admin/locations; сериализует Enum-значения в строки перед отправкой;",
    "find_location_id_by_name() — поиск локации по имени + типу + стране + родительской локации; при отсутствии автоматически создаёт запись. GET /admin/locations?search={name}&limit=500;",
    "get_route_segments() — GET /admin/route-segments;",
    "ensure_route_segment_id() — верификация существования сегмента с повторными попытками (до 5 попыток, интервал 1 с);",
    "create_tariff() — POST /admin/tariffs; update_tariff() — PUT /admin/tariffs/{id};",
    "bulk replace сегментов — массовая замена всех сегментов компании одним запросом;",
    "загрузка dropoff-локаций — PUT /admin/tariffs/{tariff_id}/dropoff-locations.",
]:
    new_paragraphs.append(C(t(m)))

new_paragraphs += [
    H3(t("7.4. Ключ сегмента и управление паузами")),
    BT(t("Детерминированный ключ сегмента: MD5-хеш конкатенации company_id | transport_type | start_location_id | end_location_id. Настраиваемые задержки между запросами: 0,5 с (общие запросы), 2,0 с (после bulk-замены сегментов), 0,5 с (после создания тарифа) — для соблюдения rate limit API.")),
    H3(t("7.5. Нормализация дат и кодов стран")),
    BT(t("Функция convert_to_iso_date() поддерживает 6 форматов: YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY, MM/DD/YYYY, YYYY.MM.DD, DD-MM-YYYY; принимает строки и объекты datetime. Функция normalize_country_code() приводит коды стран к формату ISO 2: принимает 2-буквенные коды, имена из Enum CountryCodeType, английские названия (RUSSIA→RU, CHINA→CN и др.).")),
]

# ─── Раздел 8 ───
new_paragraphs += [
    H2(t("Раздел 8. Сроки и стоимость работ")),
    H3(t("8.1. Сроки")),
    T(tb("Дата начала выполнения работ: "), t("«"), tb("24"), t("» ноября"), t(" 2025 г.;"), fi=0, space_after=0),
    T(tb("Окончание: "), t("«"), tb("___"), t("» _________ 202"), t("_"), t(" г."), fi=0, space_after=0),
    H3(t("8.2. Стоимость")),
    BT(t("Стоимость работ по настоящему Техническому заданию составляет "), tb("___"), tb(" ("), tb("_________"), tb(") рублей 00 копеек"), t(". Стоимость включает вознаграждение за отчуждение исключительного права на результаты работ, в том числе на Программу для ЭВМ и базы данных платформы "), t("«Logiways»"), t(" в составе данного модуля.")),
    H3(t("8.3. Порядок оплаты")),
    T(t("Стоимость в размере "), tb("___"), tb(" ("), tb("_________"), tb(") рублей 00 копеек"),
      t(" перечисляется по реквизитам, указанным в п. V настоящего Технического задания, в течение "),
      tb("10 (десяти)"), t(" рабочих дней с даты подписания Акта сдачи-приёмки результатов работ по настоящему Техническому заданию в порядке, установленном Договором."),
      fi=0, space_after=0),
]

# ─── Подписи ───
new_paragraphs += [
    N(t("")),  # пустая строка перед подписями
]

# ─────────────────────────────────────────────
# 5. Вставляем новые параграфы перед insert_before_el
# ─────────────────────────────────────────────
if insert_before_el is not None:
    for p_el in reversed(new_paragraphs):
        insert_before_el.addprevious(p_el)
else:
    for p_el in new_paragraphs:
        body_xml.append(p_el)

# ─────────────────────────────────────────────
# 6. Сохраняем
# ─────────────────────────────────────────────
doc.save(OUTPUT)
print(f"OK Saved: {OUTPUT}")
