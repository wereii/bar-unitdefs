"""
unitdefs-reshaper.py

Reprocesses unitdefs export from Beyond All Reason into more usable format.
Mainly it focuses on:
- Extracting data that is important statistic of a unit (build power for builders, metal production for mexes, ...)
- Removing engine specific information (sounds, models locations, ...)
"""

import json
import logging
import argparse
import pathlib
from functools import partial
from typing import Callable

logger = logging.getLogger("unitdefs-reshaper")

# ---- Definitions

# NOTE: Does not handle armscavenger properly
FACTION_PREFIX_MAPPER = {
    "arm": "armada",
    "cor": "cortex",
    "leg": "legion",
    "raptor": "raptor",
    "scav": "scavenger",
}


class JsonCallableEncoder(json.JSONEncoder):
    """Json encoder that realizes any callables before serialization."""

    def default(self, obj):
        o = obj
        if callable(obj):
            try:
                o = obj()
            except Exception as e:
                raise TypeError from e
        return super().default(o)


class IdResolver:
    """Resolve engine IDs to data"""
    mapper: dict[int, any]

    def __init__(self):
        self.mapper = {}

    def register_id(self, id_: int, data: any):
        self.mapper[id_] = data

    def resolve_id(self, id_: int) -> any:
        return self.mapper[id_]

    def lazy_resolve_id(self, id_: int) -> Callable[[], any]:
        return partial(self.resolve_id, id_)


_default_sentinel = object()


def _copy_key(key: any, *, source: dict, target: dict, default: any = _default_sentinel):
    if default != _default_sentinel:
        target[key] = source.get(key, default)
    else:
        target[key] = source[key]


# ---- Implementations


def process_unitdefs(unitdefs_dir: pathlib.Path) -> list:
    id_name_resolver = IdResolver()
    weapon_def_resolver = IdResolver()

    output = list()

    for unitdef_path in unitdefs_dir.iterdir():
        if not unitdef_path.is_file() and unitdef_path.suffix != ".json":
            logger.debug(f"Skipping {unitdef_path}")
            continue

        logger.debug(f"Processing {unitdef_path.name}")
        with open(unitdef_path, "r") as fd:
            unitdef_data_raw = json.load(fd)

        unit_dict = dict()
        engine_unit_name = unitdef_data_raw["name"]

        # "Cache" ids for later resolution
        id_name_resolver.register_id(unitdef_data_raw["id"], engine_unit_name)
        if "wDefs" in unitdef_data_raw:
            process_weapon_defs(unitdef_data_raw["wDefs"], weapon_def_resolver)

        extract_generic(unitdef_data_raw, unit_dict)
        extract_unit_type(unitdef_data_raw, unit_dict)
        extract_unit_kind(unitdef_data_raw, unit_dict)
        extract_tech_level(unitdef_data_raw, unit_dict)
        extract_features(unitdef_data_raw, unit_dict)

        logger.debug(f"{engine_unit_name} - extracted generic fields")

        output.append(unit_dict)

    return output


def process_weapon_defs(wdefs_list: list[dict], wdef_resolver: IdResolver):
    for definition in wdefs_list:
        if not definition:
            continue
        wdef_resolver.register_id(definition["id"], definition)


def extract_generic(unitdef_data: dict, result_data: dict):
    """Extract generic fields like translatedHumanName, hp, costs, ..."""

    result_data["humanName"] = unitdef_data["translatedHumanName"]
    result_data["humanTooltip"] = unitdef_data["translatedTooltip"]

    _copy_key("name", source=unitdef_data, target=result_data)
    _copy_key("health", source=unitdef_data, target=result_data)
    _copy_key("metalCost", source=unitdef_data, target=result_data)
    _copy_key("energyCost", source=unitdef_data, target=result_data)
    _copy_key("buildTime", source=unitdef_data, target=result_data)

    _copy_key("metalStorage", source=unitdef_data, target=result_data)
    _copy_key("energyStorage", source=unitdef_data, target=result_data)

    result_data["los"] = unitdef_data.get("sightDistance", 0)
    result_data["losAir"] = unitdef_data.get("airSightDistance", 0)

    # there is also radarRange key but not all units, that have radarRadius, have radarRange (armaap)
    result_data["radarRange"] = unitdef_data.get("radarRadius", 0)

    result_data["unitgroup"] = unitdef_data["customParams"].get("unitgroup")

    faction = None
    # Exception, scavboss
    if unitdef_data["name"].startswith("armscavenger"):
        faction = "scavenger"
    # Exception, scavboss
    elif unitdef_data["name"] == "corvacct":
        faction = "scavenger"
    else:
        for prefix, faction_name in FACTION_PREFIX_MAPPER.items():
            if unitdef_data["name"].startswith(prefix):
                faction = faction_name

    result_data["faction"] = faction


def extract_unit_type(unitdef_data: dict, result_data: dict):
    """Extract unit type [unit | building]"""

    if unitdef_data["isBuilding"]:
        result_data["type"] = "building"
    else:
        result_data["type"] = "unit"


