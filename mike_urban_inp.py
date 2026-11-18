"""Compatibility command and import for :mod:`epanet_addons.mike_urban.inp`."""

import argparse
from pathlib import Path

from epanet_addons.mike_urban.inp import *

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(mdb_to_inp(args.source, args.destination))
