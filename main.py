import pandas as pd
import os

from parsers.utils import segments_to_df

import parsers.amethyst as amethyst_parser
import parsers.eurosib as eurosib_parse
import parsers.grandlog as grandlog_parser
import parsers.gw_china_limited as gw_china_limited_parser
import parsers.hesion_global_logistics as hesion_global_logistics_parser
import parsers.hs_china_limited as HS_CHINA_LIMITED_parse
import parsers.khasan as khasan_parser
import parsers.lcl as lcl_parser
import parsers.marmedcontainer as marmedcontainer_parse
import parsers.mohill as mohill_parse
import parsers.moro_logistics as moro_logistics_parser
import parsers.ningbo_ystar_logistics as ningbo_ystar_logistics_parser
import parsers.shaanxi_coal_international_logistics as shaanxi_coal_international_logistics_parser
import parsers.shenzhen_eagleway_supply_chain_management as shenzhen_eagleway_supply_chain_management_parser
import parsers.shenzhen_interrail_logistics as shenzhen_interrail_logistics_parser
import parsers.shenzhen_space_logistics as shenzhen_space_logistics_parser
import parsers.shenzhen_wotu_international as shenzhen_wotu_international_parser
import parsers.shenzhen_wotu_international_logistics as shenzhen_wotu_international_logistics_parser
import parsers.spacelog as spacelog_parser
import parsers.tml as tml_parser
import parsers.torgmoll as Torgmoll_parse
import parsers.transforever_international_forwarding as transforever_international_forwarding_parser
import parsers.unknown_company1 as unknown_company1_parser
import parsers.unknown_company2 as unknown_company2_parser
import parsers.unknown_company3 as unknown_company3_parser
import parsers.unknown_company4 as unknown_company4_parser
import parsers.transcontainer as transcontainer_parse
import parsers.rustrans as rustrans_parse
import parsers.tcl_baltic_line as tcl_baltic_line_parser
import parsers.tcl_asia_line as tcl_asia_line_parser
import parsers.fesco as fesco_parser
import parsers.poseidon as poseidon_parser
import parsers.railtrust as railtrust_parser
import parsers.ametist_line as ametist_line_parser
import parsers.global_logistic as global_logistic_parser
import parsers.logoper as logoper_parser
import parsers.tk_logistika as tk_logistika_parser
import parsers.garant_intermodal as garant_intermodal_parser
import parsers.sansko as sansko_parser
import parsers.panda as panda_parser

'''
Мармед - Контейнерное Агенство
HS CHINA LIMITED
Torgmoll
Mohill Rus - не парсится VVO+Railway
TML - порт не парсим
GW CHINA LIMITED - tt, Via, дата
Shenzhen Eagleway Supply Chain Management - стация, via, etd
LCL - add type start and end
Amethyst - add type start and end
Hesion Global Logistics - etd, VIA
NingBo Y-STAR Logistics - free time
UnknownCompany1 - ?
Spacelog - много чего 
Moro Logistics
Transforever International Forwarding
Shaanxi Coal International Logistics 
Неизвестная_компания_4
Неизвестная_компания_3
Неизвестная_компания_2
SHENZHEN INTERRAIL LOGISTICS

'''

PATHS_old = {
    "TransContainer": "data/0916.pdf",
    "RusTrans": "data/RusTrans.xlsx",
    "MarmedContainer": "data/Marmed-container.xlsx",
    "HS_CHINA_LIMITED": "data/HS_CHINA_LIMITED.xlsx",
    "Torgmoll": "data/Torgmoll.xlsx",
    "Mohill": "data/Mohill.xlsx",
    "TransportCompanies": "Транспортные компании.xlsx",
    "GrandLog": "D:/Logiways/parser/data/GrandLog ЖД.pdf",
    "GrandLog_sea": "D:/Logiways/parser/data/Коммерческое предложение на морские перевозки с 15 апреля 2026 г..pdf",
    "MoroLogistics": "D:/Logiways/Август/Тарифы+ Расписание/24. Moro Logistics/Тариф.pdf",
    "UnknownCompany2": "D:/Logiways/Ноябрь/Тарифы+ Расписание-3/30. Неизвестная компания_2/Тариф.pdf",
    "Khasan": "D:/Logiways/parser/data/хасан2204.docx",
    "SHENZHEN_INTERRAIL": "D:/Logiways/Ноябрь/Тарифы+ Расписание-3/27. SHENZHEN INTERRAIL LOGISTICS/Тариф+Расписание_2.pdf",
    "Shenzhen_Wotu_Logistics": "D:/Logiways/Ноябрь/Тарифы+ Расписание-3/25. Shenzhen Wotu International Logistics/Тариф.pdf",
    "Fesco": "data/FESCO Shuttles THROUGH from 01.02.2026 (COC RUR) (прил. 1 к Приказу № 19 от 19.01.2026) - upd.pdf",
    "Poseidon": "data/Прием и отправка из портов с 15.03.2026 по 31.03.2026НДС 0%.docx",
}

