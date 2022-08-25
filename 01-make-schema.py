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
2) From the taxonomy keep only the classes that are mentioned in shapes, together with their superclasses
"""

TEST=True
OUTPUT_FOLDER="test-data/01-make-schema/" if TEST else "yago-data/"
INPUT_FOLDER= "input-data"

###########################################################################
#           Booting
###########################################################################

print("Creating YAGO schema...")
print("  Importing...",end="", flush=True)
from rdflib import URIRef, RDFS, Graph
import utils
import sys
from os.path import exists
import evaluator
print("done")

if not(exists("input-data")):
    print("  'input-data' folder not found\nfailed")
    exit()

###########################################################################
#           Load Schema data and Shape data
###########################################################################

# Load YAGO shapes
print("  Loading YAGO shapes...", end="", flush=True)
yagoShapes = Graph()
yagoShapes.parse(INPUT_FOLDER+"/00-shapes.ttl", format="turtle")
print("done")

# Load Schema.org taxonomy
print("  Loading Schema.org taxonomy...", end="", flush=True)
schemaTaxonomy = Graph()
schemaTaxonomy.parse(INPUT_FOLDER+"/00-schema-org.ttl", format="turtle")
print("done")

###########################################################################
#           Construct YAGO schema
###########################################################################

def addSuperClasses(schemaClass):
    for superClass in schemaTaxonomy.objects(schemaClass, RDFS.subClassOf):
        yagoShapes.add((schemaClass, RDFS.subClassOf, superClass))
        addSuperClasses(superClass)
        
for schemaClass in yagoShapes.subjects(utils.fromClass, None):
    addSuperClasses(schemaClass)

permitted_namespaces = ["http://www.opengis.net/ont/geosparql#", "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "http://yago-knowledge.org/schema#", "http://www.w3.org/2001/XMLSchema#"]

for targetClass in yagoShapes.objects(None, utils.shaclNode):
    if targetClass==utils.schemaThing:
        continue
    if any(targetClass.startswith(s) for s in permitted_namespaces):
        continue    
    if (targetClass, RDFS.subClassOf, None) not in yagoShapes:
        print("  *** Undefined range:",targetClass)
    
###########################################################################
#           Write and test YAGO schema
###########################################################################

# The schema is most beautiful in native TTL
print("  Writing schema...", end="", flush=True)
yagoShapes.serialize(destination=(OUTPUT_FOLDER+"01-yago-schema.ttl"), format="turtle", encoding="UTF-8")
print("done")

print("done")

if TEST:
    print("The schema is TTL and thus cannot be compared automatically to the gold standard.")