def extract_tech_level(unitdef_data: dict, result_data: dict):
    result_data["techLevel"] = unitdef_data["customParams"].get("techlevel")


def extract_unit_kind(unitdef_data: dict, result_data: dict):
    """Extract unit kind [ bot | veh | air | sub | hov | ...? ]"""
    # TODO
    kind = None

    # TODO: Lot of assumptions here, raptors have their of category?

    if unitdef_data["isBuilding"]:
        kind = "building"
        if unitdef_data["isFactory"]:
            kind = "factory"
        elif unitdef_data["isExtractor"]:
            kind = "extractor"
            _copy_key("extractsMetal", source=unitdef_data, target=result_data)
        elif unitdef_data["customParams"].get("solar"):
            kind = "solargen"
            if unitdef_data["energyUpkeep"] < 0:
                # T1 solar
                unitdef_data["energyMake"] = abs(unitdef_data["energyUpkeep"])
            else:
                # T2
                unitdef_data["energyMake"] = unitdef_data["energyMake"] or unitdef_data["totalEnergyOut"]
        elif unitdef_data["windGenerator"]:
            kind = "windgen"
            _copy_key("energymultiplier", source=unitdef_data["customParams"], target=result_data)
        elif unitdef_data["tidalGenerator"]:
            kind = "tidalgen"
        elif unitdef_data["isStaticBuilder"]:
            kind = "static_builder"
        elif unitdef_data["energyStorage"] > 0 or unitdef_data["metalStorage"] > 0:
            kind = "storage"
        elif unitdef_data["modCategories"].get("weapon"):
            kind = "defense"

    elif unitdef_data["isAirUnit"]:
        kind = "air"
        # TODO: sub-kind vtol
    elif unitdef_data["isGroundUnit"]:
        categories = unitdef_data["modCategories"]
        if categories.get("space"):
            kind = "space"
        elif categories.get("commander"):
            kind = "commander"
        elif categories.get("bot"):
            kind = "bot"
        elif categories.get("tank"):
            kind = "vehicle"
        elif categories.get("hover"):
            kind = "hover"
        elif categories.get("underwater"):
            kind = "sub"
        elif categories.get("ship"):
            kind = "ship"
        elif unitdef_data["isImmobile"]:
            print(f"\n{unitdef_data['name']}\n")
            if unitdef_data["hasShield"]:
                kind = "shield"
            else:
                kind = "immobile"
        elif unitdef_data["deathExplosion"] == "decoycommander":
            # TODO: Arbitrary check
            kind = "decoycommander"
        elif categories.get("object"):
            kind = "object"
        else:
            logger.warning("Unknown unit kind: %s", unitdef_data["name"])

    result_data["unit_kind"] = kind


def extract_features(unitdef_data: dict, result_data: dict):
    features = dict()
    categories = unitdef_data["modCategories"]

    if categories.get("empable"):
        features["empable"] = True

    if categories.get("vtol"):
        features["vtol"] = True

    if unitdef_data["canSelfDestruct"] or unitdef_data["canSelfD"]:
        features["selfd"] = True

    if unitdef_data["canKamikaze"]:
        features["kamikaze"] = True

    if unitdef_data["canCloak"]:
        features["cloak"] = True

    if unitdef_data["isTransport"]:
        features["transport"] = True

    if unitdef_data["capturable"]:
        features["capturable"] = True

    if unitdef_data["canCapture"]:
        features["can_capture"] = True

    if unitdef_data["canResurrect"]:
        features["can_resurrect"] = True

    if unitdef_data["canRepair"]:
        features["can_repair"] = True

    if features:
        result_data["features"] = features
    else:
        result_data["features"] = None


# ----


arg_parser = argparse.ArgumentParser(prog="unitdefs-reshaper")

arg_parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging")
arg_parser.add_argument("--dry-run", "-n", action="store_true", help="Run without writing anything")

arg_parser.add_argument(
    "--unitdefs-dir",
    required=True,
    help='Location of exported json unitdefs (usually "json_export/")',
    type=pathlib.Path,
)

arg_parser.add_argument(
    "--output-file",
    help='Path to directory where to output files, defaults to "./unitdefs.json"',
    default=pathlib.Path("./unitdefs.json").resolve(),
    type=pathlib.Path,
)


def main():
    args = arg_parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    try:
        unitdefs_dir: pathlib.Path = args.unitdefs_dir.resolve(strict=True)
    except FileNotFoundError:
        logger.error(f"Could not find unitdefs directory '{args.unitdefs_dir}', does it exist?")
        exit(1)

    output_file: pathlib.Path = args.output_file

    processed = process_unitdefs(unitdefs_dir)
    logger.debug("Processed raw unitdefs")

    if not args.dry_run:
        logger.info(f"Writing unitdefs to file {output_file}")
        with open(output_file, "w") as out_fp:
            json.dump(processed, out_fp, cls=JsonCallableEncoder)
    else:
        logger.info("Dry run, not writing anything")


if __name__ == "__main__":
    main()
