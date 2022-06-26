"""
Creates the YAGO 4 taxonomy from the Wikidata taxonomy

(c) 2021 Fabian M. Suchanek

Call:
  python3 01-make-taxonomy.py

Input:
- a folder "input-data" with 
  - the hard-coded YAGO top-level taxonomy
  - a wikidata file 00-wikidata.ttl.gz

Output:
- The YAGO top-level taxonomy in 01-yago-schema.ttl
- The YAGO lower level taxonomy in 01-yago-taxonomy.tsv
- Unmapped classes (which appear in Wikidata but not in YAGO, and whose instances have to be attached to a superclass in YAGO) in 01-non-yago-classes.tsv
    
Algorithm:
1) Start with top-level YAGO classes
2) For each YAGO top level class y that is mapped to a Wikidata class w,
   glue the entire subtree of w under y,
   - excluding bad classes
   - skipping over classes that do not have an English Wikipedia page
3) Remove a class and its descendants if it transitively subclasses two disjoint classes
"""

TEST=True
OUTPUT_FOLDER="test-data/01-make-taxonomy/" if TEST else "yago-data/"
WIKIDATA_FILE= "test-data/01-make-taxonomy/00-wikidata.ttl" if TEST else "input-data/wikidata.ttl.gz"

###########################################################################
#           Booting
###########################################################################

print("Creating YAGO taxonomy...")
print("  Importing...",end="", flush=True)
from rdflib import URIRef, RDFS, Graph
import utils
import sys
from os.path import exists
from collections import defaultdict
import evaluator
print("done")

if not(exists("input-data")):
    print("  'data' folder not found\nfailed")
    exit()

###########################################################################
#           Load YAGO top-level taxonomy and Wikidata taxonomy
###########################################################################

# Load YAGO schema
print("  Loading YAGO schema...", end="", flush=True)
yagoSchema = Graph()
# yagoSchema.parse("input-data/bio-schema.ttl", format="turtle")
yagoSchema.parse("input-data/schema.ttl", format="turtle")
yagoSchema.parse("input-data/shapes.ttl", format="turtle")
yagoSchema.parse("input-data/bio-shapes.ttl", format="turtle")
print("done")

# YAGO taxonomy
# mapping a subclass to its superclasses and vice versa
yagoTaxonomyUp = defaultdict(set)
yagoTaxonomyDown = defaultdict(set)
for (s,p,o) in yagoSchema.triples((None, RDFS.subClassOf, None)):
    yagoTaxonomyUp[s].add(o)
    yagoTaxonomyDown[o].add(s)
    
# Load Wikidata taxonomy
wikidataTaxonomy = Graph()
wikidataClassesWithWikipediaPage=set()

for graph in utils.readWikidataEntities(WIKIDATA_FILE):
    for s,p,o in graph.triples((None, utils.wikidataSubClassOf, None)):
        wikidataTaxonomy.add((s,RDFS.subClassOf,o))
        for w in graph.subjects(utils.schemaAbout, s):
            if w.startswith("https://en.wikipedia.org/wiki/"):
                wikidataClassesWithWikipediaPage.add(s)

###########################################################################
#           Create YAGO taxonomy
###########################################################################

# Classes that will not be added to YAGO, and whose children won't be added either
badClasses = {
    URIRef("http://www.wikidata.org/entity/Q17379835"), # Wikimedia page outside the main knowledge tree
    URIRef("http://www.wikidata.org/entity/Q17442446"), # Wikimedia internal stuff
    URIRef("http://www.wikidata.org/entity/Q4167410"),  # disambiguation page
    URIRef("http://www.wikidata.org/entity/Q13406463"), # list article
    URIRef("http://www.wikidata.org/entity/Q17524420"), # aspect of history
    URIRef("http://www.wikidata.org/entity/Q18340514")  # article about events in a specific year or time period
}

