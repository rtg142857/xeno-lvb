#  MIT License
#  
#  Copyright (c) 2026 rtg142857
#  
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#  
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#  
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.

# Dependencies: xeno_lvb.py from https://github.com/roccodev/xeno-lvb (but modify Info.to_json to remove the <>, and modify Default.to_json to always return the bytes)
# The below libraries
# A dumped version of (your own copy of) Xenoblade 3's data, with all 4 DLCs
from __future__ import annotations # deprecated if using python 3.14+
from xeno_lvb import Lvb
import json
from pathlib import Path
import numpy as np
from shapely import Polygon, unary_union
import pandas as pd

from json import JSONEncoder
def _default(self, obj):
    return getattr(obj.__class__, "to_json", _default.default)(obj)
_default.default = JSONEncoder().default
JSONEncoder.default = _default
JSON_INCL_BYTES = True

class LocationComponent():
    """
    Represents the data of a single entry with LOCA magic
    (with all the associated CNTP).
    """
    def __init__(self, loca_entry: dict, cntp_data: list, cntp_entries=None):
        """
        Takes in a single LOCA entry and the full list of CNTP entries.
        Alternatively, takes in a pre-selected list of CNTP etnries as "cntp_entries" (in which case it ignores the full list).

        Initialises self.LOCA, self.bdat_id, self.CNTP, self.lb, self.ub, and self.polygon.
        """
        self.LOCA = loca_entry
        self.bdat_id = get_from_entry(loca_entry, "bdat_id")

        self.CNTP = []
        cntp_first_idx, cntp_last_idx = get_cntp_indices_from_loca(loca_entry)

        cntp_list = np.zeros(shape=(0, 2))
        lb = np.inf

        if cntp_entries == None:
            cntp_entries = cntp_data[cntp_first_idx:cntp_last_idx]
        for cntp_entry in cntp_entries:
            self.CNTP.append(cntp_entry)

            xform = get_from_entry(cntp_entry, "xform")
            xz = np.array([[xform[0], xform[2]]])
            cntp_list = np.append(cntp_list, xz, axis=0)

            y = xform[1]
            lb = min(y, lb)
        
        self.lb = lb
        yScl = get_from_entry(loca_entry, "xform")[13]
        self.ub = lb + yScl

        self.polygon = Polygon(cntp_list)

class Location():
    """
    Represents the data for a set of LocationComponents all corresponding to the same maXXa_GMK_Location entry.
    """
    def __init__(self, component_list: list[LocationComponent]):
        """
        Takes in a (nonempty) list of LocationComponents. Mostly just used for being a list of components,
        but it does store the polygon (union of component polygons) and does some asserts for safety.

        Initialises self.bdat_id, self.components, self.polygon, self.lb, self.ub.
        The latter two are the extrema across all components.
        """
        component_bdat_ids = set([component.bdat_id for component in component_list])
        component_lbs = [component.lb for component in component_list]
        component_ubs = [component.ub for component in component_list]
        self.lb = min(component_lbs)
        self.ub = max(component_ubs)

        assert len(component_bdat_ids) == 1 # must be at least one component, and all of them must have the same value

        self.bdat_id = component_list[0].bdat_id
        self.components = component_list

        component_polygons = [component.polygon for component in component_list]
        self.polygon = unary_union(component_polygons)
        
    def append_component(self, component: LocationComponent):
        """
        Adds a new LocationComponent to the location. Component must have the same bdat_id (and ub/lb?) as the preexisting ones.
        """
        assert component.bdat_id == self.bdat_id

        self.lb = min(self.lb, component.lb)
        self.ub = max(self.ub, component.ub)
        self.components.append(component)
        self.polygon = component.polygon.union(self.polygon)

