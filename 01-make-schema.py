"""
Creates the YAGO 4 schema from schema.org and the hard-coded shapes

CC-BY 2022 Fabian M. Suchanek

Call:
  python3 01-make-schema.py

Input:
- 00-shapes.ttl, the hard-coded YAGO shapes
- 00-schema-org.ttl, the taxonomy from schema.org

Output:
- 01-yago-final-schema.ttl, the YAGO schema and top-level taxonomy
    
Algorithm:
1) Load schema.org taxonomy and hard-coded shapes
2) From the taxonomy keep only the classes that are mentioned in shapes, together with their superclasses. Force this to be a tree.
"""

OUTPUT_FOLDER="yago-data/"
INPUT_FOLDER= "input-data"

###########################################################################
#           Booting
###########################################################################

print("Step 01: Creating YAGO schema...")
print("  Importing...",end="", flush=True)
from TurtleUtils import Graph
import TurtleUtils
import sys
from os.path import exists
import evaluator
import Prefixes
import re
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

for s, p, o in yagoShapes:
    for t in (s, p, o):
        if not TurtleUtils.checkTerm(t):
            print("  Warning: illegal term:", t)
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
    if not existingSuperClasses and not schemaTaxonomy.objects(schemaClass, Prefixes.rdfsSubClassOf) and not schemaClass==Prefixes.schemaThing:
        print("  Warning:",schemaClass,"is not a transitive subclass of schema:Thing")
    for superClass in schemaTaxonomy.objects(schemaClass, Prefixes.rdfsSubClassOf):
        if superClass in existingSuperClasses:
            continue
        if existingSuperClasses:
            print("  Info:",schemaClass,"already has the superclass",existingSuperClasses[0],", not adding",superClass)
            continue
        yagoShapes.add((schemaClass, Prefixes.rdfsSubClassOf, superClass))
        addSuperClasses(superClass)
        
for schemaClass in yagoShapes.subjects(Prefixes.fromClass):
    addSuperClasses(schemaClass)

# Verify self-containedness
permitted_namespaces = ["geo:", "rdfs:", "yago:", "xsd:"]
for targetClass in yagoShapes.objects(None, Prefixes.shaclNode):
    if targetClass==Prefixes.schemaThing:
        continue
    if any(targetClass.startswith(s) for s in permitted_namespaces):
        continue    
    if not yagoShapes.objects(targetClass, Prefixes.rdfsSubClassOf):
        print("  Warning: the range",targetClass,"is undefined in the schema")

# Verify unique property mappings
for o in yagoShapes.objects(None, Prefixes.fromProperty):
    mappedTo=set(c for b in yagoShapes.subjects(Prefixes.fromProperty, o) for c in yagoShapes.objects(b, Prefixes.shaclPath) )
    if len(mappedTo)>1:
        print("  Warning: the Wikidata property",o,"is mapped to more than one YAGO property:",mappedTo)
        
# Verify the SHACL patterns
for s,p,o in yagoShapes.triplesWithPredicate(Prefixes.shaclPattern):
    try:
        re.compile(TurtleUtils.splitLiteral(o)[0])
    except:
        print("  Warning: the SHACL pattern",TurtleUtils.splitLiteral(o)[0],"does not compile as a regex, removing")
        yagoShapes.remove((s,p,o))

# Verify max counts
for o in yagoShapes.objects(None, Prefixes.shaclMaxCount):
    _, intMaxCount, _, _ = TurtleUtils.splitLiteral(o)    
    if intMaxCount is None or intMaxCount<=0:
        print("  Warning: Maxcount has to be a positive int, not ",o)
        
# Add "rdf:type rdfs:Class" to define an implicit target class
for s in yagoShapes.subjects(Prefixes.rdfType, Prefixes.shaclNodeShape):
    yagoShapes.add((s, Prefixes.rdfType, Prefixes.rdfsClass))
    
###########################################################################
#           Write YAGO schema
###########################################################################

# The schema is best in TTL
print("  Writing schema to",OUTPUT_FOLDER,"...", end="", flush=True)
yagoShapes.printToFile(OUTPUT_FOLDER+"01-yago-final-schema.ttl")
print("done")

print("done")