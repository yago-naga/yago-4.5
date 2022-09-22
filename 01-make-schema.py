"""
Creates the YAGO 4 schema from schema.org and the hard-coded shapes

(c) 2022 Fabian M. Suchanek

Call:
  python3 01-make-schema.py

Input:
- 00-shapes.ttl, the hard-coded YAGO shapes
- 00-schema-org.ttl, the taxonomy from schema.org

Output:
- 01-yago-schema.ttl, the YAGO schema and top-level taxonomy
    
Algorithm:
1) Load schema.org taxonomy and hard-coded shapes
2) From the taxonomy keep only the classes that are mentioned in shapes, together with their superclasses. Force this to be a tree.
"""

TEST=False
OUTPUT_FOLDER="test-data/01-make-schema/" if TEST else "yago-data/"
INPUT_FOLDER= "input-data"

###########################################################################
#           Booting
###########################################################################

print("Creating YAGO schema...")
print("  Importing...",end="", flush=True)
from TurtleUtils import Graph
import sys
from os.path import exists
import evaluator
import Prefixes
print("done")

if not(exists("input-data")):
    print("  'input-data' folder not found\nfailed")
    exit()

###########################################################################
#           Load Schema data and Shape data
###########################################################################

# Load YAGO shapes
yagoShapes = Graph()
yagoShapes.loadTurtleFile(INPUT_FOLDER+"/00-shapes.ttl", "  Loading YAGO shapes")

# Load Schema.org taxonomy
schemaTaxonomy = Graph()
schemaTaxonomy.loadTurtleFile(INPUT_FOLDER+"/00-schema-org.ttl", "  Loading Schema.org taxonomy")

###########################################################################
#           Construct YAGO schema
###########################################################################

# Add in all super-classes

def addSuperClasses(schemaClass):
    """ Adds all the superclasses of the given class from schema.org to yagoShapes, forcing a tree structure"""
    existingSuperClasses=yagoShapes.objects(schemaClass, Prefixes.rdfsSubClassOf)
    for superClass in schemaTaxonomy.objects(schemaClass, Prefixes.rdfsSubClassOf):
        if superClass in existingSuperClasses:
            continue
        if existingSuperClasses:
            print("  Info:",schemaClass,"already has the superclasses",existingSuperClasses,", not adding",superClass)
            continue
        yagoShapes.add((schemaClass, Prefixes.rdfsSubClassOf, superClass))
        addSuperClasses(superClass)
        
for schemaClass in yagoShapes.subjects(Prefixes.fromClass):
    addSuperClasses(schemaClass)

# Now we verify self-containedness

permitted_namespaces = ["geo:", "rdfs:", "yago:", "xsd:"]

for targetClass in yagoShapes.objects(None, Prefixes.shaclNode):
    if targetClass==Prefixes.schemaThing:
        continue
    if any(targetClass.startswith(s) for s in permitted_namespaces):
        continue    
    if not yagoShapes.objects(targetClass, Prefixes.rdfsSubClassOf):
        print("  Warning: the range",targetClass,"is undefined in the schema")
    
###########################################################################
#           Write and test YAGO schema
###########################################################################

# The schema is best in TTL
print("  Writing schema...", end="", flush=True)
yagoShapes.printToFile(OUTPUT_FOLDER+"01-yago-schema.ttl")
print("done")

print("done")

#if TEST:
    #evaluator.compare(OUTPUT_FOLDER+"01-yago-schema.ttl", OUTPUT_FOLDER+"01-yago-schema-gold.ttl")