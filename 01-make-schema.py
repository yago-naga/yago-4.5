"""
Creates the YAGO 4.5.1 schema from the hard-coded shapes

CC-BY 2022-2025 Fabian M. Suchanek

Call:
  python3 01-make-schema.py

Input:
- yago-schema.ttl, the hard-coded YAGO schema and shapes

Output:
- 01-yago-final-schema.ttl, the YAGO schema, checked for inconsistencies
    
Algorithm:
1) Load the schema
2) Write out the schema
"""

###########################################################################
#           Booting
###########################################################################

import TurtleUtils
import sys
import os
import Evaluator
import Prefixes
import re
import Schema

OUTPUT_FOLDER="yago-data/"
INPUT_FOLDER= "input-data"

print("Step 01: Creating YAGO schema...")

if not os.path.exists(INPUT_FOLDER):
    print(f"  Input folder {INPUT_FOLDER} not found\nfailed")
    exit()

# Load YAGO shapes
yagoSchema=Schema.YagoSchema(INPUT_FOLDER+"/yago-schema.ttl")

# Write out the schema
print("  Writing schema to",OUTPUT_FOLDER,"...", end="", flush=True)
yagoSchema.writeToFile(OUTPUT_FOLDER+"01-yago-final-schema.ttl")
print("done")

print("done")
