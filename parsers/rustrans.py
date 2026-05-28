# Парсер РусТранс Групп
import pandas as pd
from shared import port_dict, region_dict, get_country, container_size_dict, currency_dict, get_city_port,clean
from .models import TariffSegment


def parse_RusTrans(file_path: str):
    df = pd.read_excel(file_path, header=None)
    segments: list[TariffSegment] = []
    type_route = None
    pol_rail = None
    drop_off_list = []
    company = "РусТранс Групп"
    for id_row in range(len(df)):
        row = df.iloc[id_row].astype(str).tolist()
        if "Ставки Ж/Д" in row[1]:
            conditions_rail = row[1]
    for id_row in range(len(df)):
        row = df.iloc[id_row].astype(str).tolist()
        if str(row[1]) == "Морской фрахт":
            type_route = "sea"
            continue
        if "ВМРП" in str(row[1]) and "ЖД" in str(row[1]):
            type_route = "rail"
            pol_rail = "ВМРП"
            continue
        if "Врангель" in str(row[1]) and "ЖД" in str(row[1]):
            type_route = "rail"
            pol_rail = "Врангель"
            continue
        if type_route == "sea" and "drop" in row[3]:
            for id_sea_row in range(3, 12):
                if "drop" in row[id_sea_row]:
                    sp = row[id_sea_row].split("drop")
                    if sp[0].split()[0] == "20DC":
                        if '\\' in sp[1]:
                            for drop_off in sp[1].split('\\'):
                                drop_off_list.append({"type_container": "20DC", "weight_limit": container_size_dict.get("20DC", "24"), "destination": drop_off.strip(), "SOC/COC": "COC", "id_row": id_sea_row})
                        else:
                            for drop_off in sp[1].split('/'):
                                drop_off_list.append({"type_container": "20DC", "weight_limit": container_size_dict.get("20DC", "24"), "destination": drop_off.strip(), "SOC/COC": "COC", "id_row": id_sea_row})
                    elif sp[0].split()[0] == "40HC":
                        if '\\' in sp[1]:
                            for drop_off in sp[1].split('\\'):
                                drop_off_list.append({"type_container": "40HC", "weight_limit": container_size_dict.get("40HC", ""), "destination": drop_off.strip(), "SOC/COC": "COC", "id_row": id_sea_row})
                        else:
                            for drop_off in sp[1].split('/'):
                                drop_off_list.append({"type_container": "40HC", "weight_limit": container_size_dict.get("40HC", ""), "destination": drop_off.strip(), "SOC/COC": "COC", "id_row": id_sea_row})
                elif "COC" in row[id_sea_row]:
                    sp = row[id_sea_row].split()
                    drop_off_list.append({"type_container": "20DC", "weight_limit": container_size_dict.get("20DC", "24"), "destination": sp[4], "SOC/COC": "COC", "id_row": id_sea_row})
                elif "SOC" in row[id_sea_row]:
                    sp = row[id_sea_row].split()
                    drop_off_list.append({"type_container": sp[0], "weight_limit": container_size_dict.get(sp[0], ""), "destination": "All", "SOC/COC": "SOC", "id_row": id_sea_row})

        if type_route == "sea" and " - " in str(row[1]):
            route = row[1]
            pol = route.split(" - ")[0]
            pod = route.split(" - ")[1] + "/"
            for drop_off in drop_off_list:
                drop_dest = region_dict.get(drop_off['destination'], drop_off['destination'])
                pol_port = port_dict.get(pol, pol)
                cost = row[drop_off['id_row']].replace("$", '')

                # parent locations для порта
                pol_parent = get_city_port(pol_port) if get_city_port(pol_port) and get_city_port(pol_port) != pol_port else (pol_port.split()[0] if pol_port else None)

                for pod_item in pod.split("/"):
                    if pod_item:
                        pod_ = port_dict.get(pod_item, pod_item)
                        cost_ = cost if "/" not in cost else cost.split("/")[0] if drop_dest == "Владивосток" and drop_dest == pod_ else cost.split("/")[1] if drop_dest == pod_ else ''
                        if cost_:
                            segments.append(
                                TariffSegment(
                                    transport_type=type_route,
                                    start_point=f"{pol_port}, {get_country(pol_port)}",
                                    end_point=f"{pod_}, {get_country(get_city_port(pod_))}",
                                    container_type=drop_off["type_container"],
                                    weight_limit=drop_off.get("weight_limit"),
                                    min_weight_kg=None,
                                    max_weight_kg="24" if drop_off["type_container"] == "20DC" else "28",
                                    cost=cost_,
                                    currency=currency_dict.get("$", "$"),
                                    company=company,
                                    container_ownership=drop_off.get("SOC/COC"),
                                    port_service_term="FILO",
                                    end_location_type="port",
                                    start_location_type="port",
                                    parent_start_location=pol_parent,
                                    parent_start_location_type="city",
                                    parent_end_location=get_city_port(pod_),
                                    parent_end_location_type="city",
                                    dropoff_location=drop_dest if drop_dest != "All" else None,
                                    dropoff_location_type="city" if drop_dest != "All" else None,
                                    dropoff_location_country="Россия" if drop_dest != "All" else None,
                                )
                            )

        if "руб" in row[9] and type_route == "rail":
            security_20 = row[9].split("руб")[0].split("/")[0].strip().replace(" ", "")
            security_40 = row[9].split("руб")[0].split("/")[1].strip().replace(" ", "")
            pol_r = port_dict.get(pol_rail, pol_rail)

            # parent для ж/д
            pol_rail_city = get_city_port(pol_r) if get_city_port(pol_r) else "Владивосток"

            for id_rail_row in range(6, 9):
                stations = row[2].split(",")
                for station in stations:
                    station = station.strip()
                    segments.append(
                        TariffSegment(
                            transport_type=type_route,
                            start_point=f"{pol_r}, {get_country(get_city_port(pol_r))}",
                            end_point=f"{station}, {get_country(row[1])}",
                            container_type="20DC" if id_rail_row == 6 or id_rail_row == 7 else "40HC",
                            weight_limit="24" if id_rail_row == 6 else "28",
                            min_weight_kg="24" if id_rail_row == 7 else None,
                            max_weight_kg="24" if id_rail_row == 6 else "28",
                            cost=row[id_rail_row],
                            currency=currency_dict.get("руб", "руб"),
                            company=company,
                            conditions=(
                                f"Охрана: {security_20}. {conditions_rail}"
                                if id_rail_row == 6 or id_rail_row == 7
                                else f"Охрана: {security_40}. {conditions_rail}"
                            )
                            + f" Станция назначения: {station}",
                            container_ownership="COC",
                            end_location_type="rail_station",
                            start_location_type="port",
                            parent_start_location=pol_rail_city,
                            parent_start_location_type="city",
                            parent_end_location=row[1],
                            parent_end_location_type="city"
                        )
                    )
    return segments


