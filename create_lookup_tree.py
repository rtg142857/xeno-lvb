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

# Dependencies: xeno_lvb.py
# The below libraries
# A dumped version of (your own copy of) Xenoblade 3's data, with all 4 DLCs
from __future__ import annotations # deprecated if using python 3.14+
from xeno_lvb import Lvb
import json
from pathlib import Path
import numpy as np
from shapely import Polygon, unary_union, Point
import pandas as pd
import sys

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

    Has self.bdat_id, self.components, self.polygon, self.lb, self.ub.
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
        Adds a new LocationComponent to the location. Component must have the same bdat_id as the preexisting ones.
        """
        assert component.bdat_id == self.bdat_id

        self.lb = min(self.lb, component.lb)
        self.ub = max(self.ub, component.ub)
        self.components.append(component)
        self.polygon = component.polygon.union(self.polygon)

class RestSpot():
    """
    Represents the data for a Rest Spot. Has self.COMU, self.bdat_id, self.polygon, self.lb, and self.ub.

    If the shape is 2 (a sphere), functionally defines the polygon as a vertical 32-gonal prism.
    If it's 3 (a cuboid), it's a cuboid.
    """
    def __init__(self, comu_entry: dict):
        self.COMU = comu_entry
        self.bdat_id = get_from_entry(comu_entry, "bdat_id")

        shape = get_from_entry(comu_entry, "shape")
        xform = get_from_entry(comu_entry, "xform")

        match shape:
            case 2: # sphere
                centre_y = xform[1]
                xScl = xform[12] # we assert it's a sphere, so applies to all 3 directions; xScl represents the diameter
                self.lb = centre_y - xScl/2
                self.ub = centre_y + xScl/2

                centre_xz = [xform[0], xform[2]]
                self.polygon = Point(centre_xz).buffer(xScl/2) # technically a 32-gon

            case 3: # cuboid
                centre_y = xform[1]
                yScl = xform[13]
                self.lb = centre_y - yScl/2
                self.ub = centre_y + yScl/2

                #centre_xy = [xform[0], xform[2]]
                xScl = xform[12]
                zScl = xform[14]
                points = [[xform[0] + xScl/2, xform[2] + zScl/2],
                          [xform[0] - xScl/2, xform[2] + zScl/2],
                          [xform[0] - xScl/2, xform[2] - zScl/2],
                          [xform[0] + xScl/2, xform[2] - zScl/2]]
                self.polygon = Polygon(points)
            case _:
                raise AssertionError

class Coordinate():
    """
    A point in 3D space (shapely Points are only in 2d)
    """
    def __init__(self, x: float, y: float, z: float):
        """
        Initiates self.point, self.y, self.x, self.z
        """
        self.x = x
        self.y = y
        self.z = z
        self.point = Point([x, z])

def get_coord_from_entry(lvb_entry: dict) -> Coordinate:
    """
    Takes in an lvb entry. Gets its Coordinate.
    """
    xform = get_from_entry(lvb_entry, "xform")
    return Coordinate(xform[0], xform[1], xform[2])

class PointOfInterest():
    """
    General class for objects which exist at a specific point.
    Used for non-location entities: NPCs, enemy spawnpoints, ...

    Location is stored in "coordinates", a list of Coordinate objects, each of which have Coordinate.y and Coordinate.point values for height and xz respectively
    """
    def __init__(self, lvb_entry: dict, lvb_data: dict, magic: str):
        """
        Takes in an lvb entry, the entire lvb dict FOR THE ENTRY'S DLC (just in case it's needed to get the points), and the magic

        Initialises self.bdat_id, self.magic, self.coordinates
        """
        if magic == "NPC ":
            magic = "NPC"
        self.magic = magic
        self.bdat_id = get_from_entry(lvb_entry, "bdat_id")

        match magic:
            case "TBOX" | "PREC" | "RBOX" | "ETHP" | "ARCH" | "ENSP" | "EAFF" | "ENFO" | "KIEV":
                # single point
                self.coordinates = [get_coord_from_entry(lvb_entry)]
            case "ENMY":
                # either single point, or get points from the ENEL entries, which are gotten from the ENEM entries
                enem_idx = get_enem_idx(lvb_entry)
                if hex(enem_idx) == "0xffff":
                    self.coordinates = [get_coord_from_entry(lvb_entry)]
                else:
                    enem_data = get_lvb_entries(lvb_data, "ENEM")
                    enel_start, enel_end = get_enel_idxs(enem_data[enem_idx])

                    enel_data = get_lvb_entries(lvb_data, "ENEL")
                    self.coordinates = []
                    for enel_idx in range(enel_start, enel_end):
                        self.coordinates.append(get_coord_from_entry(enel_data[enel_idx]))
            case "NPC":
                # get range of NPCS entries, each of which has a range of NPCL entries
                npcs_start, npcs_end = get_npcs_idxs(lvb_entry)
                
                npcs_data = get_lvb_entries(lvb_data, "NPCS")
                npcl_data = get_lvb_entries(lvb_data, "NPCL")
                self.coordinates = []
                for npcs_idx in range(npcs_start, npcs_end):
                    npcl_start, npcl_end = get_npcl_idxs(npcs_data[npcs_idx])
                    if npcs_single_locator(npcs_data[npcs_idx]):
                        npcl_end = npcl_start + 1
                    for npcl_idx in range(npcl_start, npcl_end):
                        self.coordinates.append(get_coord_from_entry(npcl_data[npcl_idx]))
            case _:
                raise AssertionError

class Place():
    """
    Represents the data for a location and all its sublocations.
    Sublocations are also represented by Places.
    Also contains the data for all points of interest: NPCs, enemy spawns, etc.
    This latter data is stored in a dict "poi_dict" with keys the same as the magic fields
    (e.g. "ENMY", "TBOX") and values a list of bdat_ids of entries with that magic.

    In the following, "Location" only requires the existence of lb, ub, and polygon methods. In reality, all relevant functions can take either a Location or a RestSpot.
    """
    def __init__(self, location: Location | RestSpot, subplaces: list[Place]=[]) -> None:
        """
        Takes in a Location and, optionally, a list of Places to be the sublocations.
        Initialises self.bdat_id, self.location, self.places, self.poi_dict (points of interest).
        """
        self.bdat_id = location.bdat_id
        self.location = location
        self.places = subplaces
        self.poi_dict = {}
    
    def insert_subplace_directly(self, subplace: Place):
        """
        Inserts a Place directly to self's list of subplaces.
        """
        self.places.append(subplace)
    
    def remove_subplaces(self, subplace_indices_to_remove: list):
        """
        Takes in a boolean mask with length len(self.places).
        Removes all places at indices where the mask == True.
        """
        self.places = [place for i, place in enumerate(self.places) if not subplace_indices_to_remove[i]]

    def insert_location_not_as_sublocation(self, location: Location | RestSpot):
        """
        Converts a location to a place and inserts it directly to self's list of subplaces.
        If anything in the current list of places is a sublocation, removes them from the current list
        and puts them in the location's list of subplaces instead.

        ASSUMES! that the location is not a *sub*place to anything in the list of places!
        """
        subplaces_of_location = []
        indices_to_remove = [False] * len(self.places)
        for i, place in enumerate(self.places):
            if location_a_contains_b(location, place.location):
                indices_to_remove[i] = True
                subplaces_of_location.append(place)

        self.remove_subplaces(indices_to_remove)
        new_place = Place(location, subplaces_of_location)
        self.insert_subplace_directly(new_place)

    def insert_location_recursive(self, location: Location | RestSpot):
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
            place_data = place.location
            if location_a_contains_b(place_data, location):
                assert order_status != "super" # place cannot be a superlocation of one and a sublocation of another on the same level; otherwise the sublocation would be a sub of the superlocation
                order_status = "sub"
            elif location_a_contains_b(location, place_data):
                assert order_status != "sub"
                order_status = "super"

        if order_status == "sub":
            # Recursive step: location is a sublocation of at least one place in the list; add it there instead
            for place in self.places:
                if location_a_contains_b(place.location, location):
                    place.insert_location_recursive(location)
        else: # location is not a sublocation of anything, so it should be added to the list directly, and move current places to its place list if they're sublocations as necessary
            self.insert_location_not_as_sublocation(location)

    def insert_poi_directly(self, poi: PointOfInterest):
        """
        Inserts a point of interest directly into the current place('s self.poi dict),
        without considering whether or not it should go into any subplaces (or, indeed, the place itself).

        If it's already there, does nothing.
        """
        magic = poi.magic
        if magic not in self.poi_dict.keys():
            self.poi_dict[magic] = [poi.bdat_id]
        else:
            if poi.bdat_id not in self.poi_dict[magic]:
                self.poi_dict[magic].append(poi.bdat_id)

    def insert_poi_recursive(self, poi: PointOfInterest):
        """
        Inserts a point of interest where it should go in the place's subtree.
        It may be inserted in multiple subplaces, either because two places in the subtree
        (neither of which is contained in the other) each contain the poi,
        or because the poi has multiple coordinates.
        """
        for coord in poi.coordinates:
            insert_directly = True # keeps track of whether or not the poi should be inserted directly, or in one of the subplaces
            for subplace in self.places:
                if coordinate_within_location(coord, subplace.location):
                    insert_directly = False
                    subplace.insert_poi_recursive(poi)
            
            if insert_directly:
                self.insert_poi_directly(poi)

    def to_json(self):
        return_dict = {
            "bdat_id": self.bdat_id,
            "places": self.places
        }
        for k, v in self.poi_dict.items():
            return_dict[k] = v
        return return_dict
    
    # def to_json_debug(self):
    #     return {
    #         "bdat_id": convert_hashid_to_name(self.bdat_id, gmk_location, location_names),
    #         "places": self.places,
    #         "poi": self.poi_dict
    #     }

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

    assert lvb_dict != {}, "No lvb files found. Is the unpack_xbtool_path correct?"
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
    #print(f"Lvb data for this DLC has no magic {magic}")
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
        
def get_indices_from_entry(entry: dict, offset: int) -> tuple[int, int]:
    """
    Takes in a dict representing an entry from an lvb file.
    Reads the bytes, with some offset of hex digits from the right,
    and returns a tuple representing the four bytes after that offset,
    interpreted as two ints (with weird endianness as used by XC3).
    """
    bytes = get_from_entry(entry, "bytes")
    if offset != 0: # index of "-0" gets interpreted as 0, messing up the slicing
        last_high = bytes[-2-offset:-offset]
    else:
        last_high = bytes[-2-offset:]
    last_low = bytes[-4-offset:-2-offset]
    first_high = bytes[-6-offset:-4-offset]
    first_low = bytes[-8-offset:-6-offset]
    return int(first_high+first_low, 16), int(last_high+last_low, 16)

def get_cntp_indices_from_loca(loca_entry: dict) -> tuple[int, int]:
    """
    Takes in a dict representing a LOCA entry from an lvb file.
    Returns a tuple: the starting and ending index of the corresponding CNTP entries.
    """
    return get_indices_from_entry(loca_entry, 0)

def get_enem_idx(enmy_entry: dict) -> int:
    """
    Takes in a dict representing an ENMY entry from an lvb file.
    Returns the index of the corresponding ENEM entry.
    """
    _, idx = get_indices_from_entry(enmy_entry, 8)
    return idx

def get_enel_idxs(enem_entry: dict) -> tuple[int, int]:
    """
    Takes in a dict representing an ENEM entry from an lvb file.
    Returns a tuple: the starting and ending index of the corresponding ENEL entries.
    """
    return get_indices_from_entry(enem_entry, 0)

def get_npcs_idxs(npc_entry: dict) -> tuple[int, int]:
    """
    Takes in a dict representing an NPC entry from an lvb file.
    Returns a tuple: the starting and ending index of the corresponding NPCS entries.
    """
    return get_indices_from_entry(npc_entry, 16)

def get_npcl_idxs(npcs_entry: dict) -> tuple[int, int]:
    """
    Takes in a dict representing an NPCS entry from an lvb file.
    Returns a tuple: the starting and ending index of the corresponding NPCL entries.
    """
    return get_indices_from_entry(npcs_entry, 24)

def npcs_single_locator(npcs_entry: dict) -> bool:
    """
    Takes in an NPCS entry.
    Returns True if the NPCS bytes indicate that there should be a single NPCL entry
    due to the start time equalling the end time.
    """
    bytes = get_from_entry(npcs_entry, "bytes")
    byte1 = bytes[2:4]
    byte2 = bytes[4:6]
    return byte1 == byte2

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

def get_rest_spot_data(lvb_dict: dict, verbose=False) -> list[RestSpot]:
    rest_spot_list = []
    for dlc in lvb_dict.keys():
        if verbose:
            print(f"Converting rest spot data for DLC {dlc}")
        comu_data = get_lvb_entries(lvb_dict[dlc], "COMU")
        for comu_entry in comu_data:
            rest_spot = RestSpot(comu_entry)
            rest_spot_list.append(rest_spot)
    return rest_spot_list

def get_poi_data(lvb_dict: dict, magic: str, verbose=False) -> list[PointOfInterest]:
    """
    Takes in an lvb dict of a region as given by get_lvb_data, and a magic str.
    Returns a list of PointsOfInterest of that magic type in that region.
    """
    poi_list = []
    for dlc in lvb_dict.keys():
        if verbose:
            print(f"Converting {magic} data for DLC {dlc}")
        lvb_data_for_magic = get_lvb_entries(lvb_dict[dlc], magic)
        for entry in lvb_data_for_magic:
            poi = PointOfInterest(entry, lvb_dict[dlc], magic)
            poi_list.append(poi)
    return poi_list

def initialise_region(region: str) -> Location:
    """
    Takes in a region ID, purely for naming.
    Makes a "root" Location in the style of get_location_data to represent an entire region.
    Basically a cube 2e6 to a side, centred on the origin, with dummy other data.
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

def location_a_contains_b(location_a: Location | RestSpot, location_b: Location | RestSpot) -> bool:
    """
    Takes in two Locations (or RestSpots).
    Returns True if the second location is contained within the first, and False otherwise.

    For the vertical axis, we only check if the midpoint of the second is contained within the first (there are some locations that are obviously "contained" but where the second actually extends a bit above the first).

    For horizontal containment, the criterion is "Is the centre of (the bounding box of) b contained
    within (the perimeter of) a, and is b's area less than or equal to that of a's".
    More natural criteria (such as simple polygon-in-polygon containment) are too strict.
    """
    b_avg_y = (location_b.lb + location_b.ub) / 2
    if b_avg_y > location_a.ub or b_avg_y < location_a.lb:
        return False
    
    b_xmin, b_zmin, b_xmax, b_zmax = location_b.polygon.bounds
    b_centre = Point((b_xmax+b_xmin)/2, (b_zmin+b_zmax)/2)
    b_centre_in_a = location_a.polygon.contains(b_centre)
    b_leq_a = location_b.polygon.area <= location_a.polygon.area
    #return location_a.polygon.contains(location_b.polygon)
    return b_centre_in_a and b_leq_a

def coordinate_within_location(coordinate: Coordinate, location: Location | RestSpot) -> bool:
    """
    Takes in a coordinate and a location(/RestSpot).
    Returns True if the coordinate is contained within the location, and False otherwise.

    Assumes that the location is a vertical prism.
    """
    y_containment = coordinate.y >= location.lb and coordinate.y <= location.ub
    xz_containment = location.polygon.contains(coordinate.point)
    return y_containment and xz_containment

def create_place_tree(lvb_dict: dict, region: str, verbose=False) -> Place:
    """
    Takes in the lvb data of a region as given by get_lvb_data,
    and a region ID (e.g. ma01a).
    Returns a tree-style dict structure, where each node corresponds to a location(/landmark/area/etc).
    Each node is a Place, which can have other places as subnodes.

    The place tree is filled with all the LOCA entries (Locations) and COMU entries (Rest Spots).
    """
    if verbose:
        print("Initialising region...")
    place_tree = Place(initialise_region(region))

    types = [(get_location_data, "locations"),
             (get_rest_spot_data, "rest spots")]
    for place_type in types:
        get_data = place_type[0]
        name = place_type[1]

        if verbose:
            print(f"Converting lvb data to {name}...")
        location_list = get_data(lvb_dict, verbose)

        if verbose:
            num = len(location_list)
            print(f"Adding {num} {name} to the tree...")

        for i, location in enumerate(location_list):
            if verbose and (i % 10 == 0 or i == num - 1):
                bdat_id = location.bdat_id
                print(f"{i+1}/{num}: {bdat_id}")
            place_tree.insert_location_recursive(location)

    return place_tree

def fill_place_tree_with_magic(place_tree: Place, lvb_dict: dict, magic: str, verbose=False):
    """
    Takes in a place_tree which has had all its locations/rest spots filled in,
    and the lvb data for a region as given by get_lvb_data,
    and a magic str.
    Fills in the place tree with all the entities of that magic type. 
    """
    if verbose:
        print(f"Processing magic {magic}")
        print(f"Creating {magic} coordinate data from lvb data...")

    poi_data = get_poi_data(lvb_dict, magic)

    if verbose:
        num = len(poi_data)
        print(f"Adding {num} {magic} to place tree...")

    for i, poi in enumerate(poi_data):
        if verbose and (i % 10 == 0 or i == num - 1):
            bdat_id = poi.bdat_id
            print(f"{i+1}/{num}: {bdat_id}")

        place_tree.insert_poi_recursive(poi)

#####################################################################

# Additional debugging stuff

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

# To enter debug mode: uncomment the below lines, replace with paths to your own TSVs of the maXXa_GMK_Location and msg_location_name_en bdats (as processed by https://github.com/Sir-Teatei-Moonlight/xenoblade-bdat-tools/blob/root/bdat2_reader.py and the hash mapper in the same repo), and replace the to_json method of the Place class with to_json_debug. (It needs to be called to_json or else xeno_lvb won't work.)

# gmk_location_path = Path(f"C:/Users/rtg14/Desktop/Not_work/My_Programs/wiki_bdat_processing/XC3_colonies/bdats/ma01a_GMK_Location.tsv")
# location_names_path = Path(f"C:/Users/rtg14/Desktop/Not_work/My_Programs/wiki_bdat_processing/XC3_colonies/bdats/msg_location_name_en.tsv")
# gmk_location, location_names = get_location_bdats(gmk_location_path, location_names_path)

#############################################################################

from json import JSONEncoder
def _default(self, obj):
    return getattr(obj.__class__, "to_json", _default.default)(obj)
_default.default = JSONEncoder().default
JSONEncoder.default = _default
JSON_INCL_BYTES = True

def main(region, unpack_xbtool_path, outpath, verbose=False):
    if verbose:
        print("Getting lvb data...")
    lvb_data = get_lvb_data(region, unpack_xbtool_path, verbose=verbose)

    if verbose:
        print("Creating place tree...")
    place_tree = create_place_tree(lvb_data, region, verbose=verbose)

    if verbose:
        print("Filling place tree with object data...")
    if region == "ma40a":
        fields = ["ENMY", "NPC ", "TBOX", "PREC", "RBOX", "ETHP", "ARCH", "ENSP", "EAFF", "ENFO", "KIEV"]
    else:
        fields = ["ENMY", "NPC ", "TBOX", "PREC"]
    for magic in fields:
        fill_place_tree_with_magic(place_tree, lvb_data, magic, verbose=verbose) 

    if verbose:
        print("Writing to file...")

    outfile = open(outpath, "w+", encoding="utf-8-sig")
    outfile.write(json.dumps(place_tree, indent=1))
    outfile.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("region", help="The ID of the region to make a tree for (e.g. ma01a for the Aetia Region)")
    parser.add_argument("unpack_xbtool_path", help="The path to the output of unpack_xbtool. This directory should have subfolders such as gmk_r, dlc1, dlc2, bdat, etc. (Only gmk_r and the dlc folders are used.)")
    parser.add_argument("outpath", help="The filename to save the output json string to.")
    parser.add_argument("-v", "--verbose", help="increase output verbosity",
                    action="store_true")
    args = parser.parse_args()

    main(args.region, Path(args.unpack_xbtool_path), Path(args.outpath), args.verbose)