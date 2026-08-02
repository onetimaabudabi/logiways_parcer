"""Сбор тарифов по 16 «старым» компаниям и выгрузка в tariff_analysis_TEST.xlsx.

Список компаний зафиксирован и совпадает с companies_all.json:
    ТрансКонтейнер, РусТранс Групп, Посейдон, Рейл Траст, Ametist Line,
    FESCO, TLC Baltic Line, Логопер, KHASAN, EuroSib, GrandLog, Mohill Rus,
    ТК Логистика, Гарант Интермодал, Panda Express Line, Sunsko.

Новые парсеры (vladmorrybport, atrans_global, khasan_docx, rustrans_group,
sansko_new, logoper_new, mohill_new, neco_line, ppk1_import, tdg, tml_income,
railtrust_sinokor, transcontainer_vietnam, ametist_dropoff, grandlog_wagon,
grandlog_terminal, sea_rail_operator и прочие) здесь НЕ импортируются и не
вызываются — они дают другие названия компаний и в этот список не входят.

Каждый парсер вызывается изолированно: падение одного не срывает прогон,
а попадает в итоговый отчёт.
"""

import io
import contextlib

import pandas as pd

from parsers.utils import segments_to_df

# --- Парсеры 16 «старых» компаний ------------------------------------------
import parsers.transcontainer as transcontainer_parser      # ТрансКонтейнер
import parsers.rustrans as rustrans_parser                  # РусТранс Групп
import parsers.poseidon as poseidon_parser                  # Посейдон
import parsers.railtrust as railtrust_parser                # Рейл Траст
import parsers.ametist_line as ametist_line_parser          # Ametist Line
import parsers.fesco as fesco_parser                        # FESCO
import parsers.tcl_baltic_line as tcl_baltic_line_parser    # TLC Baltic Line
import parsers.tcl_asia_line as tcl_asia_line_parser        # TLC Baltic Line
import parsers.logoper as logoper_parser                    # Логопер
import parsers.khasan as khasan_parser                      # KHASAN
import parsers.eurosib as eurosib_parser                    # EuroSib
import parsers.grandlog as grandlog_parser                  # GrandLog
import parsers.mohill as mohill_parser                      # Mohill Rus
import parsers.tk_logistika as tk_logistika_parser          # ТК Логистика
import parsers.garant_intermodal as garant_intermodal_parser  # Гарант Интермодал
import parsers.panda as panda_parser                        # Panda Express Line
import parsers.sansko as sansko_parser                      # Sunsko