def addSubClasses(lastGoodYagoClass, wikidataClass, unmappedClassesWriter, treated, pathToRoot):
    """Adds the Wikidata classes to the YAGO taxonomy, excluding bad classes and classes without Wikipedia pages"""
    if wikidataClass in badClasses:
        return
    if wikidataClass in pathToRoot:
        return
    if wikidataClass in wikidataClassesWithWikipediaPage:
        yagoTaxonomyUp[wikidataClass].add(lastGoodYagoClass)
        yagoTaxonomyDown[lastGoodYagoClass].add(wikidataClass)
        lastGoodYagoClass=wikidataClass
    else:       
        unmappedClassesWriter.writeFact(utils.compressPrefix(wikidataClass),"rdfs:subClassOf",utils.compressPrefix(lastGoodYagoClass))
    # "Treated" serves to avoid adding the subclasses again in case of double inheritance
    if wikidataClass in treated:
        return
    treated.add(wikidataClass)
    pathToRoot.append(wikidataClass)
    for subClass in wikidataTaxonomy.subjects(RDFS.subClassOf, wikidataClass):    
        addSubClasses(lastGoodYagoClass, subClass, unmappedClassesWriter, treated, pathToRoot)
    pathToRoot.pop()

print("  Creating YAGO taxonomy...", end="", flush=True)
with utils.TsvFileWriter(OUTPUT_FOLDER+"01-non-yago-classes.tsv") as unmappedClassesWriter:
    treated=set()
    for s,p,o in yagoSchema.triples((None, utils.fromClass, None)):
        if s!=utils.schemaThing:
            for subclass in wikidataTaxonomy.subjects(RDFS.subClassOf, o):
                addSubClasses(s,subclass, unmappedClassesWriter,treated,[o])
print("done")

###########################################################################
#           Remove classes that subclass two disjoint top-level classes
###########################################################################

def disjoint(disjointTopLevelClass, cls):
    """TRUE if cls is a transitive subclass of a class that is disjoint with disjointTopLevelClass"""    
    return any(yagoSchema.triples((disjointTopLevelClass, utils.owlDisjointWith, cls))) \
        or any(disjoint(disjointTopLevelClass, superclass) for superclass in yagoTaxonomyUp[cls])

def removeClass(cls):
    """ Removes the class from the YAGO taxonomy """    
    for subClass in set(yagoTaxonomyDown[cls]):
        removeClass(subClass)
    yagoTaxonomyDown.pop(cls)
    for superclass in yagoTaxonomyUp[cls]:
        yagoTaxonomyDown[superclass].remove(cls)    
    yagoTaxonomyUp.pop(cls)
    
def checkDisjointness(disjointTopLevelClass, currentClass):
    """ Recursively top-down removes any classes that are disjoint with disjointTopLevelClass, starting with currentClass """   
    for subClass in set(yagoTaxonomyDown[currentClass]):
        for otherSuperclass in yagoTaxonomyUp[subClass]:
            if otherSuperclass==currentClass:
                continue
            if disjoint(disjointTopLevelClass, otherSuperclass):
                removeClass(subClass)
        checkDisjointness(disjointTopLevelClass, subClass)

print("  Removing disjoint-inconsistent classes...", end="", flush=True)
for disjointTopLevelClass in yagoSchema.subjects(utils.owlDisjointWith, None):
    checkDisjointness(disjointTopLevelClass, utils.schemaThing)
print("done")

###########################################################################
#           Serialize the result
###########################################################################

# The schema is most beautiful in native TTL
print("  Writing schema...", end="", flush=True)
yagoSchema.serialize(destination=(OUTPUT_FOLDER+"01-yago-schema.ttl"), format="turtle", encoding="UTF-8")
print("done")

print("  Writing taxonomy...", end="", flush=True)
with utils.TsvFileWriter(OUTPUT_FOLDER+"01-yago-taxonomy.tsv") as taxonomyWriter:
    for cls in yagoTaxonomyUp:
        for superclass in yagoTaxonomyUp[cls]:
            taxonomyWriter.writeFact(utils.compressPrefix(cls), "rdfs:subClassOf", utils.compressPrefix(superclass))
print("done")
print("done")

if TEST:
    evaluator.compare(OUTPUT_FOLDER+"01-non-yago-classes.tsv")
    evaluator.compare(OUTPUT_FOLDER+"01-yago-taxonomy.tsv")
    print("YAGO Schema has to be compared by hand")