PATHS = [
    {
        "company":"Khasan",
        "folder": "drive/downloads/",
        "parser": khasan_parser
    },
    {
        "company":"LCL",
        "folder": "drive/downloads/",
        "parser": lcl_parser
    },
    {
        "company":"Shenzhen Wotu Logistics",
        "folder": "drive/downloads/",
        "parser": shenzhen_wotu_international_logistics_parser
    },
    {
        "company":"TransContainer",
        "folder": "drive/downloads/",
        "parser": transcontainer_parse
    },
    {
        "company":"RusTrans",
        "folder": "drive/downloads/",
        "parser": rustrans_parse
    },
    {
        "company":"Torgmoll",
        "folder": "drive/downloads/",
        "parser": Torgmoll_parse
    },
    {
        "company":"TML",
        "folder": "drive/downloads/",
        "parser": tml_parser
    },
    {
        "company":"Spacelog",
        "folder": "drive/downloads/",
        "parser": spacelog_parser
    },
    {
        "company":"EuroSib",
        "folder": "drive/downloads/",
        "parser": eurosib_parse
    },
    {
        "company":"GrandLog",
        "folder": "drive/downloads/",
        "parser": grandlog_parser
    },
    {
        "company":"Amethyst",
        "folder": "drive/downloads/",
        "parser": amethyst_parser
    },
    {
        "company":"Mohill",
        "folder": "drive/downloads/",
        "parser": mohill_parse
    },
    {
        "company": "TLC Baltic Line",
        "folder": "D:/Logiways/Диск/TCL Baltic Line/",
        "parser": tcl_baltic_line_parser,
        "filename": "КП Февраль 2025г. BALTIC LINE  01-28 (1) (3).pdf"
    },
    {
        "company": "TLC Asia Line",
        "folder": "D:/Logiways/Диск/TCL Baltic Line/",
        "parser": tcl_asia_line_parser,
        "filename": "КП Февраль 2026 ASIA LINE   (2).pdf"
    },
    {
        "company": "RailTrust",
        "folder": "data/",
        "parser": railtrust_parser,
        "filename": "Прайс Рейл Траст с 01.03.26.pdf"
    },
]