def parse_RusTrans_all_tranc(file_path: str):
    df = pd.read_excel(file_path, header=None)
    result = []
    type_route = None
    pol = None
    drop_off_list = []
    company = "РусТранс Групп"
    for i in range(len(df)):
        row = df.iloc[i].astype(str).tolist()
        if str(row[1]) == "Морской фрахт":
            type_route = "Морской фрахт"
            continue
        if "ВМРП" in str(row[1]) and "ЖД" in str(row[1]):
            type_route = "ЖД ВМРП"
            pol = "ВМРП"
            continue
        if "Врангель" in str(row[1]) and "ЖД" in str(row[1]):
            type_route = "ЖД Врангель"
            pol = "Врангель"
            continue
        if type_route == "Морской фрахт" and "drop" in row[3]:
            for i in range(3, 12):
                if "drop" in row[i]:
                    sp = row[i].split("drop")
                    if sp[0].split()[0] == "20DC":
                        if '\\' in sp[1]:
                            for drop_off in sp[1].split('\\'):
                                drop_off_list.append({"type_container": "20DC", "size": container_size_dict.get("20DC", "до 24т"), "destination": drop_off.strip(), "SOC/COC": "COC", "id_row": i})
                        else:
                            for drop_off in sp[1].split('/'):
                                drop_off_list.append({"type_container": "20DC", "size": container_size_dict.get("20DC", "до 24т"), "destination": drop_off.strip(), "SOC/COC": "COC", "id_row": i})
                    elif sp[0].split()[0] == "40HC":
                        if '\\' in sp[1]:
                            for drop_off in sp[1].split('\\'):
                                drop_off_list.append({"type_container": "40HC", "size": container_size_dict.get("40HC", ""), "destination": drop_off.strip(), "SOC/COC": "COC", "id_row": i})
                        else:
                            for drop_off in sp[1].split('/'):
                                drop_off_list.append({"type_container": "40HC", "size": container_size_dict.get("40HC", ""), "destination": drop_off.strip(), "SOC/COC": "COC", "id_row": i})
                elif "COC" in row[i]:
                    sp = row[i].split()
                    drop_off_list.append({"type_container": "20DC", "size": container_size_dict.get("20DC", "до 24т"), "destination": sp[4], "SOC/COC": "COC", "id_row": i})
                elif "SOC" in row[i]:
                    sp = row[i].split()
                    drop_off_list.append({"type_container": sp[0], "size": container_size_dict.get(sp[0], ""), "destination": None, "SOC/COC": "SOC", "id_row": i})

        if type_route == "Морской фрахт" and " - " in str(row[1]):
            route = row[1]
            pol = route.split(" - ")[0]
            pod = route.split(" - ")[1]
            for drop_off in drop_off_list:
                if "/" in pod:
                    for pod_item in pod.split("/"):
                        result.append({
                            "type_route": type_route, "pol": pol, "pod": pod_item,
                            "destination": region_dict.get(drop_off['destination'], drop_off['destination']),
                            "container": drop_off['type_container'], "size": drop_off.get('size'),
                            "tarif": row[drop_off['id_row']], "security": None, "currency": "$", "SOC/COC": drop_off['SOC/COC']
                        })
                else:
                    result.append({
                        "type_route": type_route, "pol": pol, "pod": pod,
                        "destination": region_dict.get(drop_off['destination'], drop_off['destination']),
                        "container": drop_off['type_container'], "size": drop_off.get('size'),
                        "tarif": row[drop_off['id_row']], "security": None, "currency": "$", "SOC/COC": drop_off['SOC/COC']
                    })

        if "руб" in row[9] and "ЖД" in type_route:
            for i in range(6, 9):
                result.append({
                    "type_route": type_route, "pol": pol, "pod": row[1],
                    "destination": region_dict.get(row[1], row[1]),
                    "container": "20DC" if i == 6 or i == 7 else "40HC",
                    "size": "до 24т" if i == 6 else "до 28т",
                    "tarif": row[i], "security": row[9].split("руб")[0], "currency": "руб",
                    "SOC/COC": "COC"
                })
    segments: list[TariffSegment] = []
    for item in result:
        type_route = str(item.get("type_route", ""))
        transport_type = "sea" if "Морской" in type_route else ("rail" if "ЖД" in type_route else "")

        pol_raw = str(item.get("pol", "")).strip()
        pod_raw = str(item.get("pod", "")).strip()
        pol_port = port_dict.get(pol_raw, pol_raw)
        pod_port = port_dict.get(pod_raw, pod_raw)

        destination_raw = str(item.get("destination", "")).strip()
        final_destination = destination_raw
        if destination_raw and "," not in destination_raw:
            country = get_country(destination_raw)
            if country:
                final_destination = f"{destination_raw}, {country}"

        size_raw = str(item.get("size", "")).strip()
        m = re.search(r"(\\d+)", size_raw)
        weight_limit = m.group(1) if m else container_size_dict.get(str(item.get("container", "")).strip(), None)

        currency_raw = str(item.get("currency", "")).strip()
        currency = currency_dict.get(currency_raw, currency_raw)

        soc_coc = str(item.get("SOC/COC", "")).strip()
        conditions = f"FI-LO {soc_coc}".strip() if transport_type == "sea" else ""
        security = item.get("security")
        if security:
            conditions = f"Охрана: {security}. {conditions}".strip()

        segments.append(
            TariffSegment(
                transport_type=transport_type,
                start_point=f"{pol_port}, {get_country(pol_port)}" if pol_port else "",
                end_point=f"{pod_port}, {get_country(pod_port)}" if pod_port else "",
                final_destination=final_destination,
                container_type=str(item.get("container", "")).strip(),
                weight_limit=weight_limit,
                cost=item.get("tarif"),
                currency=currency,
                departure_dates={},
                company=company,
                conditions=conditions,
                departures=None,
                container_ownership=soc_coc or None,
                port_service_term="FILO" if transport_type == "sea" else None,
                final_destination_location_type=None,
                end_location_type=None,
                start_location_type=None,
                parent_start_location=None,
                parent_start_location_type=None,
                parent_end_location=None,
                parent_end_location_type=None,
                parent_final_destination_location=None,
                parent_final_destination_location_type=None,
                stopovers_location=None,
                stopovers_location_type=None,
                stopovers_location_country=None,
                sequence=0,
            )
        )
    return segments


# _segments_wrapper_for_parse_RusTrans
from .models import TariffSegment
from .utils import to_segments as _to_segments

_parse_RusTrans_impl = parse_RusTrans

def parse(*args, **kwargs) -> list[TariffSegment]:
    return _to_segments(_parse_RusTrans_impl(*args, **kwargs))