# Реестр: (метка, компания, вызываемое, аргументы).
# Пустые аргументы — парсер сам находит файл или тянет данные с сайта.
PARSERS = [
    ("transcontainer", "ТрансКонтейнер", transcontainer_parser.parse,
     ("data/0916.pdf",)),

    ("rustrans", "РусТранс Групп", rustrans_parser.parse,
     ("data/RusTrans.xlsx",)),

    ("poseidon", "Посейдон", poseidon_parser.parse,
     ("data/Прием и отправка из портов с 15.03.2026 по 31.03.2026НДС 0%.docx",)),

    ("railtrust", "Рейл Траст", railtrust_parser.parse,
     ("data/Прайс Рейл Траст с 01.03.26.pdf",)),

    ("ametist_line", "Ametist Line", ametist_line_parser.parse,
     ("data/February 2026 Rates (2).pdf",)),

    ("fesco", "FESCO", fesco_parser.parse,
     ("data/FESCO Shuttles THROUGH from 01.02.2026 (COC RUR) "
      "(прил. 1 к Приказу № 19 от 19.01.2026) - upd.pdf",)),

    # TLC Baltic Line: в репозитории файлов нет, в PATHS_old были прописаны
    # пути с чужой машины (D:/Logiways/Диск/TCL Baltic Line/...).
    # Положите PDF в data/ и раскомментируйте.
    # ("tcl_baltic_line", "TLC Baltic Line", tcl_baltic_line_parser.parse,
    #  ("data/КП Февраль 2025г. BALTIC LINE  01-28 (1) (3).pdf",)),
    # ("tcl_asia_line", "TLC Baltic Line", tcl_asia_line_parser.parse,
    #  ("data/КП Февраль 2026 ASIA LINE   (2).pdf",)),

    ("logoper", "Логопер", logoper_parser.parse,
     ("data/ИНТЕРМОДАЛЬНЫЕ тарифы ЛОГОПЕР CY-FOR станции ДВ - "
      "Мск Екб Нск от 30.04.2026.pdf",)),

    ("khasan", "KHASAN", khasan_parser.parse,
     ("data/хасан2204.docx",)),

    # EuroSib тянет прайс и расписание со своего сайта (cont.eurosib.biz).
    # Требуется доступ в интернет; локальные копии лежат в download/.
    ("eurosib", "EuroSib", eurosib_parser.parse, ()),

    ("grandlog", "GrandLog", grandlog_parser.parse,
     ("data/GrandLog ЖД.pdf",)),

    ("mohill", "Mohill Rus", mohill_parser.parse,
     ("data/Notice MOHILL Line Far East JUNE (25.05).xlsx",)),

    ("tk_logistika", "ТК Логистика", tk_logistika_parser.parse, ()),

    ("garant_intermodal_1", "Гарант Интермодал", garant_intermodal_parser.parse,
     ("data/01.04.-30.04.Шанхай-Пусан-СOC-cтанции.pdf",)),
    ("garant_intermodal_2", "Гарант Интермодал", garant_intermodal_parser.parse,
     ("data/01.05.-15.05.-SOC-ШанхайПусан-ВМРП-Станц.назнач.pdf",)),
    ("garant_intermodal_3", "Гарант Интермодал", garant_intermodal_parser.parse,
     ("data/01.05.-15.05.-Шанхай-Пусан-жд-Москва.pdf",)),
    ("garant_intermodal_4", "Гарант Интермодал", garant_intermodal_parser.parse,
     ("data/10.04.-30.04.-Шанхай-Пусан-Врангель-станции-SOC.pdf",)),

    ("panda", "Panda Express Line", panda_parser.parse,
     ("data/Панда.pdf",)),

    ("sansko", "Sunsko", sansko_parser.parse,
     ("data/01.06 - 15.06 RUS Sunsko Far East Intermodal Service.pdf",)),
]

# Компании, которые должны получиться на выходе (сверяется в конце прогона).
EXPECTED_COMPANIES = {
    "ТрансКонтейнер", "РусТранс Групп", "Посейдон", "Рейл Траст",
    "Ametist Line", "FESCO", "TLC Baltic Line", "Логопер", "KHASAN",
    "EuroSib", "GrandLog", "Mohill Rus", "ТК Логистика",
    "Гарант Интермодал", "Panda Express Line", "Sunsko",
}


def parse_selected(verbose: bool = True):
    """Запускает парсеры из PARSERS и возвращает (df, отчёт)."""
    segments, report = [], []

    for label, company, func, args in PARSERS:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                result = func(*args)
            segments += result
            report.append((label, company, len(result), None))
        except FileNotFoundError as e:
            report.append((label, company, 0, f"нет файла: {str(e)[:70]}"))
        except Exception as e:
            report.append((label, company, 0, f"{type(e).__name__}: {str(e)[:70]}"))

    df = segments_to_df(segments)

    if verbose:
        print(f"{'парсер':22} {'компания':20} {'сегм.':>6}  примечание")
        for label, company, count, err in report:
            print(f"  {label:20} {company:20} {count:>6}  {err or ''}")

        ok = sum(1 for *_, err in report if err is None)
        print(f"\nПарсеров отработало: {ok}/{len(report)}; сегментов: {len(segments)}")

        if not df.empty and "company" in df.columns:
            got = set(df["company"].dropna().unique())
            print(f"\nКомпаний в выгрузке: {len(got)}")
            for name in sorted(got):
                print(f"  + {name}: {int((df['company'] == name).sum())} строк")
            missing = EXPECTED_COMPANIES - got
            if missing:
                print(f"\nНЕ ПОПАЛИ в выгрузку: {sorted(missing)}")
            extra = got - EXPECTED_COMPANIES
            if extra:
                print(f"ЛИШНИЕ (нет в companies_all.json): {sorted(extra)}")

    return df, report


def start_parse():
    df, _report = parse_selected()
    with pd.ExcelWriter("tariff_analysis_TEST.xlsx") as writer:
        df.to_excel(writer, sheet_name="Raw Data", index=False)
    print(f"\nЗаписано в tariff_analysis_TEST.xlsx: {len(df)} строк")
    return df


if __name__ == "__main__":
    start_parse()