def parse_all(paths=None):
    segments = []
    paths = paths or PATHS_old #PATHS
    TransportCompanies = paths.get("TransportCompanies", "Транспортные компании.xlsx")
    #segments += khasan_parser.parse(paths["Khasan"])
    '''
    for path in paths:
        folder = path.get("folder","") + path.get("company", "")
        if os.path.exists(folder):
            files = [os.path.join(folder, f) for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
            if len(files) != 0:
                segments += path["parser"].parse(files[0])
    '''

    #segments += eurosib_parse.parse()
    #segments += logoper_parser.parse("data/ИНТЕРМОДАЛЬНЫЕ тарифы ЛОГОПЕР CY-FOR станции ДВ - Мск Екб Нск от 30.04.2026.pdf")
    #segments += panda_parser.parse("data/Панда.pdf")
    segments += mohill_parse.parse("data/Notice MOHILL Line Far East JUNE (25.05).xlsx")
    # Санско
    #segments += sansko_parser.parse("data/01.06 - 15.06 RUS Sunsko Far East Intermodal Service.pdf")

    '''
    # Гарант Интермодал - 5 файлов
    segments += garant_intermodal_parser.parse("data/01.04.-30.04.-Все-порты-жд-Москва (1).pdf")
    segments += garant_intermodal_parser.parse("data/01.04.-30.04.Шанхай-Пусан-СOC-cтанции.pdf")
    segments += garant_intermodal_parser.parse("data/01.05.-15.05.-SOC-ШанхайПусан-ВМРП-Станц.назнач.pdf")
    segments += garant_intermodal_parser.parse("data/01.05.-15.05.-Шанхай-Пусан-жд-Москва.pdf")
    segments += garant_intermodal_parser.parse("data/10.04.-30.04.-Шанхай-Пусан-Врангель-станции-SOC.pdf")
    '''
    '''
    #Готово
    segments += poseidon_parser.parse(paths["Poseidon"])
    segments += railtrust_parser.parse("data/Прайс Рейл Траст с 01.03.26.pdf")
    segments += railtrust_parser.parse_skvoznoy("data/Прайс Рейл Траст сквозной с 10.03.2026.pdf")
    segments += ametist_line_parser.parse("data/February 2026 Rates (2).pdf")
    
    segments += logoper_parser.parse("data/ИНТЕРМОДАЛЬНЫЕ тарифы ЛОГОПЕР CY-FOR станции ДВ - Мск Екб Нск от 11.03.2026 (1).pdf")
    
    #segments += global_logistic_parser.parse("data/Dear Baksanovaig.docx") # тут только truck
    
    #Готово
    segments += fesco_parser.parse(paths["Fesco"])
    #segments += transcontainer_parse.parse(paths["TransContainer"])
    segments += rustrans_parse.parse(paths["RusTrans"])
    segments += eurosib_parse.parse()
    segments += grandlog_parser.parse(paths["GrandLog"]) #май
    segments += tcl_baltic_line_parser.parse("D:/Logiways/Диск/TCL Baltic Line/КП Февраль 2025г. BALTIC LINE  01-28 (1) (3).pdf")
    segments += tcl_asia_line_parser.parse("D:/Logiways/Диск/TCL Baltic Line/КП Февраль 2026 ASIA LINE   (2).pdf")
    segments += khasan_parser.parse(paths["Khasan"])
    segments += grandlog_parser.parse_GrandLog_offer(paths["GrandLog_sea"]) #май
    segments += mohill_parse.parse(paths["Mohill"])
    segments += tk_logistika_parser.parse()
    '''
    
    #segments += shenzhen_space_logistics_parser.parse(TransportCompanies)
    #segments += shenzhen_wotu_international_parser.parse(TransportCompanies)
    
    #segments += shenzhen_wotu_international_logistics_parser.parse(
    #    paths["Shenzhen_Wotu_Logistics"]
    #)
    
    '''
    segments += marmedcontainer_parse.parse(paths["MarmedContainer"])
    segments += HS_CHINA_LIMITED_parse.parse(paths["HS_CHINA_LIMITED"])
    segments += Torgmoll_parse.parse(paths["Torgmoll"])
    segments += mohill_parse.parse(paths["Mohill"])
    segments += tml_parser.parse(TransportCompanies)
    segments += gw_china_limited_parser.parse(TransportCompanies)
    segments += shenzhen_eagleway_supply_chain_management_parser.parse(
        TransportCompanies
    )
    segments += lcl_parser.parse(TransportCompanies)
    segments += amethyst_parser.parse(TransportCompanies)
    segments += hesion_global_logistics_parser.parse(TransportCompanies)
    segments += ningbo_ystar_logistics_parser.parse(TransportCompanies)
    segments += unknown_company1_parser.parse(TransportCompanies)
    segments += spacelog_parser.parse(TransportCompanies)
    tables_data_MoroLogistics = moro_logistics_parser.get_tables_pdf_MoroLogistics(
        "", paths["MoroLogistics"], "Moro Logistics"
    )
    segments += moro_logistics_parser.parse(tables_data_MoroLogistics, company_name="Moro Logistics")
    segments += transforever_international_forwarding_parser.parse(TransportCompanies)
    segments += shaanxi_coal_international_logistics_parser.parse(TransportCompanies)
    segments += unknown_company4_parser.parse(TransportCompanies)
    segments += unknown_company3_parser.parse(TransportCompanies)
    segments += unknown_company2_parser.parse(paths["UnknownCompany2"])
    segments += shenzhen_interrail_logistics_parser.parse(paths["SHENZHEN_INTERRAIL"])
    '''

    return segments_to_df(segments)

def start_parse():
    df_all = parse_all()
    with pd.ExcelWriter("tariff_analysis_TEST.xlsx") as writer:
        df_all.to_excel(writer, sheet_name="Raw Data", index=False)
    exit(0)
start_parse()
'''
if __name__ == "__main__":
    
    df_all = parse_all()
    with pd.ExcelWriter("tariff_analysis_ALL_NEW.xlsx") as writer:
        df_all.to_excel(writer, sheet_name="Raw Data", index=False)
    exit(0)
    #run_parsing_and_send()
    df_EuroSib = parse_EuroSib()
    with pd.ExcelWriter("tariff_analysis_EuroSib.xlsx") as writer:
        df_EuroSib.to_excel(writer, sheet_name="Raw Data", index=False)
    df_TransContainer = segments_to_df(parse_TransContainer(PATHS["TransContainer"]))
    with pd.ExcelWriter("tariff_analysis_TransContainer.xlsx") as writer:
        df_TransContainer.to_excel(writer, sheet_name="Raw Data", index=False)
    
    df_RusTrans = segments_to_df(parse_RusTrans(PATHS["RusTrans"]))
    with pd.ExcelWriter("tariff_analysis_RusTrans.xlsx") as writer:
        df_RusTrans.to_excel(writer, sheet_name="Raw Data", index=False)
'''