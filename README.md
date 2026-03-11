# xeno-lvb

A tool to extract gimmick disposition files (`.lvb`) from Xenoblade 2 and 3.

## Differences from [original fork](https://github.com/roccodev/xeno-lvb)

* xeno_lvb.py dumps the bytes of the gimmick data always, not only if __name__==__main__.
* Hash IDs do not have angle brackets <>.
* create_lookup_tree.py has been added. TODO: More comprehensive documentation, once it's complete.