class Place():
    """
    Represents the data for a location and all its sublocations.
    Sublocations are also represented by Places.
    """
    def __init__(self, location: Location, subplaces: list[Place]=[]) -> None:
        """
        Takes in a Location and, optionally, a list of Places to be the sublocations.
        Initialises self.bdat_id, self.data, self.places.
        """
        self.bdat_id = location.bdat_id
        self.data = location
        self.places = subplaces
    
    def insert_subplace_directly(self, subplace: Place):
        """
        Inserts a Place directly to self's list of subplaces
        """
        self.places.append(subplace)
    
    def remove_subplaces(self, subplace_indices_to_remove: list):
        self.places = [place for i, place in enumerate(self.places) if not subplace_indices_to_remove[i]]

    def insert_location_not_as_sublocation(self, location: Location):
        """
        Converts a location to a place and inserts it directly to self's list of subplaces.
        If anything in the current list of places is a sublocation, removes them from the current list
        and puts them in the location's list of subplaces instead.

        ASSUMES! that the location is not a *sub*place to anything in the list of places!
        """
        subplaces_of_location = []
        indices_to_remove = [False] * len(self.places)
        for i, place in enumerate(self.places):
            if location_a_contains_b(location, place.data):
                indices_to_remove[i] = True
                subplaces_of_location.append(place)

        self.remove_subplaces(indices_to_remove)
        new_place = Place(location, subplaces_of_location)
        self.insert_subplace_directly(new_place)

    def insert_location_recursive(self, location: Location):
        """
        Makes a location into a place and inserts it where it should go in the list of subplaces.
        If any current subplaces are a sublocation to it, removes them from the list and adds them as the location's list of subplaces.
        If the location is a sublocation to any places, puts them in their list of subplaces instead.
        """
        # check if sublocation to anything in the list
        # if so, sublocation handling
            # get list of places that the location is a sublocation of
            # put the location in those places (recursive step)
        # if not, (super)location handling
            # get list of places in the place tree that are sublocations of the location
            # pop them from the place list, and put them as places in the location
            # Then put the location in the place list
        order_status = "None"
        for place in self.places:
            place_data = place.data
            if location_a_contains_b(place_data, location):
                assert order_status != "super" # place cannot be a superlocation of one and a sublocation of another on the same level; otherwise the sublocation would be a sub of the superlocation
                order_status = "sub"
            elif location_a_contains_b(location, place_data):
                assert order_status != "sub"
                order_status = "super"

        if order_status == "sub":
            # Recursive step: location is a sublocation of at least one place in the list; add it there instead
            for place in self.places:
                if location_a_contains_b(place.data, location):
                    place.insert_location_recursive(location)
        else: # location is not a sublocation of anything, so it should be added to the list directly, and move current places to its place list if they're sublocations as necessary
            self.insert_location_not_as_sublocation(location)

    def to_json(self):
        if self.places == []:
            return {"bdat_id": convert_hashid_to_name(self.bdat_id, gmk_location, location_names) }
        else:
            return {
                "bdat_id": convert_hashid_to_name(self.bdat_id, gmk_location, location_names), # for debugging; TODO: remove
                "places": self.places
            }

def get_lvb_filename(unpack_xbtool_path: Path, dlc: str, region: str) -> Path:
    """
    Takes in a Path representing the path to the unpack_xbtool folder with the XC3 data,
    and a string representing a dlc: "base", "dlc01", "dlc02", "dlc03", "dlc04",
    and a region ID (e.g. ma01a).
    Returns the path to the .lvb file for that dlc and that region ID.
    """
    if dlc == "base":
        full_path = unpack_xbtool_path / "gmk_r" / region / f"{region}.lvb"
        return full_path
    else:
        dlc_without_zero = "dlc"+dlc[-1]
        full_path = unpack_xbtool_path / dlc_without_zero / "gmk_r" / region / f"{region}_{dlc}.lvb"
        return full_path

def read_lvb_file(path: Path) -> dict:
    """
    Takes in a Path argument: the path to a .lvb file.
    Reads in the .lvb file and returns the lvb file as a dictionary.
    If no file exists at that location, return None.
    """
    try:
        file = open(path, "rb")
        data = list(file.read())
        file.close()
    except FileNotFoundError:
        return None
    lvb = Lvb(data)
    lvb = json.loads(json.dumps(lvb, ensure_ascii=False)) # converting to dict
    return lvb

