# xeno-lvb

A tool to extract gimmick disposition files (`.lvb`) from Xenoblade 2 and 3, modified for Xeno Series Wiki purposes.

## Differences from [original fork](https://github.com/roccodev/xeno-lvb)

* xeno_lvb.py dumps the bytes of the gimmick data always, not only if `__name__==__main__`.
* Hash IDs do not have angle brackets <>.
* create_lookup_tree.py has been added. This creates a tree (in json format) for a given region, where nodes are a location in that region and every object in that location, and subnodes are sublocations of that location.

## Usage of create_lookup_tree.py
```
python create_lookup_tree.py [region] [unpack_xbtool_path] [outpath] (--verbose)
```
* `region`: The ID of the region to make a tree for (e.g. ma01a for the Aetia Region).
* `unpack_xbtool_path`: The path to the output of xbtool, as used on the data of (your own copy of) Xenoblade 3. This directory should have subfolders such as gmk_r, dlc1, dlc2, bdat, etc. (Only gmk_r and the dlc folders are used.)
* `outpath`: The filename to save the output string to, in json form.

## Debug mode
There also exists a debug mode, which prints the in-game names of locations rather than their hash IDs, and slightly reorganises the output format. Its use is somewhat more involved and requires modifying the source code; search "debug mode" in the code for instructions.