def get_lvb_data(region: str, unpack_xbtool_path: Path, verbose=False) -> dict:
    """
    Takes in a string argument representing a region ID (e.g. ma01a),
    and a path to the unpack_xbtool folder with the XC3 data.
    Returns a dict of gimmick data.
    Keys are "base", "dlc01", "dlc02", "dlc03", "dlc04".
    Values are dictionaries of the lvb data as returned by read_lvb_file.
    """
    lvb_dict = {}
    for dlc in ["base", "dlc01", "dlc02", "dlc03", "dlc04"]:
        filename = get_lvb_filename(unpack_xbtool_path, dlc, region)
        if verbose:
            print(f"Loading file: {filename}")
        lvb_data = read_lvb_file(filename)
        if lvb_data != None:
            lvb_dict[dlc] = lvb_data

    assert lvb_dict != {}, "No lvb files found. Is the upack_xbtool_path correct?"
    return lvb_dict

def get_lvb_entries(lvb_data_given_dlc: dict, magic: str) -> list:
    """
    Takes in a dictionary of lvb data as returned by read_lvb_file,
    and a "magic" field.
    Returns a list representing the entries of the lvb with that magic.
    If there are no sections with that magic, print so and return an empty list.
    """
    for section in lvb_data_given_dlc["sections"]:
        if section["magic"] == magic:
            return section["entries"]
    print(f"Lvb data for this DLC has no magic {magic}")
    return []

def get_from_entry(entry: dict, field: str) -> str | list | int:
    """
    Takes in an entry from the lvb files,
    and a str representing a field to return.
    Currently supports the following fields:
    * "bdat_id" (str)
    * "shape" (int)
    * "xform" (list of floats)
    * "bytes" (str)
    """
    match field:
        case "bdat_id":
            return entry["info"]["bdat_id"]
        case "shape":
            return entry["info"]["shape"]
        case "xform":
            return entry["xform"]
        case "bytes":
            return entry["bytes"]
        
def get_cntp_indices_from_loca(loca_entry: dict) -> tuple[int, int]:
    """
    Takes in a dict representing a loca entry from an lvb file.
    Returns a tuple: the starting and ending index of the corresponding CNTP entries.
    """
    bytes = get_from_entry(loca_entry, "bytes")
    last_high = bytes[-2:]
    last_low = bytes[-4:-2]
    first_high = bytes[-6:-4]
    first_low = bytes[-8:-6]
    return int(first_high+first_low, 16), int(last_high+last_low, 16)

def get_location_data(lvb_dict: dict, verbose=False) -> list[Location]:
    """
    Takes in an lvb dict of a region as given by get_lvb_data.
    Returns a list of Locations in that region.
    """
    location_dict = {}
    for dlc in lvb_dict.keys():
        if verbose:
            print(f"Converting location data for DLC {dlc}")
        loca_data = get_lvb_entries(lvb_dict[dlc], "LOCA")
        cntp_data = get_lvb_entries(lvb_dict[dlc], "CNTP")
        for loca_entry in loca_data:
            component = LocationComponent(loca_entry, cntp_data)
            bdat_id = component.bdat_id
            if bdat_id not in location_dict.keys():
                location_dict[bdat_id] = [component]
            else:
                location_dict[bdat_id].append(component)
    
    location_list = []
    for bdat_id in location_dict.keys():
        location = Location(location_dict[bdat_id])
        location_list.append(location)
    return location_list

def initialise_region(region: str) -> Location:
    """
    Takes in a region ID, purely for naming.
    Makes a "root" Location in the style of get_location_data to represent an entire region.
    Basically a cube 2e6 to a side, centred on the origin, with dummy other data.

    if ur reading this, ligma balls
    """
    LOCA = {"info": {"bdat_id": region}, "xform": [0,0,0,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,2e6,0,0], "bytes": "00000000"}
    CNTP = [
        {"info": {"bdat_id": region}, "xform": [1e6,-1e6,1e6,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,2e6,0,0], "bytes": "00000000"},
        {"info": {"bdat_id": region}, "xform": [-1e6,-1e6,1e6,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,2e6,0,0], "bytes": "00000000"},
        {"info": {"bdat_id": region}, "xform": [-1e6,-1e6,-1e6,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,2e6,0,0], "bytes": "00000000"},
        {"info": {"bdat_id": region}, "xform": [1e6,-1e6,-1e6,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,2e6,0,0], "bytes": "00000000"},
    ]
    location_component = LocationComponent(LOCA, [], cntp_entries=CNTP)
    location = Location([location_component])
    return location

def location_a_contains_b(location_a: Location, location_b: Location) -> bool:
    """
    Takes in two Locations. # (with structure like an entry in get_location_data)
    Returns True if the second location is entirely contained within the first, and False otherwise.

    For the vertical axis, we only check if the midpoint of the second is contained within the first (there are some locations that are obviously "contained" but where the second actually extends a bit above the first).
    """
    b_avg_y = (location_b.lb + location_b.ub) / 2
    if b_avg_y > location_a.ub or b_avg_y < location_a.lb:
        return False
    
    return location_a.polygon.contains(location_b.polygon)

def create_place_tree(lvb_dict: dict, region: str, verbose=False) -> Place:
    """
    Takes in the lvb data of a region as given by get_lvb_data,
    and a region ID (e.g. ma01a).
    Returns a tree-style dict structure, where each node corresponds to a location(/landmark/area/etc).
    Each node is a Place, which can have other places as subnodes.
    """
    if verbose:
        print("Initialising region...")
    place_tree = Place(initialise_region(region))

    if verbose:
        print("Converting lvb data to Locations...")
    location_data = get_location_data(lvb_dict, verbose)

    if verbose:
        num = len(location_data)
        print(f"Adding {num} locations to the tree...")
    
    for i, location in enumerate(location_data):

        if verbose:
            bdat_id = location.bdat_id
            print(f"{i+1}/{num}: {bdat_id}")

        place_tree.insert_location_recursive(location)

    return place_tree

def get_bdat(path: Path) -> pd.DataFrame:
    bdat = pd.read_csv(path, dtype="string", na_filter=False, sep="\t", comment="\t")
    bdat = bdat.set_index("ID", drop=False)
    return bdat

def get_location_bdats(gmk_location_path: Path, location_names_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    return get_bdat(gmk_location_path), get_bdat(location_names_path)

def convert_hashid_to_name(bdat_id: str, gmk_location: pd.DataFrame, location_names: pd.DataFrame) -> str:
    name_id = None
    for row in gmk_location.index.values.tolist():
        if gmk_location.loc[row, "hashID"] == bdat_id:
            name_id = gmk_location.loc[row, "LocationName"]
    if name_id in [None, "0"]:
        return bdat_id
    return location_names.loc[name_id, "name"]

region = "ma40a"
unpack_xbtool_path = Path("C:/Users/rtg14/Desktop/Not_work/My_Programs/XC3_files_2.2.0/unpack_xbtool")

print("Getting lvb data...")
lvb_data = get_lvb_data(region, unpack_xbtool_path, verbose=True)

print("Creating place tree...")
place_tree = create_place_tree(lvb_data, region, verbose=True)

print("Writing to file...")
gmk_location_path = Path(f"C:/Users/rtg14/Desktop/Not_work/My_Programs/wiki_bdat_processing/XC3_colonies/bdats/{region}_GMK_Location.tsv")
location_names_path = Path(f"C:/Users/rtg14/Desktop/Not_work/My_Programs/wiki_bdat_processing/XC3_colonies/bdats/msg_location_name_en.tsv")
gmk_location, location_names = get_location_bdats(gmk_location_path, location_names_path)

outpath = Path(f"C:/Users/rtg14/Desktop/Not_work/My_Programs/xeno-lvb/output/{region}_tree.json")
outfile = open(outpath, "w+", encoding="utf-8-sig")
outfile.write(json.dumps(place_tree, indent=1))
outfile.close()